from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import orchestration.query_orchestrator as orchestrator


def test_provenance_prompt_contains_primary_and_linked_citations():
    evidence = orchestrator.EvidenceBundle(
        query="temperature",
        primary_results=[
            {
                "doc_id": "ctd-1",
                "source_type": "ctd",
                "time": "2024-01-18",
                "text": "Surface temperature was 12.3 C.",
            }
        ],
        linked_evidence=[
            {
                "doc_id": "sst-1",
                "source_type": "remote_sensing",
                "link_type": "same_day",
                "text": "Satellite SST was 12.1 C.",
            }
        ],
        source_types_found=["ctd", "remote_sensing"],
    )

    prompt = orchestrator.build_provenance_prompt(
        "What was the temperature?",
        evidence,
    )

    assert "[ctd-1]" in prompt
    assert "[sst-1]" in prompt
    assert "ONLY use the evidence" in prompt
    assert "<user_question>What was the temperature?</user_question>" in prompt


def test_query_pipeline_packages_results_and_metadata(monkeypatch):
    import retrieval.hybrid_retriever as hybrid

    monkeypatch.setattr(
        hybrid,
        "hybrid_search",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                doc_id="ctd-1",
                source_type="ctd",
                sample_id="2024-01-O-s1",
                event_id="event-1",
                time="2024-01-18",
                bay="O",
                station="s1",
                title="CTD",
                text="temperature",
                score=0.9,
            ),
            SimpleNamespace(
                doc_id="sst-1",
                source_type="remote_sensing",
                sample_id=None,
                event_id="event-2",
                time="2024-01-19",
                bay="O",
                station=None,
                title="SST",
                text="sst",
                score=0.8,
            ),
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "expand_evidence",
        lambda _rows: [{"doc_id": "linked-1"}],
    )

    bundle = orchestrator.query_pipeline("temperature")

    assert len(bundle.primary_results) == 2
    assert bundle.linked_evidence == [{"doc_id": "linked-1"}]
    assert set(bundle.source_types_found) == {"ctd", "remote_sensing"}
    assert bundle.bays_found == ["O"]
    assert bundle.time_range == "2024-01-18 to 2024-01-19"


def test_expand_evidence_uses_bound_event_ids(monkeypatch):
    captured = {}
    row = SimpleNamespace(
        doc_id="linked-1",
        source_type="remote_sensing",
        sample_id=None,
        event_id="event-2",
        time="2024-01-19",
        bay="O",
        station=None,
        title="SST",
        text="sst",
        link_type="same_day",
    )

    class Result:
        def fetchall(self):
            return [row]

    class Session:
        def execute(self, statement, params):
            captured["statement"] = str(statement)
            captured["params"] = params
            return Result()

    @contextmanager
    def fake_session():
        yield Session()

    monkeypatch.setattr(orchestrator, "get_session", fake_session)
    linked = orchestrator.expand_evidence(
        [
            {
                "doc_id": "primary-1",
                "event_id": "event-1' OR 1=1 --",
            }
        ]
    )

    assert linked[0]["doc_id"] == "linked-1"
    assert "event-1' OR 1=1 --" not in captured["statement"]
    assert captured["params"]["eid_0"] == "event-1' OR 1=1 --"


def test_expand_evidence_short_circuits_without_event_ids():
    assert orchestrator.expand_evidence([]) == []
    assert orchestrator.expand_evidence([{"doc_id": "only"}]) == []
