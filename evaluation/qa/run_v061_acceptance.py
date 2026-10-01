"""Bounded operator QA against the serving catalogue; claim review is separate.

This opens no listener and changes no authentication configuration or identities.
It calls the application with non-persisting QA identity data. Exact counts may
retain immutable aggregate evidence; corpus/publications/chat history are not
modified. Live authenticated UI/history checks remain a separate gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
import uuid

from sqlalchemy import text

import api.main as api
import config
from api.auth import CurrentUser, ROLE_PERMISSIONS
from api.schemas import ChatRequest
from db.connection import get_engine
from evaluation.qa.run_anemone_questions import metric
from ingestion.edna_aggregate import load_aggregate
from ingestion.immutable_bundle import digest
from model_runtime import get_model_runtime


class GenerationBudgetExceeded(RuntimeError):
    pass


class MeteredModels:
    def __init__(self, models, limit):
        self.models, self.limit = models, limit
        self.generations = []

    def __getattr__(self, name):
        return getattr(self.models, name)

    def generate_content(self, **kwargs):
        if len(self.generations) >= self.limit:
            raise GenerationBudgetExceeded("QA generation budget exhausted")
        record = {"attempt": len(self.generations) + 1, "status": "started"}
        self.generations.append(record)
        started = time.perf_counter()
        try:
            response = self.models.generate_content(**kwargs)
            record["status"] = "returned"
            usage = getattr(response, "usage_metadata", None)
            record["usage"] = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else None
            return response
        except Exception as exc:
            record.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            record["latency_ms"] = round((time.perf_counter() - started) * 1000)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("deterministic", "model"))
    parser.add_argument("--matrix", type=Path, default=Path("evaluation/qa/anemone_v061_questions.json"))
    args = parser.parse_args()
    matrix = json.loads(args.matrix.read_text())
    assert matrix["provider_generation_limit"] == 33
    assert config.MODEL_PROVIDER == "vertex" and config.CHAT_MODEL == "gemini-3.6-flash"
    assert config.PERSIST_LOCAL_CHAT not in {"1", "true", "yes"}, "QA must not create chat history"
    with get_engine().connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261001_0014"
        publication = [dict(row) for row in connection.execute(text(
            "SELECT channel,generation_id,manifest_sha256 FROM corpus_publication ORDER BY channel"
        )).mappings()]
    runtime = get_model_runtime()
    client = runtime._client()
    meter = MeteredModels(client.models, matrix["provider_generation_limit"] if args.phase == "model" else 0)
    # Only this process's provider client is wrapped; normal production limits
    # and retry behavior are retained and every actual generation is counted.
    class ClientProxy:
        models = meter
        def __getattr__(self, name):
            return getattr(client, name)
    runtime.client = ClientProxy()
    user = CurrentUser(id=uuid.UUID(int=0), email="acceptance@test.invalid", display_name=None,
        role="researcher", account_type="research", status="active", auth_provider="disabled",
        permissions=ROLE_PERMISSIONS["researcher"])
    print("V061_QA_BASELINE=" + json.dumps({"source_commit": os.environ["SOURCE_COMMIT"],
        "phase": args.phase, "model": config.CHAT_MODEL, "publication": publication,
        "chat_history_writes": 0, "claim_review": "required"}), flush=True)
    completed = 0
    for case in matrix["cases"]:
        if case["provider_generation"] != (args.phase == "model"):
            continue
        for repeat in range(1, case["repeat"] + 1):
            started = time.perf_counter()
            before = len(meter.generations)
            try:
                result = api.chat(ChatRequest(**case["request"]), user=user).model_dump(mode="json")
                issues = []
                if case["expected_kind"] in {"answer", "explanation"} and result["outcome"] != "answered" and case["id"] != "freshness":
                    issues.append("unexpected_abstention")
                if case["id"] == "freshness" and result["abstention_reason"] != "freshness_unavailable":
                    issues.append("unsupported_freshness")
                if result["model_invoked"] != case["provider_generation"]:
                    issues.append("unexpected_generation_route")
                audit = result.get("answer_audit") or {}
                if result["outcome"] == "answered" and (audit.get("invalid_citation_count") != 0 or not audit.get("valid_citation_count")):
                    issues.append("citation_audit_failed")
                checks = {}
                for document in result["analysis_context"]:
                    if document.get("aggregate_id"):
                        bundle = load_aggregate(document["aggregate_id"])
                        assert bundle and digest(bundle["payload"]) == document["aggregate_id"]
                        for key, expected in case["expected_metrics"].items():
                            actual = metric(bundle["payload"]["summary"], key)
                            checks[key] = {"actual": actual, "expected": expected}
                            if actual != expected:
                                issues.append("numeric_mismatch:" + key)
                if set(checks) != set(case["expected_metrics"]):
                    issues.append("missing_exact_metric_evidence")
                payload = {"id": case["id"], "repeat": repeat, "request": case["request"],
                    "response": result, "checks": checks, "issues": issues,
                    "provider_calls": meter.generations[before:],
                    "latency_ms": round((time.perf_counter() - started) * 1000),
                    "claim_review": "pending", "expected_behavior": case["expected_behavior"]}
                print("V061_QA_CASE=" + json.dumps(payload), flush=True)
                completed += 1
                if issues:
                    raise RuntimeError("Structural acceptance failed; stop before further generations")
            except Exception as exc:
                # Do not print connection strings, provider credentials or raw
                # exception messages in operator logs.
                print("V061_QA_STOP=" + json.dumps({"id": case["id"], "repeat": repeat,
                    "error_type": type(exc).__name__, "completed": completed,
                    "provider_calls": len(meter.generations)}), flush=True)
                raise SystemExit(1) from None
    print("V061_QA_COMPLETE=" + json.dumps({"completed": completed, "provider_calls": len(meter.generations),
        "phase": args.phase, "claim_review": "pending"}), flush=True)


if __name__ == "__main__":
    main()
