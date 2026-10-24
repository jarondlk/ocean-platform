"""Versioned map context and representative positions; canonical counts stay separate."""

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from sqlalchemy import text

from api.edna_service import _sample_conditions
from ingestion.immutable_bundle import canonical_bytes, digest, validate_id

ALGORITHM = "edna-location-context-v4"
METRIC = "location_context"
REGISTRY = Path(__file__).with_name("reference") / "cop17_map_areas.json"
MAX_POSITIONS = 5000
SELECTION = "Exact stored coordinate pairs ordered by latitude, longitude; smallest matching sample_id represents each position. Examples are deterministic, not random or a survey of every area."
DISCLAIMER = "Approximate geographic context inferred from map data, not an ANEMONE-supplied sampling-area name or verified bay membership. Provider grid positions do not establish exact sampling sites. Unassigned positions may be inland, offshore, ambiguous or outside the reviewed map layer."


def options(value=None):
    value = value or {"example_limit": 10, "area_groups": False}
    if (
        set(value) != {"example_limit", "area_groups"}
        or type(value["example_limit"]) is not int
        or not 0 <= value["example_limit"] <= 20
        or type(value["area_groups"]) is not bool
    ):
        raise ValueError("Invalid location-context options")
    return dict(value)


def registry():
    raw = REGISTRY.read_bytes()
    value = json.loads(raw)
    if (
        value["schema_version"] != 1
        or not value["version"]
        or not value["method"]
        or not value["sources"]
    ):
        raise ValueError("Incomplete map registry")
    features = value["features"]
    seen = set()
    for row in value["positions"]:
        key = (row["lat"], row["lon"])
        if (
            key in seen
            or not all(type(v) in (int, float) and math.isfinite(v) for v in key)
            or not -90 <= key[0] <= 90
            or not -180 <= key[1] <= 180
        ):
            raise ValueError("Invalid map position")
        seen.add(key)
        if row.get("feature_id") is not None and row["feature_id"] not in features:
            raise ValueError("Unknown map feature")
    for feature in features.values():
        if not feature["name"] or not feature["source_url"].startswith(
            ("https://www.marineregions.org/", "https://www.geonames.org/")
        ):
            raise ValueError("Invalid map feature source")
    return value, hashlib.sha256(raw).hexdigest()


def map_positions(rows, mapping):
    assigned = {(r["lat"], r["lon"]): r for r in mapping["positions"]}
    result = []
    for row in rows:
        row = dict(row)
        association = assigned.get((row["lat"], row["lon"]))
        row["map_context"] = (
            deepcopy(association)
            if association
            else {
                "lat": row["lat"],
                "lon": row["lon"],
                "feature_id": None,
                "reason": "outside_reviewed_map_layer",
            }
        )
        result.append(row)
    return result


def grouping(rows):
    counts = Counter(r["map_context"].get("feature_id") for r in rows)
    return {
        "generalized_area_groups": [
            {"feature_id": key, "coordinate_positions": counts[key]}
            for key in sorted(k for k in counts if k is not None)
        ],
        "mapped_positions": sum(v for k, v in counts.items() if k is not None),
        "unassigned_positions": counts[None],
    }


def read_positions(connection, filters):
    clauses, params = _sample_conditions(filters)
    clauses += ["s.lat BETWEEN -90 AND 90", "s.lon BETWEEN -180 AND 180"]
    statement = (
        "SELECT DISTINCT ON (s.lat,s.lon) s.lat,s.lon,s.sample_id,s.original_sample_label,s.collection_date_utc,s.temporal_precision,s.coordinate_precision,s.source_snapshot_id,s.source_file_id,s.source_row_hash FROM edna_sample s WHERE "
        + " AND ".join(clauses)
        + " ORDER BY s.lat,s.lon,s.sample_id LIMIT :position_limit"
    )
    rows = (
        connection.execute(
            text(statement), {**params, "position_limit": MAX_POSITIONS + 1}
        )
        .mappings()
        .all()
    )
    if len(rows) > MAX_POSITIONS:
        raise ValueError("Location-context position budget exceeded; narrow filters")
    result = []
    for source in rows:
        row = dict(source)
        for key in (
            "sample_id",
            "source_snapshot_id",
            "source_file_id",
            "source_row_hash",
        ):
            validate_id(row[key])
        for key in (
            "collection_date_utc",
            "temporal_precision",
            "original_sample_label",
            "coordinate_precision",
        ):
            if row[key] is not None:
                row[key] = str(row[key])
        row["lat"], row["lon"] = float(row["lat"]), float(row["lon"])
        result.append(row)
    return result


