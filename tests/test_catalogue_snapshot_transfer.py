"""Synthetic copy acceptance: exact bytes, current eligibility and honest isolation."""

from copy import deepcopy
import hashlib
import json

import pytest

from ingestion.catalogue_snapshot import LocalCatalogueSnapshotStore
from ingestion.catalogue_snapshot_fixtures import FIXTURE_ROWS, fixture_snapshot
from ingestion.catalogue_snapshot_transfer import (
    TransferRejected,
    build_transfer,
    import_quarantined,
    transfer_id,
)
from schema.catalogue_snapshot import manifest_id, validated_manifest


def copy_fixture(rows=None):
    snapshot, contents = fixture_snapshot(rows=rows)
    manifest = build_transfer(
        snapshot,
        contents,
        destination_id="v1-synthetic-site",
        authorization_ref="synthetic-approved-transfer",
        origin_system="synthetic-origin",
        qualifications={
            key: (
                "Synthetic descriptive fixture; not scientific approval",
                "Synthetic permitted cohort only",
            )
            for key in contents
        },
        encodings={key: "json-rows-v1" for key in contents},
    )
    return snapshot, contents, manifest


def imported(tmp_path, manifest, contents, **overrides):
    store = overrides.pop(
        "store",
        LocalCatalogueSnapshotStore(
            root=tmp_path / "store", access_gate=lambda value: True
        ),
    )
    result = import_quarantined(
        manifest,
        contents,
        destination_id="v1-synthetic-site",
        store=store,
        quarantine_root=tmp_path / "quarantine",
        authorize=lambda value: True,
        eligible=lambda obj, origin: True,
        **overrides,
    )
    return store, result


def test_valid_copy_is_independent_exact_and_never_promotes_latest(tmp_path):
    source, contents, manifest = copy_fixture()
    original = deepcopy(manifest.model_dump(mode="json"))
    store, result = imported(tmp_path, manifest, contents)
    restored, actual = store.read(result.snapshot_id)
    assert actual == contents
    assert manifest_id(source) == result.source_snapshot_id
    assert result.snapshot_id != result.source_snapshot_id
    assert result.object_count == 8
    assert dict(result.row_counts) == {
        key: len(json.loads(data)) for key, data in contents.items()
    }
    assert store.latest() == (None, 0) and result.latest_promoted is False
    assert manifest.model_dump(mode="json") == original
    assert all(
        obj.provenance.origin.source_snapshot_id == result.source_snapshot_id
        for obj in restored.objects
    )
    assert all(
        obj.provenance.origin.live_dependency is False for obj in restored.objects
    )
    assert list((tmp_path / "quarantine").iterdir()) == []
    # Current withdrawal denies the independent copy; no legacy lookup occurs.
    store.revoke(result.snapshot_id)
    with pytest.raises(PermissionError):
        store.read(result.snapshot_id)


def test_transfer_identity_and_replay_are_deterministic(tmp_path):
    source, contents, manifest = copy_fixture()
    reordered = manifest.model_dump(mode="json")
    reordered["objects"].reverse()
    reordered["snapshot"]["objects"].reverse()
    reordered["snapshot"]["source_captures"].reverse()
    assert transfer_id(reordered) == transfer_id(manifest)
    store, result = imported(tmp_path, manifest, contents)
    second = import_quarantined(
        reordered,
        contents,
        destination_id="v1-synthetic-site",
        store=store,
        quarantine_root=tmp_path / "quarantine",
        authorize=lambda value: True,
        eligible=lambda obj, origin: True,
    )
    assert result == second and store.latest() == (None, 0)


def test_shared_hashes_and_exact_zero_rows_do_not_collide(tmp_path):
    rows = {
        family: {role: [] for role in tables} for family, tables in FIXTURE_ROWS.items()
    }
    _, contents, manifest = copy_fixture(rows)
    assert len({hashlib.sha256(data).hexdigest() for data in contents.values()}) == 1
    store, result = imported(tmp_path, manifest, contents)
    assert set(dict(result.row_counts).values()) == {0}
    assert store.read(result.snapshot_id)[1] == contents


@pytest.mark.parametrize(
    "failure",
    [
        "destination",
        "authorization",
        "eligibility",
        "target-policy",
        "bytes",
        "missing",
        "extra",
        "count",
        "origin",
        "source-id",
        "live-dependency",
        "unknown-version",
    ],
)
def test_rejected_copies_never_seal_or_publish(tmp_path, failure):
    _, contents, manifest = copy_fixture()
    value = manifest.model_dump(mode="json")
    supplied = dict(contents)
    key = next(iter(contents))

    def authorize(value):
        return failure != "authorization"

    def eligible(obj, origin):
        return failure != "eligibility"

    if failure == "destination":
        value["destination_id"] = "legacy-site"
    elif failure in {"authorization", "eligibility", "target-policy"}:
        pass
    elif failure == "bytes":
        supplied[key] += b" "
    elif failure == "missing":
        supplied.pop(key)
    elif failure == "extra":
        supplied["private-unregistered"] = b"[]"
    elif failure == "count":
        value["objects"][0]["row_count"] += 1
    elif failure == "origin":
        value["objects"][0]["origin"]["content_sha256"] = "f" * 64
    elif failure == "source-id":
        value["source_snapshot_id"] = "f" * 64
    elif failure == "live-dependency":
        value["objects"][0]["origin"]["live_dependency"] = True
    elif failure == "unknown-version":
        value["schema_version"] = "catalogue-transfer-v2"
    store = LocalCatalogueSnapshotStore(
        root=tmp_path / "store", access_gate=lambda value: failure != "target-policy"
    )
    with pytest.raises((ValueError, PermissionError)):
        import_quarantined(
            value,
            supplied,
            destination_id="v1-synthetic-site",
            store=store,
            quarantine_root=tmp_path / "quarantine",
            authorize=authorize,
            eligible=eligible,
        )
    assert store.latest() == (None, 0)
    assert store.lifecycle()["snapshots"] == {}
    assert (
        not (tmp_path / "quarantine").exists()
        or list((tmp_path / "quarantine").iterdir()) == []
    )


