from __future__ import annotations

import importlib
import json
import sys

import pandas as pd


def test_source_row_hash_is_stable_and_content_sensitive():
    load_db = importlib.import_module("scripts.load_db")
    frame = pd.DataFrame(
        [
            {
                "sample_id": "2024-01-O-s1",
                "temperature": 12.3,
                "observed_at": pd.Timestamp("2024-01-18"),
            }
        ]
    )

    first = load_db.add_source_row_hash(frame)
    second = load_db.add_source_row_hash(frame.copy())
    changed = load_db.add_source_row_hash(
        frame.assign(temperature=12.4)
    )

    assert first.loc[0, "source_row_hash"] == second.loc[0, "source_row_hash"]
    assert len(first.loc[0, "source_row_hash"]) == 64
    assert first.loc[0, "source_row_hash"] != changed.loc[0, "source_row_hash"]


def test_upsert_counts_do_not_double_count_replaced_rows():
    load_db = importlib.import_module("scripts.load_db")

    counts = load_db._upsert_count_summary(
        matched=82,
        replaced=82,
        inserted_after_delete=85,
    )

    assert counts == {
        "updated": 82,
        "inserted": 3,
        "unchanged": 0,
    }


def test_upsert_counts_reject_inconsistent_database_results():
    load_db = importlib.import_module("scripts.load_db")

    try:
        load_db._upsert_count_summary(
            matched=1,
            replaced=2,
            inserted_after_delete=2,
        )
    except RuntimeError as exc:
        assert "inconsistent row counts" in str(exc)
    else:
        raise AssertionError("Inconsistent upsert counts were accepted")


def test_mutating_upsert_cli_delegates_to_transactional_loader(
    monkeypatch,
    capsys,
):
    load_db = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(
        load_db,
        "upsert_corpus",
        lambda: {
            "mode": "upsert",
            "incoming_rows": 3,
            "inserted_rows": 1,
            "updated_rows": 1,
            "unchanged_rows": 1,
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["load_db.py", "--upsert", "--json"],
    )

    load_db.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "upsert"
    assert payload["inserted_rows"] == 1


def test_database_loader_requires_explicit_safe_mutation_mode(
    monkeypatch,
):
    load_db = importlib.import_module("scripts.load_db")
    monkeypatch.setattr(sys, "argv", ["load_db.py"])

    try:
        load_db.main()
    except SystemExit as exc:
        assert "Choose a safe database mutation mode" in str(exc)
    else:
        raise AssertionError("Unsafe implicit append mode was accepted")