def validate(payload):
    try:
        context = payload["summary"]["location_context"]
        selected = options(context["options"])
        rows = context["positions"]
        count = payload["summary"]["geography"]["locations"][
            "distinct_coordinate_pairs"
        ]
        assert payload["metric"] == METRIC and payload["algorithm_version"] == ALGORITHM
        assert (
            payload["group_by"] == []
            and payload["summary"]["publication"] == payload["publication"]
        )
        assert len(rows) == count and len(rows) <= MAX_POSITIONS
        assert context["selection"] == SELECTION and context["disclaimer"] == DISCLAIMER
        validate_id(context["registry_sha256"])
        validate_id(context["base_geography_aggregate_id"])
        keys = [(r["lat"], r["lon"]) for r in rows]
        assert keys == sorted(set(keys))
        for row in rows:
            assert all(
                type(v) in (int, float) and math.isfinite(v)
                for v in (row["lat"], row["lon"])
            )
            assert -90 <= row["lat"] <= 90 and -180 <= row["lon"] <= 180
            for key in (
                "sample_id",
                "source_snapshot_id",
                "source_file_id",
                "source_row_hash",
            ):
                validate_id(row[key])
            feature = row["map_context"].get("feature_id")
            assert feature is None or feature in context["features"]
        assert context["groups"] == grouping(rows)
        assert context["options"] == selected
        from ingestion.edna_aggregate import _validate_geography_contract

        _validate_geography_contract({**payload, "metric": "catalogue_geography"})
        assert (
            context["registry_version"]
            and context["map_method"]
            and context["map_sources"]
        )
        for row in rows:
            association = row["map_context"]
            assert (association["lat"], association["lon"]) == (row["lat"], row["lon"])
            if association.get("feature_id"):
                feature = context["features"][association["feature_id"]]
                assert feature["source_url"].startswith("https://www.geonames.org/")
                reference = next(
                    r
                    for r in feature["references"]
                    if r["feature_id"] == association["reference_feature_id"]
                )
                lat1, lat2 = math.radians(row["lat"]), math.radians(reference["lat"])
                dlon = math.radians(row["lon"] - reference["lon"])
                h = (
                    math.sin((lat2 - lat1) / 2) ** 2
                    + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                )
                distance = 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, h))))
                assert abs(distance - association["distance_to_reference_km"]) < 0.002
                assert distance <= (20 if feature["type"] in {"ISL", "ISLS"} else 10)
    except (KeyError, TypeError, ValueError, AssertionError, StopIteration) as exc:
        from ingestion.edna_aggregate import AggregateUnavailable

        raise AggregateUnavailable("Location-context contract is invalid") from exc


