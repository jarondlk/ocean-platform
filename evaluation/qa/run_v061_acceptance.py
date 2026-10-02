"""Bounded operator QA against the serving catalogue; claim review is separate.

This opens no listener and changes no authentication configuration or identities.
It calls the application with non-persisting QA identity data. Exact counts may
retain immutable aggregate evidence; corpus/publications/chat history are not
modified. Live authenticated UI/history checks remain a separate gate.
"""
from __future__ import annotations

import argparse
import hashlib
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


def emit_case(payload):
    """Keep each stdout entry well below Cloud Run's 100 KiB line limit."""
    brief = {key: payload[key] for key in ('id', 'repeat', 'issues', 'provider_calls', 'latency_ms')}
    print('V061_QA_RESULT=' + json.dumps(brief), flush=True)
    serialized = json.dumps(payload, ensure_ascii=True)
    if len(serialized) <= 48_000:
        print('V061_QA_CASE=' + serialized, flush=True)
        return
    chunks = [serialized[start:start + 16_000] for start in range(0, len(serialized), 16_000)]
    checksum = hashlib.sha256(serialized.encode()).hexdigest()
    for index, chunk in enumerate(chunks):
        print('V061_QA_CHUNK=' + json.dumps({'id': payload['id'], 'repeat': payload['repeat'],
            'index': index, 'count': len(chunks), 'sha256': checksum, 'payload': chunk}), flush=True)


def decode_cases(lines):
    """Reassemble captured records; never grade incomplete or corrupted evidence."""
    cases, groups = [], {}
    for line in lines:
        if line.startswith('V061_QA_CASE='):
            cases.append(json.loads(line.split('=', 1)[1]))
        elif line.startswith('V061_QA_CHUNK='):
            chunk = json.loads(line.split('=', 1)[1])
            groups.setdefault((chunk['id'], chunk['repeat']), []).append(chunk)
    for chunks in groups.values():
        first = chunks[0]
        if (len(chunks) != first['count'] or {c['index'] for c in chunks} != set(range(first['count']))
                or any(c['count'] != first['count'] or c['sha256'] != first['sha256'] for c in chunks)):
            raise ValueError('Incomplete or inconsistent QA chunks')
        serialized = ''.join(c['payload'] for c in sorted(chunks, key=lambda c: c['index']))
        if hashlib.sha256(serialized.encode()).hexdigest() != first['sha256']:
            raise ValueError('QA evidence hash mismatch')
        case = json.loads(serialized)
        if (case['id'], case['repeat']) != (first['id'], first['repeat']):
            raise ValueError('QA case identity mismatch')
        cases.append(case)
    return cases


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


def install_generation_meter(runtime, limit):
    """Bind the application's generation factory to this process's metered client.

    get_model_runtime normally returns a fresh runtime. Wrapping an unused
    instance cannot meter api.chat; only this non-serving operator process
    reuses the concrete Vertex runtime. Embedding clients remain unchanged.
    """
    client = runtime._client()
    meter = MeteredModels(client.models, limit)
    class ClientProxy:
        models = meter
        def __getattr__(self, name):
            return getattr(client, name)
    runtime.client = ClientProxy()
    def factory(provider=None):
        if provider not in (None, 'vertex'):
            raise ValueError('QA generation must use Vertex')
        return runtime
    api.get_model_runtime = factory
    return meter


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
    meter = install_generation_meter(runtime, matrix["provider_generation_limit"] if args.phase == "model" else 0)
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
                if result["model_invoked"] != (len(meter.generations) > before):
                    issues.append("generation_meter_route_mismatch")
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
                emit_case(payload)
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