@pytest.mark.parametrize("gate", ["authorization", "eligibility"])
def test_current_gates_are_rechecked_after_quarantine(tmp_path, gate):
    _, contents, manifest = copy_fixture()
    calls = [0]

    def authorize(value):
        if gate == "authorization":
            calls[0] += 1
            return calls[0] == 1
        return True

    def eligible(obj, origin):
        if gate == "eligibility":
            calls[0] += 1
            return calls[0] <= len(contents)
        return True

    store = LocalCatalogueSnapshotStore(
        root=tmp_path / "store", access_gate=lambda value: True
    )
    with pytest.raises(TransferRejected):
        import_quarantined(
            manifest,
            contents,
            destination_id="v1-synthetic-site",
            store=store,
            quarantine_root=tmp_path / "quarantine",
            authorize=authorize,
            eligible=eligible,
        )
    assert store.lifecycle()["snapshots"] == {}
    assert list((tmp_path / "quarantine").iterdir()) == []


def test_callbacks_cannot_mutate_the_bound_transfer(tmp_path):
    _, contents, manifest = copy_fixture()
    before = manifest.model_dump(mode="json")

    def authorize(copy):
        copy.snapshot.objects[0].sha256 = "f" * 64
        return True

    def eligible(obj, origin):
        obj.sha256 = "f" * 64
        origin.content_sha256 = "f" * 64
        return True

    store = LocalCatalogueSnapshotStore(
        root=tmp_path / "store", access_gate=lambda value: True
    )
    result = import_quarantined(
        manifest,
        contents,
        destination_id="v1-synthetic-site",
        store=store,
        quarantine_root=tmp_path / "quarantine",
        authorize=authorize,
        eligible=eligible,
    )
    assert store.read(result.snapshot_id)[1] == contents
    assert manifest.model_dump(mode="json") == before


def test_chained_copy_rejected_instead_of_overwriting_original_origin(tmp_path):
    _, contents, manifest = copy_fixture()
    store, result = imported(tmp_path, manifest, contents)
    snapshot, contents = store.read(result.snapshot_id)
    with pytest.raises(ValueError, match="Chained"):
        build_transfer(
            snapshot,
            contents,
            destination_id="another-v1-site",
            authorization_ref="another-auth",
            origin_system="v1-synthetic-site",
            qualifications={
                key: ("Synthetic", "Current access required") for key in contents
            },
            encodings={key: "json-rows-v1" for key in contents},
        )


@pytest.mark.parametrize(
    "data",
    [
        b"{}",
        b"[1]",
        b'[{"x":1,"x":2}]',
        b'[{"x":NaN}]',
        b'[{"x":9007199254740993}]',
        b"\xff",
    ],
)
def test_ambiguous_json_rows_reject_before_copy(tmp_path, data):
    snapshot, contents, _ = copy_fixture()
    payload = snapshot.model_dump(mode="json")
    obj = payload["objects"][0]
    digest = hashlib.sha256(data).hexdigest()
    obj.update(sha256=digest, size_bytes=len(data))
    obj["provenance"]["content_sha256"] = digest
    contents[obj["object_id"]] = data
    with pytest.raises(ValueError):
        build_transfer(
            validated_manifest(payload),
            contents,
            destination_id="v1-synthetic-site",
            authorization_ref="synthetic-auth",
            origin_system="synthetic-origin",
            qualifications={
                key: ("Synthetic", "Current access required") for key in contents
            },
            encodings={key: "json-rows-v1" for key in contents},
        )


def test_opaque_bytes_have_no_invented_row_count(tmp_path):
    snapshot, contents, _ = copy_fixture()
    manifest = build_transfer(
        snapshot,
        contents,
        destination_id="v1-synthetic-site",
        authorization_ref="synthetic-auth",
        origin_system="synthetic-origin",
        qualifications={
            key: ("Synthetic", "Current access required") for key in contents
        },
        encodings={key: "opaque-bytes-v1" for key in contents},
    )
    store, result = imported(tmp_path, manifest, contents)
    assert set(dict(result.row_counts).values()) == {None}
    assert store.read(result.snapshot_id)[1] == contents


def test_quarantine_symlink_never_targets_external_directory(tmp_path):
    _, contents, manifest = copy_fixture()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "quarantine").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        imported(tmp_path, manifest, contents)
    assert list(outside.iterdir()) == []


def test_all_four_fixture_families_keep_scientific_units_and_gaps():
    snapshot, contents = fixture_snapshot()
    assert {source.source_family for source in snapshot.source_captures} == set(
        FIXTURE_ROWS
    )
    ctd = json.loads(contents["synthetic:ctd:depth_observations"])
    assert ctd[0]["temperature_degC"] == -1.5 and len(ctd) == 2
    assert json.loads(contents["synthetic:remote_sensing:coverage"])[0][
        "missing_dates"
    ] == ["2024-01-02"]
    assert (
        json.loads(contents["synthetic:metagenome:metaeuk_measurements"])[0]["method"]
        == "MetaEuk"
    )
    assert (
        json.loads(contents["synthetic:edna_metabarcoding:canonical_rows"])[1][
            "is_control"
        ]
        is True
    )
    assert {
        obj.role
        for obj in snapshot.objects
        if obj.source_family == "edna_metabarcoding"
    } == {"canonical_rows", "classifications"}
