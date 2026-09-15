"""Bounded QA against real retrieval/model, with isolated in-memory chat history.

Run inside the configured application environment. Production PostgreSQL is
forced read-only; only ephemeral SQLite records are written. The caller supplies
candidate code in an ephemeral job filesystem, not a service deployment.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import config
from db.connection import get_engine
from db.app_models import AppBase, AppUser, ChatInteraction
from api.auth import current_user_from_model
import api.chat_records as records
import api.main as api
from api.schemas import ChatRequest
from model_runtime import get_model_runtime, _finish_reason


def main():
    engine = get_engine()

    @event.listens_for(engine, "connect")
    def read_only(connection, _record):
        cursor = connection.cursor()
        cursor.execute("SET default_transaction_read_only = on")
        cursor.close()

    isolated = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AppBase.metadata.create_all(isolated)
    factory = sessionmaker(bind=isolated, expire_on_commit=False)

    @contextmanager
    def qa_session():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    records.get_session = qa_session
    with qa_session() as session:
        account = AppUser(
            id=uuid.uuid4(),
            auth_provider="qa-isolated",
            auth_subject="chat-system-qa",
            email="qa@example.invalid",
            role="researcher",
            account_type="internal",
            status="active",
        )
        session.add(account)
        user = current_user_from_model(account)

    rebuilt_edna_count = None
    if os.environ.get('QA_REFRESH_EDNA') == '1':
        # Preview the planned retrieval refresh without writing production rows.
        import pandas as pd
        from sqlalchemy import text
        from retrieval.edna_document_builder import build_edna_documents
        from retrieval.edna_materializer import _read_active_frames
        with engine.connect() as connection:
            frames = _read_active_frames(connection)
            standards = pd.read_sql_query(text("SELECT * FROM edna_internal_standard WHERE active IS TRUE ORDER BY internal_standard_id LIMIT 10001"), connection)
        if len(standards) > 10000:
            raise ValueError('QA standard row limit exceeded')
        rebuilt = {document.doc_id: document for document in build_edna_documents(*frames, standards)}
        rebuilt_edna_count = len(rebuilt)
        original_retrieve = api.retrieve_with_expansion
        def refreshed_retrieve(*args, **kwargs):
            bundle = original_retrieve(*args, **kwargs)
            for role in ('primary', 'linked'):
                bundle[role] = [{**row, 'text': rebuilt[row['doc_id']].text,
                                'metadata': rebuilt[row['doc_id']].metadata}
                               if row.get('doc_id') in rebuilt else row for row in bundle.get(role, [])]
            return bundle
        api.retrieve_with_expansion = refreshed_retrieve

    runtime = get_model_runtime()
    client = runtime._client()
    original_generate = client.models.generate_content
    observed = []

    def observe(**kwargs):
        response = original_generate(**kwargs)
        usage = response.usage_metadata
        observed.append(
            {
                "finish_reason": _finish_reason(response),
                "output_tokens": getattr(usage, "candidates_token_count", None),
                "prompt_tokens": getattr(usage, "prompt_token_count", None),
                "raw_answer": response.text
                if os.environ.get("QA_CAPTURE_RAW") == "1"
                and _finish_reason(response) == "STOP"
                else None,
            }
        )
        return response

    client.models.generate_content = observe
    api.get_model_runtime = lambda: runtime
    matrix = json.loads(Path("evaluation/qa/issue59_v045.json").read_text())
    cases = list(matrix["cases"])
    for original in ("original", "mixed_sources", "legacy_context", "controls"):
        base = next(c for c in cases if c["id"] == original)
        for repeat in range(2, int(os.environ.get("QA_REPEATS", "3")) + 1):
            cases.append({**base, "id": f"{original}_repeat_{repeat}"})
    cases.extend(
        [
            {
                "id": "empty_ctd_context",
                "query": "Summarize CTD seasonal temperature trends and satellite SST agreement in this date range.",
                "options": {
                    "source_type": "ctd",
                    "time_from": "2099-01-01",
                    "time_to": "2099-12-31",
                },
                "expect": "No historical context should answer as if it matched the explicit empty 2099 scope.",
            },
            {
                "id": "japanese_edna",
                "query": "利用可能なANEMONE MiFish試料はいくつありますか。試料数と解析手法の数を区別し、採取日と場所を出典付きで教えてください。",
                "options": {"source_type": "edna_metabarcoding"},
                "expect": "One physical sample, two methods, supported date and coordinates, valid citations.",
            },
            {
                "id": "leading_abundance",
                "query": "Since both MiFish methods have 9,635 reads, can I report 19,270 fish and say their agreement independently proves there was no contamination?",
                "options": {"source_type": "edna_metabarcoding"},
                "expect": "Reject summed organism counts, independent validation and contamination-free inference.",
            },
        ]
    )
    if os.environ.get("QA_CITATION_DIAGNOSTIC") == "1":
        selected = [
            c
            for c in matrix["cases"]
            if c["id"] in {"original", "legacy_context", "mixed_sources"}
        ]
        cases = [
            {**c, "id": f"{c['id']}_diagnostic_{i}"}
            for i in (1, 2, 3)
            for c in selected
        ]
    manifest = {
        "date": "2026-09-15",
        "version": api.app.version,
        "model": config.CHAT_MODEL,
        "cap": config.CHAT_MAX_OUTPUT_TOKENS,
        "cases": len(cases),
        "history": "isolated SQLite",
        "corpus": "production PostgreSQL read-only",
        "rebuilt_edna_documents": rebuilt_edna_count,
        "edna_refresh": "in-memory preview; retrieval ranking and production embeddings unchanged" if rebuilt_edna_count is not None else "not applied",
        "source_sha256": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in [
                "orchestration/citations.py",
                "orchestration/citation_syntax.py",
                "orchestration/evidence_scope.py",
                "orchestration/answer_audit.py",
                "retrieval/edna_document_builder.py",
                "api/schemas.py",
                "api/chat_records.py",
                "orchestration/unified.py",
                "api/main.py",
                "model_runtime.py",
            ]
        },
    }
    print("CHAT_QA_MANIFEST=" + json.dumps(manifest), flush=True)
    for case in cases:
        observed.clear()
        start = time.monotonic()
        result = {"id": case["id"], "query": case["query"], "expect": case["expect"]}
        request = ChatRequest(
            **{**matrix["defaults"], **case["options"], "query": case["query"]}
        )
        result["request"] = request.model_dump(mode="json", exclude_none=True)
        try:
            response = api.chat(request, user=user)
            payload = response.model_dump(mode="json")
            result.update(http_status=200, response=payload)
        except HTTPException as exc:
            result.update(http_status=exc.status_code, error=exc.detail)
        except Exception as exc:
            result.update(
                http_status=500, error={"type": type(exc).__name__, "message": str(exc)}
            )
        with qa_session() as session:
            record = session.scalars(
                select(ChatInteraction).order_by(ChatInteraction.created_at.desc())
            ).first()
            if record and record.query == case["query"]:
                result["history"] = {
                    k: getattr(record, k)
                    for k in [
                        "status",
                        "outcome",
                        "error_code",
                        "answer",
                        "prompt_sha256",
                        "corpus_fingerprint",
                        "prompt_version",
                        "request_options",
                        "evidence_snapshot",
                    ]
                }
        result.update(
            generations=list(observed), seconds=round(time.monotonic() - start, 3)
        )
        print(
            "CHAT_QA_RESULT="
            + json.dumps(records.json_safe(result), ensure_ascii=False),
            flush=True,
        )
    print("CHAT_QA_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
