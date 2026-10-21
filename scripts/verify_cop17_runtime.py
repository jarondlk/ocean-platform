#!/usr/bin/env python3
"""Run real-data COP17 acceptance inside an authorized demo QA job.

Requires the disposable cop17-isolated-qa viewer and demo runtime secrets.
Does not create users, modify scientific rows, or replace browser OAuth QA.
COP17_QA_SECTION may be all (default), published, or free-text.
"""

import json
import os
import time
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
import jwt
from sqlalchemy.engine import make_url


def guard_demo():
    url = make_url(os.environ["DATABASE_URL"])
    if (
        url.database != "ocean_cop17"
        or url.query.get("host")
        != "/cloudsql/data-infra-infobio:asia-northeast1:ocean-cop17-postgres"
    ):
        raise RuntimeError("Only the fixed isolated demo database is allowed")
    if (
        os.environ.get("COP17_DEMO_ENABLED", "").lower() != "true"
        or os.environ.get("EDNA_ARTIFACT_URI")
        != "gs://data-infra-infobio-ocean-cop17/edna-cop17-snapshot"
    ):
        raise RuntimeError(
            "Only the isolated COP17 profile and artifact store are allowed"
        )


guard_demo()
if "__file__" in globals():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
import api.main as api
from orchestration.research_intents import QUESTIONS
from ingestion.edna_analysis_bundle import load_analysis
from ingestion.immutable_bundle import digest
from db.connection import get_session
from db.app_models import AppUser
import uuid

with get_session() as session:
    actor = session.get(AppUser, uuid.UUID("cccccccc-1717-4171-8171-171717171717"))
    if actor is None or (actor.email, actor.auth_subject, actor.role, actor.status) != (
        "cop17-qa@example.invalid",
        "cop17-isolated-qa",
        "viewer",
        "active",
    ):
        raise RuntimeError("The disposable QA viewer must be explicitly prepared first")
section = os.environ.get("COP17_QA_SECTION", "all")
if section not in {"all", "published", "free-text"}:
    raise ValueError("Unknown QA section")
client = TestClient(api.app)


def headers():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "cop17-isolated-qa",
            "provider": "google",
            "email": "cop17-qa@example.invalid",
            "email_verified": True,
            "iss": "ocean-platform-frontend",
            "aud": "ocean-platform-api",
            "iat": now,
            "exp": now + timedelta(seconds=60),
        },
        os.environ["INTERNAL_AUTH_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": "Bearer " + token}


assert client.get("/chat/analysis-options").status_code == 401
assert client.get("/pipeline/status", headers=headers()).status_code == 403
r = client.get("/chat/analysis-options", headers=headers())
assert r.status_code == 200, r.text
options = r.json()["options"]
choices = [
    o
    for o in options
    if o["status"] == "current"
    and o["analysis_kind"] == "regional_frequency"
    and o["assignment_methods"] == ["qcauto_95pct_3nn_target"]
]
assert len(choices) == 1, [(o["analysis_id"], o["status"]) for o in options]
option = choices[0]
protocols = [
    p
    for p, v in option["protocols"].items()
    if str(v.get("sequencing_method")).lower() == "miseq"
    and str(v.get("library_layout")).lower() == "paired"
]
assert len(protocols) == 1
protocol = protocols[0]
E3 = "Which fish species were most frequently detected along the Miyagi coast from 2020 to 2023? Show the top 10, including the denominators and yearly changes."
E4 = "Compare fish eDNA detection frequencies under high and low sea surface temperatures in Miyagi. Show a representative time series and cite the datasets."
report = {
    "analysis_id": option["analysis_id"],
    "protocol_id": protocol,
    "cases": [],
    "auth_boundaries": "anonymous 401; viewer admin 403",
}


