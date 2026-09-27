"""Catalogue promotion and correction tests in a disposable PostgreSQL schema."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

import config
import api.edna_service as service
from db.models import CorpusBase
from ingestion.anemone_catalogue import prepare_catalogue, read_normalized_unit
from scripts import import_anemone_catalogue as importer
from tests.test_anemone_catalogue import make_archive, rewrite

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_INTEGRATION") != "1",
    reason="requires disposable PostgreSQL",
)


@pytest.fixture
def database(tmp_path, monkeypatch):
    schema = "catalogue_test_" + uuid.uuid4().hex
    admin = create_engine(config.DATABASE_URL)
    with admin.begin() as c:
        c.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        config.DATABASE_URL, connect_args={"options": f"-csearch_path={schema},public"}
    )
    CorpusBase.metadata.create_all(engine, checkfirst=False)
    monkeypatch.setattr(config, "SERVING_DIR", tmp_path / "serving")
    monkeypatch.setattr(config, "EDNA_ARTIFACT_URI", "")
    monkeypatch.setattr(service, "get_engine", lambda: engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as c:
            c.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


def state(engine):
    with engine.connect() as c:
        return {
            t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
            for t in (
                "edna_sample",
                "edna_detection",
                "retrieval_document",
                "corpus_publication",
            )
        }


def test_atomic_import_rerun_stale_generation_and_failed_derivation(
    database, tmp_path, monkeypatch
):
    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive"), work)
    before = state(database)
    result = importer.import_candidate(database, work, publish_retrieval=True)
    assert not result["committed"] and state(database) == before
    first = importer.import_candidate(
        database, work, execute=True, publish_retrieval=True
    )
    assert first["retrieval"]["documents"] == 2
    summary = service.edna_summary({})
    assert summary["source_occurrences"] == 1 and summary["assays"] == 1
    assert len(summary["methods"]) == 2
    assert summary["publication"]["anemone-canonical"]["generation_id"] == candidate["candidate_id"]
    pointer = (config.SERVING_DIR / "edna_current.json").read_bytes()
    second = importer.import_candidate(
        database,
        work,
        execute=True,
        expected_previous=candidate["candidate_id"],
        publish_retrieval=True,
    )
    assert second["retrieval"]["merge"]["unchanged"] == 2
    assert second["retrieval"]["merge"]["embedding_invalidated"] == 0
    assert (config.SERVING_DIR / "edna_current.json").read_bytes() == pointer
    before = state(database)
    with pytest.raises(ValueError, match="generation changed"):
        importer.import_candidate(database, work, execute=True)
    assert state(database) == before

    def changed(p):
        rewrite(
            p,
            "community_qc_target.tsv.xz",
            lambda lines: [lines[0], lines[1].replace("\t10\t", "\t11\t")],
        )

    # A derivative error after all canonical units have merged must roll back.
    prepare_catalogue(make_archive(tmp_path / "correction", changed), work)
    monkeypatch.setattr(
        importer,
        "_merge_documents",
        lambda *a: (_ for _ in ()).throw(RuntimeError("injected derivative failure")),
    )
    with pytest.raises(RuntimeError, match="injected"):
        importer.import_candidate(
            database,
            work,
            execute=True,
            expected_previous=candidate["candidate_id"],
            publish_retrieval=True,
        )
    assert state(database) == before
    assert (config.SERVING_DIR / "edna_current.json").read_bytes() == pointer
    with database.connect() as c:
        assert (
            c.execute(
                text(
                    "SELECT generation_id FROM corpus_publication WHERE channel='anemone-canonical'"
                )
            ).scalar()
            == candidate["candidate_id"]
        )


def test_late_unit_corruption_rolls_back_and_empty_tables_remain_queryable(
    database, tmp_path
):
    def mutate(p):
        for name in ("community_qc_target.tsv.xz", "community_qc3nn_target.tsv.xz"):
            rewrite(p, name, lambda lines: lines[:1])
        for key, data in list(p.items()):
            p[key.replace("/MiFish/ANEMONE/", "/Other/OtherTeam/")] = data

    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive", mutate), work)
    unit = candidate["units"][-1]
    path = (
        work
        / "normalized/snapshots"
        / unit["normalization_id"]
        / "normalization_manifest.json"
    )
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        importer.import_candidate(database, work, execute=True)
    assert state(database)["edna_sample"] == 0
    path.write_bytes(original)
    importer.import_candidate(database, work, execute=True, publish_retrieval=True)
    assert (
        service.edna_samples(
            {"assignment_method": "qcauto_target"}, limit=10, offset=0
        )["total"]
        == 2
    )
    assert (
        service.edna_samples(
            {"provider_locus": "Other", "target_status": "target"}, limit=10, offset=0
        )["total"]
        == 1
    )
    assert (
        service.edna_samples(
            {"assignment_method": "qcauto_nontarget"}, limit=10, offset=0
        )["total"]
        == 0
    )
    assert service.edna_samples({"taxon": "missing"}, limit=10, offset=0)["total"] == 0
    assert state(database)["retrieval_document"] == 4
    summary = service.edna_summary({"assignment_method": "qcauto_target"})
    assert summary["source_occurrences"] == 2 and summary["methods"] == []
    assert summary["community_availability"] == [{"assignment_method": "qcauto_target", "available_tables": 2, "empty_tables": 2}]


def test_matching_review_preserves_anchor_and_changed_evidence_does_not(
    database, tmp_path
):
    def unknown(p):
        rewrite(
            p,
            "sample.tsv.xz",
            lambda lines: [line for line in lines if "\tsample_type\t" not in line],
        )

    work = tmp_path / "work"
    candidate = prepare_catalogue(make_archive(tmp_path / "archive", unknown), work)
    importer.import_candidate(database, work, execute=True)
    frames, _ = read_normalized_unit(
        work / "normalized", candidate["units"][0]["normalization_id"]
    )
    sample = frames["edna_sample"].iloc[0]
    # Stand in for an already approved and applied database review. Validation
    # of review signatures is covered by the classification integration suite.
    with database.begin() as c:
        c.execute(
            text(
                "INSERT INTO anchor_event(event_id,sample_id,source_types,active) VALUES (:id,:sample,'edna_metabarcoding',TRUE)"
            ),
            {"id": "a" * 64, "sample": sample.sample_id},
        )
        c.execute(
            text(
                "UPDATE edna_sample SET classification_review_json='{}', sample_kind='environmental', is_control=FALSE, anchor_event_id=:anchor WHERE sample_id=:sample"
            ),
            {"anchor": "a" * 64, "sample": sample.sample_id},
        )
    result = importer.import_candidate(
        database, work, execute=True, expected_previous=candidate["candidate_id"]
    )
    assert result["changes"]["preserved_reviews"] == 1
    with database.connect() as c:
        assert c.execute(
            text("SELECT active FROM anchor_event WHERE event_id=:id"), {"id": "a" * 64}
        ).scalar()
        frames["external_source_file"].loc[
            frames["external_source_file"].source_file_id == sample.source_file_id,
            "sha256",
        ] = "0" * 64
        assert importer.preserve_matching_reviews(c, frames) == 0
