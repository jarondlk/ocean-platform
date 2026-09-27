"""Run realistic questions against the local full ANEMONE candidate.

This is an acceptance probe, not an automatic scientific-quality judge. It
retains full answers for human review and checks numeric expectations/citations.
The local phase never calls a model. The model phase uses real configured Vertex
responses with the normal hybrid retrieval settings. It requires a populated
embedding index and refuses to call a missing index a successful model test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse


def metric(summary, key):
    if key == "group_count":
        return len(summary["groups"])
    value = summary
    for part in key.split("."):
        if isinstance(value, list):
            value = next(row for row in value if row.get("assignment_method") == part)
        else:
            value = value[part]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--serving-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["local", "model"], default="local")
    parser.add_argument(
        "--matrix", type=Path, default=Path("evaluation/qa/anemone_v050_questions.json")
    )
    args = parser.parse_args()
    if urlparse(args.database_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("This probe is restricted to a local candidate database")
    os.environ["DATABASE_URL"] = args.database_url
    os.environ["AUTH_MODE"] = "disabled"
    os.environ["DEPLOYMENT_ENV"] = "development"
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    import config
    from fastapi.testclient import TestClient
    import api.main as api
    from api.schemas import ChatRequest
    from orchestration.edna_aggregation import plan_aggregation
    from ingestion.immutable_bundle import digest
    from sqlalchemy import text
    from db.connection import get_engine

    config.SERVING_DIR = args.serving_dir.resolve()
    config.ANEMONE_NORMALIZED_DIR = args.work_dir.resolve() / "normalized"
    config.RAW_ANEMONE_DIR = args.work_dir.resolve() / "raw"
    if config.EDNA_ARTIFACT_URI:
        raise ValueError("Remote artifact roots are not supported by this local probe")
    pointer = json.loads((args.work_dir / "candidate.json").read_text())
    with get_engine().connect() as c:
        publication = c.execute(
            text(
                "SELECT generation_id FROM corpus_publication WHERE channel='anemone-canonical'"
            )
        ).scalar_one()
        embeddings = c.execute(
            text(
                "SELECT count(*) FROM retrieval_document WHERE active AND embedding IS NOT NULL"
            )
        ).scalar_one()
    if publication != pointer["candidate_id"]:
        raise ValueError("Candidate/database generation mismatch")
    if args.phase == "model":
        with get_engine().connect() as c:
            active_documents = c.execute(
                text("SELECT count(*) FROM retrieval_document WHERE active")
            ).scalar_one()
        with get_engine().connect() as c:
            matching_embeddings = c.execute(
                text(
                    "SELECT count(*) FROM retrieval_document WHERE active AND embedding IS NOT NULL "
                    "AND embedding_provider=:provider AND embedding_model=:model AND embedding_dim=:dim"
                ),
                {
                    "provider": config.MODEL_PROVIDER,
                    "model": config.EMBEDDING_MODEL,
                    "dim": config.EMBEDDING_DIM,
                },
            ).scalar_one()
        if matching_embeddings != active_documents or not active_documents:
            raise ValueError(
                "Model QA requires complete embeddings matching the configured model/provider/dimension; populate the local retrieval index first"
            )
        if config.MODEL_PROVIDER != "vertex":
            raise ValueError("Model phase requires the configured Vertex runtime")
        # Use the user's existing gcloud credential only in memory. No persistent
        # ADC credential, key, token artifact, or model-response stub is created.
        import subprocess
        from google import genai
        from google.genai import types
        from google.oauth2.credentials import Credentials
        from model_runtime import get_model_runtime

        token = subprocess.run(
            ["gcloud", "auth", "print-access-token", "--quiet"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
        runtime = get_model_runtime()
        runtime.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
            credentials=Credentials(token),
            http_options=types.HttpOptions(
                api_version="v1",
                timeout=60000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        api.get_model_runtime = lambda: runtime
        import db.vector_store as vectors

        vectors.get_model_runtime = lambda: runtime
    matrix = json.loads(args.matrix.read_text())
    client = TestClient(api.app, raise_server_exceptions=False)
    traces = {}
    results = []
    for case in matrix["cases"]:
        request = {"query": case["query"], **case["options"]}
        validated = ChatRequest(**request)
        plan = plan_aggregation(validated.model_dump())
        needs_model = plan is None
        if needs_model != (args.phase == "model"):
            continue
        started = time.monotonic()
        response = client.post("/chat", json=request)
        result = {
            "id": case["id"],
            "query": case["query"],
            "request": request,
            "expected_behavior": case["expected_behavior"],
            "http_status": response.status_code,
        }
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": "non-JSON response"}
        result["response"] = payload
        issues, checks = [], {}
        if response.status_code != 200:
            issues.append("request_failed")
        else:
            expected = case["expected_kind"]
            answered = payload["outcome"] == "answered"
            if expected == "answer" and not answered:
                issues.append("unnecessary_clarification")
            if expected == "explanation" and not answered:
                issues.append("interpretation_misrouted_as_count")
            if expected == "clarify" and answered:
                issues.append("unsupported_scope_answered")
            if expected == "bounded" and not answered:
                issues.append("capability_limit")
            if answered:
                audit = payload.get("answer_audit") or {}
                checks["citation_audit"] = audit.get(
                    "invalid_citation_count"
                ) == 0 and bool(audit.get("valid_citation_count"))
                if not checks["citation_audit"]:
                    issues.append("citation_audit_failed")
                result["audit_warnings"] = audit.get("warnings", [])
                ids = sorted(
                    {
                        record["citation_id"]
                        for record in audit.get("citations", [])
                        if record.get("valid")
                    }
                )
                checks["cited_document_count"] = len(ids)
                for identity in ids:
                    if identity not in traces:
                        trace = client.get("/provenance/trace/" + identity)
                        traces[identity] = {
                            "status": trace.status_code,
                            "payload": trace.json(),
                        }
                    trace = traces[identity]
                    if trace["status"] != 200 or not trace["payload"].get("found"):
                        issues.append("citation_trace_failed")
                    if identity.startswith("aggregate_edna_"):
                        aggregate_id = identity.removeprefix("aggregate_edna_")
                        export = client.get("/data/edna/aggregates/" + aggregate_id)
                        evidence = export.json().get("payload", {})
                        checks["export_hash"] = (
                            export.status_code == 200
                            and digest(evidence) == aggregate_id
                        )
                        checks["trace_matches_export"] = (
                            trace["payload"]
                            .get("trace", {})
                            .get("document", {})
                            .get("metadata")
                            == evidence
                        )
                        for name, expected_value in case["expected_metrics"].items():
                            try:
                                actual = metric(evidence["summary"], name)
                            except (KeyError, StopIteration):
                                actual = "missing"
                            checks[name] = {
                                "expected": expected_value,
                                "actual": actual,
                                "pass": actual == expected_value,
                            }
                            if actual != expected_value:
                                issues.append("numeric_mismatch:" + name)
                        if (
                            not checks["export_hash"]
                            or not checks["trace_matches_export"]
                        ):
                            issues.append("aggregate_evidence_mismatch")
                if needs_model:
                    issues.append("manual_scientific_review_required")
        result.update(
            checks=checks, issues=issues, seconds=round(time.monotonic() - started, 3)
        )
        results.append(result)
        report = {
            "phase": args.phase,
            "candidate_id": publication,
            "active_embeddings": embeddings,
            "matrix_sha256": hashlib.sha256(args.matrix.read_bytes()).hexdigest(),
            "model": config.CHAT_MODEL if args.phase == "model" else None,
            "retrieval": "hybrid" if args.phase == "model" else "exact SQL; no model",
            "results": results,
            "traces": traces,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(
            json.dumps(
                {"id": case["id"], "issues": issues, "seconds": result["seconds"]}
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