def ask(name, query, kind=None, *, sst=True, enabled=True, analysis=True, filters=None):
    scope = {
        "version": 1,
        "sources": {
            f: {"enabled": False, "filters": {}}
            for f in ["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"]
        },
    }
    scope["sources"]["edna_metabarcoding"] = {
        "enabled": enabled,
        "filters": filters or {},
    }
    if analysis:
        scope["sources"]["edna_metabarcoding"]["analysis_id"] = option["analysis_id"]
    scope["sources"]["remote_sensing"] = {
        "enabled": sst,
        "filters": {"dataset_id": "mur-miyagi-2020-2023"} if sst and analysis else {},
    }
    payload = {"query": query, "settings_mode": "manual", "evidence_scope": scope}
    if kind:
        payload["research_intent"] = {"kind": kind, "protocol_id": protocol}
    start = time.perf_counter()
    response = client.post("/chat", json=payload, headers=headers())
    elapsed = round(time.perf_counter() - start, 3)
    assert response.status_code == 200, (
        name,
        response.status_code,
        response.text[:1000],
    )
    body = response.json()
    item = {
        "name": name,
        "seconds": elapsed,
        "outcome": body.get("outcome"),
        "reason": body.get("abstention_reason"),
        "model_invoked": body.get("model_invoked"),
        "primary_sources": body.get("n_sources"),
        "interaction_id": body.get("interaction_id"),
    }
    report["cases"].append(item)
    print(json.dumps(item), flush=True)
    if body.get("outcome") == "answered":
        assert body["answer_audit"]["invalid_citation_count"] == 0
    return body


def packet(body):
    return [
        (d["doc_id"], d.get("table"), d.get("result_rows"))
        for d in body.get("analysis_context", [])
    ]


if section in {"all", "published"}:
    for kind, letter, varied in [
        ("fish_frequency", "E3", E3),
        ("temperature_comparison", "E4", E4),
    ]:
        a = ask(letter + "-A", QUESTIONS[kind][0], kind, sst=kind != "fish_frequency")
        b = ask(letter + "-B", varied, kind, sst=kind != "fish_frequency")
        assert (
            a["outcome"] == b["outcome"] == "answered"
            and not a["model_invoked"]
            and not b["model_invoked"]
        )
        assert packet(a) == packet(b), "Exact professor row/citation parity failed"
        for body in [a, b]:
            assert body["answer_audit"]["invalid_citation_count"] == 0
        ja = ask(
            letter + "-JA", QUESTIONS[kind][-1], kind, sst=kind != "fish_frequency"
        )
        assert ja["outcome"] == "answered" and packet(ja) == packet(a)
        assert all(d.get("display_language") == "ja" for d in ja["analysis_context"])
    wrong = ask("wrong-year", E3.replace("2023", "2024"), "fish_frequency", sst=False)
    assert wrong["outcome"] == "abstained" and not wrong["model_invoked"]
    off = ask("sst-disabled", E4, "temperature_comparison", sst=False)
    assert off["outcome"] == "abstained" and not off["model_invoked"]
if section in {"all", "free-text"}:
    bundle = load_analysis(option["analysis_id"])
    sample = bundle["inputs"]["canonical"]["edna_sample"][0]["sample_id"]
    for name, question in [
        (
            "free-text-EN",
            f"What taxa are recorded in the ANEMONE eDNA evidence for sample {sample}. Explain the limitations of this evidence.",
        ),
        (
            "free-text-JA",
            f"ANEMONEのサンプル {sample} の環境DNA記録を要約し、記録された分類群と制約を説明してください。",
        ),
    ]:
        body = ask(
            name, question, sst=False, analysis=False, filters={"sample_id": sample}
        )
        assert body["n_sources"] > 0 and body["outcome"] == "answered", (
            name,
            body.get("answer"),
        )
report["section"] = section
if section in {"all", "published"}:
    report["exact_professor_parity"] = True
    report["scientific_scope_rejections"] = True
    report["evidence_row_hashes"] = {
        d["table"]: digest(d["result_rows"]) for d in a["analysis_context"]
    }
if section in {"all", "free-text"}:
    report["bilingual_free_text"] = True
print(
    json.dumps({"cop17_acceptance_passed": True, **report}, ensure_ascii=False),
    flush=True,
)