def build(filters, *, engine, context_options=None):
    from ingestion import edna_aggregate as a

    selected = options(context_options)
    mapping, map_hash = registry()
    # The unchanged v3 contract verifies full-cohort fingerprints and publication.
    base = a.build_aggregate(filters, engine=engine, metric="catalogue_geography")
    filters = base["payload"]["filters"]
    publication = base["payload"]["publication"]
    with engine.connect() as connection:
        connection.exec_driver_sql(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
        )
        connection.exec_driver_sql("SET LOCAL statement_timeout = '20s'")
        pointer = a.publication_pointer()
        heads = a._publication_heads(connection)
        a._assert_publication(pointer, heads)
        if heads != publication:
            raise a.AggregateUnavailable(
                "Publication changed during map context; retry"
            )
        ids = (
            connection.execute(
                text(
                    "SELECT aggregate_id FROM edna_aggregate_evidence WHERE algorithm_version=:algorithm AND payload_json::jsonb->'filters'=CAST(:filters AS jsonb) AND payload_json::jsonb->'publication'=CAST(:publication AS jsonb) AND payload_json::jsonb->'summary'->'location_context'->>'registry_sha256'=:map_hash AND payload_json::jsonb->'summary'->'location_context'->'options'=CAST(:options AS jsonb) LIMIT 2"
                ),
                {
                    "algorithm": ALGORITHM,
                    "filters": canonical_bytes(filters).decode(),
                    "publication": canonical_bytes(publication).decode(),
                    "map_hash": map_hash,
                    "options": canonical_bytes(selected).decode(),
                },
            )
            .scalars()
            .all()
        )
        if len(ids) > 1:
            raise a.AggregateUnavailable("Conflicting location-context evidence")
        rows = None if ids else read_positions(connection, filters)
    if ids:
        result = a.load_aggregate(ids[0], engine=engine)
        if (
            result is None
            or result["payload"]["summary"]["location_context"][
                "base_geography_aggregate_id"
            ]
            != base["aggregate_id"]
        ):
            raise a.AggregateUnavailable("Location-context base evidence mismatch")
    else:
        if (
            len(rows)
            != base["payload"]["summary"]["geography"]["locations"][
                "distinct_coordinate_pairs"
            ]
        ):
            raise a.AggregateUnavailable(
                "Location examples do not reconcile with full count"
            )
        payload = deepcopy(base["payload"])
        mapped = map_positions(rows, mapping)
        used_features = {
            r["map_context"]["feature_id"]
            for r in mapped
            if r["map_context"].get("feature_id")
        }
        payload.update(algorithm_version=ALGORITHM, metric=METRIC)
        payload["summary"]["location_context"] = {
            "options": selected,
            "positions": mapped,
            "groups": grouping(mapped),
            "features": {k: mapping["features"][k] for k in sorted(used_features)},
            "registry_sha256": map_hash,
            "registry_version": mapping["version"],
            "map_method": mapping["method"],
            "map_sources": mapping["sources"],
            "selection": SELECTION,
            "disclaimer": DISCLAIMER,
            "base_geography_aggregate_id": base["aggregate_id"],
        }
        payload["query_contract"]["map_context"] = (
            "Separate, versioned map-derived geographic context. One generalized feature per coordinate position; nearby does not imply inside a bay. Original scientific metadata and exact count are unchanged."
        )
        validate(payload)
        raw = canonical_bytes(payload)
        if len(raw) > a.MAX_PAYLOAD_BYTES:
            raise a.AggregateUnavailable(
                "Location-context evidence exceeds byte budget"
            )
        identity = digest(payload)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO edna_aggregate_evidence(aggregate_id,algorithm_version,payload_json) VALUES (:id,:algorithm,:payload) ON CONFLICT (aggregate_id) DO NOTHING"
                ),
                {"id": identity, "algorithm": ALGORITHM, "payload": raw.decode()},
            )
            stored = connection.execute(
                text(
                    "SELECT payload_json FROM edna_aggregate_evidence WHERE aggregate_id=:id"
                ),
                {"id": identity},
            ).scalar_one()
            if canonical_bytes(json.loads(stored)) != raw:
                raise a.AggregateUnavailable(
                    "Immutable location-context evidence conflict"
                )
        result = {"aggregate_id": identity, "payload": payload}
    with engine.connect() as connection:
        current = a._publication_heads(connection)
    if current != publication or a.publication_pointer() != pointer:
        raise a.AggregateUnavailable("Publication changed during map context; retry")
    return result
