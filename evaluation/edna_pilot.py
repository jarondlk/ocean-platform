"""Verify saved pilot answers and explicit human scientific reviews; no LLM calls."""

from collections import Counter

from api.schemas import ChatRequest, ChatResponse
from ingestion.edna_analysis_bundle import load_analysis
from ingestion.immutable_bundle import digest
from orchestration.answer_audit import audit_answer


def evaluate_records(cases, records, *, resolve_citation, max_latency_ms=120000):
    if not isinstance(records, list) or len(records) > 50:
        raise ValueError("Expected at most 50 saved pilot records")
    expected = {c["id"]: c for c in cases["cases"]}
    if len(expected) != len(cases["cases"]):
        raise ValueError("Duplicate evaluation case IDs")
    counts = Counter(r.get("case_id") for r in records)
    results = []
    for record in records:
        identity = record.get("case_id")
        errors = []
        if identity not in expected or counts[identity] != 1:
            results.append(
                {
                    "case_id": identity,
                    "passed": False,
                    "errors": ["unknown_or_duplicate_case"],
                }
            )
            continue
        try:
            request = ChatRequest.model_validate(record["request"])
            response = ChatResponse.model_validate(record["response"])
            if (
                request.query != expected[identity]["question"]
                or response.query != request.query
            ):
                errors.append("question_mismatch")
            if (
                not request.analysis_id
                or response.options.get("context", {}).get("analysis_id")
                != request.analysis_id
            ):
                errors.append("analysis_selection_mismatch")
            else:
                bundle = load_analysis(request.analysis_id)
                for context in response.analysis_context:
                    if (
                        context.analysis_id != request.analysis_id
                        or context.table not in bundle["tables"]
                    ):
                        errors.append("context_analysis_mismatch")
                        continue
                    ids = {r["result_id"] for r in bundle["tables"][context.table]}
                    if not context.result_ids or not set(context.result_ids) <= ids:
                        errors.append("context_result_mismatch")
            audit = audit_answer(
                query=response.query,
                answer=response.answer,
                primary_sources=[r.model_dump() for r in response.sources],
                linked_sources=[r.model_dump() for r in response.linked_sources],
                analysis_context=[r.model_dump() for r in response.analysis_context],
                reliability_context=[
                    r.model_dump() for r in response.reliability_context
                ],
                retrieval_diagnostics=response.retrieval_diagnostics,
            )
            if not audit["citation_count"] or audit["invalid_citation_count"]:
                errors.append("missing_or_invalid_citations")
            traces = {}
            for citation in audit["citations"]:
                citation_id = citation["citation_id"]
                trace = resolve_citation(citation_id)
                if not trace.get("found"):
                    errors.append("unresolved_citation")
                traces[citation_id] = digest(trace)
            review = record.get("review") or {}
            if (
                review.get("verdict") != "accepted"
                or not review.get("reviewer")
                or not review.get("reviewed_at")
                or not review.get("notes")
                or review.get("source_values_checked") is not True
                or review.get("unsupported_scientific_claims") is not False
            ):
                errors.append("researcher_review_required")
            elapsed = record.get("latency_ms")
            if (
                not isinstance(elapsed, (int, float))
                or not 0 < elapsed <= max_latency_ms
            ):
                errors.append("latency_missing_or_exceeded")
            if record.get("kind") not in {"live", "synthetic"}:
                errors.append("evidence_kind_required")
            results.append(
                {
                    "case_id": identity,
                    "kind": record.get("kind"),
                    "passed": not errors,
                    "errors": sorted(set(errors)),
                    "record_sha256": digest(record),
                    "citation_count": audit["citation_count"],
                    "trace_sha256": traces,
                    "model": response.model,
                    "analysis_id": request.analysis_id,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "case_id": identity,
                    "passed": False,
                    "errors": ["validation_failed"],
                    "error_type": type(exc).__name__,
                }
            )
    missing = sorted(set(expected) - set(counts))
    live = sum(r.get("kind") == "live" and r["passed"] for r in results)
    return {
        "schema_version": 1,
        "case_set_sha256": digest(cases),
        "required_cases": len(expected),
        "submitted": len(records),
        "passed": sum(r["passed"] for r in results),
        "live_passed": live,
        "synthetic_passed": sum(
            r.get("kind") == "synthetic" and r["passed"] for r in results
        ),
        "missing_cases": missing,
        "accepted": not missing
        and len(results) == len(expected)
        and all(r["passed"] for r in results)
        and live > 0,
        "results": results,
        "limitations": [
            "Human verdicts and live/synthetic labels are supplied, not independently authenticated.",
            "This report does not establish deployment, study validity, or causal inference.",
        ],
    }
