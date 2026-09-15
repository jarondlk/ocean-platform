"""Deterministic adversarial probes; reports observations without editing app code.

Run with: python -m evaluation.qa.probe_chat_contract
A false `passed` value identifies a violated QA expectation, not a pytest error.
"""

from __future__ import annotations
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

import api.main as api
import api.auth as auth
from api.schemas import ChatRequest
from db.app_models import ChatInteraction
from model_runtime import ModelOutputLimitError
from orchestration.answer_audit import audit_answer
from orchestration.citations import prepare_citations, InvalidCitationAlias
from orchestration.unified import _build_prompt_from_context, build_prompt_with_context
from tests.test_chat_feedback import _database, _install_database, _add_user


ROW = {
    "doc_id": "ctd_qa",
    "source_type": "ctd",
    "text": "The measured temperature was 12 C.",
    "time": "2024-01-01",
}


def audit(answer, rows):
    return audit_answer(
        query="What was the CTD temperature?",
        answer=answer,
        primary_sources=rows,
        linked_sources=[],
        analysis_context=[],
        reliability_context=[],
        retrieval_diagnostics={
            "expected_source_types": ["ctd"],
            "retrieved_source_types": ["ctd"],
            "missing_source_types": [],
        },
    )


def main():
    findings = []

    def record(identity, passed, **observed):
        findings.append({"id": identity, "passed": bool(passed), "observed": observed})

    wrong = audit("The measured temperature was 999 C [ctd_qa].", [ROW])
    record(
        "contradictory_claim_not_strong",
        wrong["trust_level"] != "strong",
        audit=wrong,
        supplied_value="12 C",
        claimed_value="999 C",
    )
    one_invalid = audit("12 C [ctd_qa]. Also [invented_doc].", [ROW])
    record(
        "invalid_citation_not_strong",
        one_invalid["trust_level"] != "strong",
        audit=one_invalid,
    )

    rows = [{**ROW, "doc_id": f"ctd_{i}", "text": "x" * 8000} for i in range(8)]
    prompt, manifest = build_prompt_with_context(
        "What was the CTD temperature?", rows, inject_analysis=False, inject_reliability=False
    )
    cited = prepare_citations(prompt, rows)
    absent = "ctd_7"
    result = audit(cited.resolve(f"999 C [{absent}]."), manifest["primary"])
    record(
        "truncated_source_not_validated_as_supplied",
        result["invalid_citation_count"] == 1,
        omitted_id=absent,
        header_present=f"[{absent}] (" in prompt,
        alias_count=len(cited.aliases),
        retrieved_count=len(rows),
        audit=result,
    )

    for raw in ["[S999]", "[S1, S99]", "[S1-S2]", "[S1", "[S01]"]:
        labels = prepare_citations("\n[ctd_qa] (ctd)\n12 C.", [ROW])
        try:
            labels.resolve(raw)
            rejected = False
        except InvalidCitationAlias:
            rejected = True
        record("reject_alias_" + raw, rejected)

    range_rows = [{**ROW, "doc_id": f"ctd_{i}"} for i in range(1, 9)]
    range_prompt = _build_prompt_from_context(
        "Summarize CTD.", range_rows, {"analysis": [], "reliability": []}
    )
    range_labels = prepare_citations(range_prompt, range_rows)
    for dash in ("-", "–", "—"):
        raw = f"12 C [S1{dash}S8]."
        try:
            resolved = range_labels.resolve(raw)
            accepted = True
        except InvalidCitationAlias:
            resolved = None
            accepted = False
        record(
            "known_label_range_" + dash,
            accepted,
            raw=raw,
            all_eight_labels_present=True,
            resolved=resolved,
        )

    fake_context = [
        {
            "id": "analysis_qa_2024",
            "analysis_type": "trend",
            "text": "Onagawa in 2024: temperature rose from 10 to 24 C.",
        }
    ]
    with pytest.MonkeyPatch.context() as monkey:
        factory = _database()
        user = _add_user(factory, "qa@example.invalid")
        _install_database(monkey, factory)
        monkey.setattr(auth, "authenticate_request", lambda _r: user)
        monkey.setattr(
            api,
            "retrieve_with_expansion",
            lambda *a, **kw: {
                "primary": [],
                "linked": [],
                "diagnostics": {
                    "expected_source_types": ["ctd"],
                    "retrieved_source_types": [],
                    "missing_source_types": ["ctd"],
                },
            },
        )
        prompts = []

        def generate(**kw):
            prompts.append(kw["prompt"])
            return "The temperature rose from 10 to 24 C [S1]."

        monkey.setattr(api, "get_model_runtime", lambda: SimpleNamespace(chat=generate))
        with (
            patch(
                "orchestration.unified.analysis_context_documents",
                return_value=fake_context,
            ),
            patch(
                "orchestration.unified.reliability_context_documents", return_value=[]
            ),
        ):
            response = TestClient(api.app).post(
                "/chat",
                json={
                    "query": "Summarize CTD seasonal temperature trends in this date range.",
                    "source_type": "ctd",
                    "time_from": "2099-01-01",
                    "time_to": "2099-12-31",
                },
            )
        data = response.json()
        record(
            "empty_scope_does_not_generate_from_global_context",
            data.get("model_invoked") is False,
            http_status=response.status_code,
            outcome=data.get("outcome"),
            sources=data.get("n_sources"),
            contexts=data.get("n_context_documents"),
            model_calls=len(prompts),
            date_filter_in_prompt="2099" in prompts[0] if prompts else None,
            answer=data.get("answer"),
        )
        monkey.setattr(
            api,
            "retrieve_with_expansion",
            lambda *a, **kw: {"primary": [ROW], "linked": [], "diagnostics": {}},
        )
        response = TestClient(api.app).post(
            "/chat",
            json={
                "query": "   ",
                "inject_analysis": False,
                "inject_reliability": False,
            },
        )
        record(
            "whitespace_question_rejected",
            response.status_code == 422,
            http_status=response.status_code,
            outcome=response.json().get("outcome"),
        )
        for mode in ("timeout", "limit", "unknown_alias"):

            def failure(**kw):
                if mode == "timeout":
                    raise TimeoutError("synthetic model timeout")
                if mode == "limit":
                    raise ModelOutputLimitError(max_output_tokens=32, output_tokens=32)
                return "12 C [S999]."

            monkey.setattr(
                api, "get_model_runtime", lambda: SimpleNamespace(chat=failure)
            )
            response = TestClient(api.app).post(
                "/chat",
                json={
                    "query": f"QA {mode}",
                    "inject_analysis": False,
                    "inject_reliability": False,
                    "run_answer_audit": False,
                },
            )
            with factory() as session:
                saved = session.scalars(
                    select(ChatInteraction).where(ChatInteraction.query == f"QA {mode}")
                ).one()
                record(
                    mode + "_fails_without_saved_answer",
                    response.status_code == 502
                    and saved.status == "failed"
                    and saved.answer is None,
                    http_status=response.status_code,
                    error=response.json(),
                    saved_status=saved.status,
                    saved_answer=saved.answer,
                )
        for payload in [
            {"time_from": "2099-12-31", "time_to": "2099-01-01"},
            {"source_type": "ctd", "is_control": False},
            {"num_predict": 8193},
            {"k": 26},
        ]:
            try:
                ChatRequest(query="QA validation", **payload)
                rejected = False
            except ValueError:
                rejected = True
            record("validation_" + next(iter(payload)), rejected, payload=payload)
    print(
        json.dumps(
            {
                "date": "2026-09-14",
                "scope": "deterministic candidate contract probes; synthetic evidence and isolated history",
                "results": findings,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
