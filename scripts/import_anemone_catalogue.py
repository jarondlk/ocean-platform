#!/usr/bin/env python3
"""Atomically import a verified catalogue candidate into an explicit database.

No database URL is inherited implicitly. Default is a transactional dry run.
Missing catalogue paths are never treated as approved provider withdrawals.
"""

from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from sqlalchemy import create_engine, text
from ingestion.anemone_catalogue import file_sha256, read_normalized_unit
from scripts.load_db import _upsert_anemone_bundle
from ingestion.immutable_bundle import digest, validate_id
from retrieval.edna_materializer import (
    collect_active_documents,
    _document_frame,
    _merge_documents,
    bind_canonical_publication,
    _write_artifacts,
)
from retrieval.edna_publication import set_pending, set_ready, restore_pending


def preserve_matching_reviews(connection, frames):
    """Retain exact reviewed sample evidence; do not rebase signed attestations."""
    sample_frame = frames["edna_sample"]
    existing = (
        connection.execute(
            text(
                "SELECT s.*, f.sha256 AS reviewed_source_sha FROM edna_sample s "
                "JOIN external_source_file f ON f.source_file_id=s.source_file_id "
                "WHERE s.sample_id = ANY(:ids) AND s.classification_review_json IS NOT NULL"
            ),
            {"ids": sample_frame["sample_id"].tolist()},
        )
        .mappings()
        .all()
    )
    files = (
        frames["external_source_file"].set_index("source_file_id")["sha256"].to_dict()
    )
    old = {r["sample_id"]: dict(r) for r in existing}
    preserved = 0
    anchors = []
    rows = []
    for row in sample_frame.to_dict("records"):
        prior = old.get(row["sample_id"])
        if (
            prior
            and row["sample_kind"] == "unknown"
            and not row.get("provider_note_json")
            and files[row["source_file_id"]] == prior.get("reviewed_source_sha")
        ):
            # Leave source_snapshot_id, review signature and scientific hash
            # together. New assays/detections may cite the new acquisition.
            row = {k: v for k, v in prior.items() if k != "reviewed_source_sha"}
            if row.get("anchor_event_id"):
                anchors.append(row["anchor_event_id"])
            row["active"] = True
            preserved += 1
        rows.append(row)
    frames["edna_sample"] = pd.DataFrame(rows)
    if anchors:
        retained = pd.read_sql_query(
            text(
                "SELECT * FROM anchor_event WHERE event_id = ANY(:ids) AND active IS TRUE"
            ),
            connection,
            params={"ids": anchors},
        )
        if len(retained) != len(set(anchors)):
            raise ValueError("Reviewed sample anchor is missing")
        frames["edna_anchor_event"] = pd.concat(
            [frames["edna_anchor_event"], retained], ignore_index=True
        ).drop_duplicates("event_id")
    return preserved


