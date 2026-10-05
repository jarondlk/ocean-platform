import json

import pytest

from ingestion.anemone_catalogue import file_sha256, prepare_catalogue
from ingestion.research_readiness import build_readiness, read_candidate_metadata
from tests.test_anemone_catalogue import make_archive


@pytest.fixture
def candidate(tmp_path):
    root = tmp_path / "candidate"
    prepare_catalogue(make_archive(tmp_path / "archive"), root)
    return root


def rewrite_candidate(root, change):
    pointer_path = root / "candidate.json"
    pointer = json.loads(pointer_path.read_text())
    path = root / "candidates" / pointer["candidate_id"] / "candidate.json"
    payload = json.loads(path.read_text())
    change(payload)
    path.write_text(json.dumps(payload))
    pointer["manifest_sha256"] = file_sha256(path)
    pointer_path.write_text(json.dumps(pointer))


def test_verified_census_is_repeatable_and_does_not_write_candidate(candidate):
    before = {
        str(p.relative_to(candidate)): file_sha256(p)
        for p in candidate.rglob("*")
        if p.is_file()
    }
    source, provenance = read_candidate_metadata(candidate)
    first = build_readiness(source, provenance)
    second = build_readiness(*read_candidate_metadata(candidate))
    assert first == second
    assert first["counts"]["source_occurrences"] == 1
    assert first["source"]["row_counts"]["edna_detection"] == 2
    assert all(c["status"] == "data_blocked" for c in first["case_dispositions"])
    assert before == {
        str(p.relative_to(candidate)): file_sha256(p)
        for p in candidate.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda c: c["units"].append(c["units"][0]), "Duplicate normalized unit"),
        (lambda c: c["row_counts"].update(edna_sample=500), "do not reconcile"),
        (lambda c: c.update(status="quarantined"), "not a complete"),
        (
            lambda c: c["units"][0].update(manifest_sha256="0" * 64),
            "unit manifest checksum",
        ),
    ],
)
def test_manifest_conflicts_fail_closed(candidate, mutation, message):
    rewrite_candidate(candidate, mutation)
    with pytest.raises(ValueError, match=message):
        read_candidate_metadata(candidate)


def test_pointer_and_symlink_are_rejected(candidate, tmp_path):
    link = tmp_path / "alias"
    link.symlink_to(candidate, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        read_candidate_metadata(link)
    pointer = candidate / "candidate.json"
    data = json.loads(pointer.read_text())
    data["manifest_sha256"] = "0" * 64
    pointer.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Candidate manifest checksum"):
        read_candidate_metadata(candidate)