def import_candidate(
    engine,
    work: Path,
    *,
    execute=False,
    expected_previous=None,
    progress=None,
    publish_retrieval=False,
):
    pointer = json.loads((work / "candidate.json").read_text())
    path = work / "candidates" / validate_id(pointer["candidate_id"]) / "candidate.json"
    if file_sha256(path) != pointer["manifest_sha256"]:
        raise ValueError("Candidate pointer integrity mismatch")
    candidate = json.loads(path.read_text())
    if candidate["status"] != "complete" or candidate["failures"]:
        raise ValueError("Only complete candidates can be imported")
    totals, changes = Counter(), Counter()
    seen = set()
    artifacts, retrieval = {}, None
    pending, committed, previous_pointer = False, False, None
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "SELECT pg_advisory_lock(hashtext('ocean_platform_corpus_upsert'))"
        )
        connection.commit()
        transaction = connection.begin()
        try:
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock(hashtext('ocean_platform_corpus_upsert'))"
                )
            )
            previous = connection.execute(
                text(
                    "SELECT generation_id FROM corpus_publication WHERE channel='anemone-canonical'"
                )
            ).scalar()
            if previous != expected_previous:
                raise ValueError(
                    "Canonical generation changed; supply the observed previous generation explicitly"
                )
            for index, unit in enumerate(candidate["units"], 1):
                root = work / "normalized" / "snapshots" / validate_id(unit["normalization_id"])
                if (
                    file_sha256(root / "normalization_manifest.json")
                    != unit["manifest_sha256"]
                ):
                    raise ValueError("Candidate unit manifest checksum mismatch")
                frames, manifest = read_normalized_unit(
                    work / "normalized", unit["normalization_id"]
                )
                ids = set(frames["edna_sample"]["sample_id"])
                if ids & seen:
                    raise ValueError("Duplicate source occurrence in candidate")
                seen.update(ids)
                totals.update({k: len(v) for k, v in frames.items()})
                changes["preserved_reviews"] += preserve_matching_reviews(
                    connection, frames
                )
                tables, inactive = _upsert_anemone_bundle(
                    connection, frames=frames, manifest=manifest
                )
                for table, result in tables.items():
                    changes[table + "_inserted"] += result.get("inserted", 0)
                    changes[table + "_updated"] += result.get("updated", 0)
                for table, count in inactive.items():
                    changes[table + "_inactivated"] += count
                if progress:
                    progress(
                        {
                            "imported_units": index,
                            "total_units": len(candidate["units"]),
                        }
                    )
            if (
                dict(totals) != candidate["row_counts"]
                or len(seen) != candidate["source_occurrences"]
            ):
                raise ValueError("Imported candidate row accounting mismatch")
            connection.execute(
                text(
                    "INSERT INTO corpus_publication (channel,generation_id,manifest_sha256) VALUES ('anemone-canonical',:generation,:sha) ON CONFLICT (channel) DO UPDATE SET generation_id=EXCLUDED.generation_id,manifest_sha256=EXCLUDED.manifest_sha256"
                ),
                {
                    "generation": candidate["candidate_id"],
                    "sha": pointer["manifest_sha256"],
                },
            )
            if publish_retrieval:
                documents, _ = collect_active_documents(connection)
                frame = _document_frame(documents)
                retrieval = {"documents": len(documents)}
                if execute:
                    artifacts = _write_artifacts(documents, frame, publish=False)
                    retrieval["merge"] = _merge_documents(connection, frame)
                    manifest = artifacts["manifest"]
                    connection.execute(
                        text(
                            "INSERT INTO corpus_publication (channel,generation_id,manifest_sha256) VALUES ('edna',:generation,:sha) ON CONFLICT (channel) DO UPDATE SET generation_id=EXCLUDED.generation_id,manifest_sha256=EXCLUDED.manifest_sha256"
                        ),
                        {"generation": manifest["id"], "sha": digest(manifest)},
                    )
                    bind_canonical_publication(connection)
                    previous_pointer = set_pending()
                    pending = True
            if execute:
                transaction.commit()
                committed = True
                if artifacts:
                    set_ready(artifacts["manifest"])
            else:
                transaction.rollback()
        except BaseException:
            if transaction.is_active:
                transaction.rollback()
            if pending and not committed:
                restore_pending(previous_pointer)
            raise
        finally:
            connection.rollback()
            connection.exec_driver_sql(
                "SELECT pg_advisory_unlock(hashtext('ocean_platform_corpus_upsert'))"
            )
            connection.commit()
    return {
        "candidate_id": candidate["candidate_id"],
        "committed": execute,
        "row_counts": dict(totals),
        "changes": dict(changes),
        "withdrawals_applied": False,
        "retrieval": retrieval,
        "artifacts": artifacts,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--expected-previous")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--publish-retrieval",
        action="store_true",
        help="Commit canonical rows and full retrieval corpus together; requires an explicitly isolated DATA_DIR or configured artifact store",
    )
    args = parser.parse_args()
    result = import_candidate(
        create_engine(args.database_url),
        args.work_dir,
        execute=args.execute,
        expected_previous=args.expected_previous,
        publish_retrieval=args.publish_retrieval,
        progress=lambda r: print(json.dumps(r), flush=True),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
