"""One canonical eDNA predicate plan, rendered to SQL or frozen-row selection.

The relational predicates deliberately distinguish a sample occurrence, an assay,
and a detection. An available empty community table can select its assay and
occurrence without creating a detection. Scientific eligibility is a separate
policy; these predicates retain all four raw assignment methods.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from preprocessing.edna_taxonomy import CANONICAL_RANKS
from schema.time_range import matches_time, sql_time_conditions, time_bounds


EDNA_ASSIGNMENT_METHODS = frozenset({
    "qcauto_target", "qcauto_95pct_3nn_target", "qcauto_nontarget",
    "qcauto_95pct_3nn_nontarget",
})
EDNA_SAMPLE_KINDS = frozenset({
    "environmental", "negative_control", "positive_control", "mock_community", "unknown",
})
TAXON_COLUMNS = ("assigned_taxon_name", *CANONICAL_RANKS)
SAMPLE_DIRECT = (
    "provider", "provider_locus", "provider_team", "provider_project_id",
    "provider_run_id", "sample_kind", "sample_id",
)
DETECTION_DIRECT = ("assignment_method", "target_status")
BOUNDS = (("lat_min", "lat", ">="), ("lat_max", "lat", "<="),
          ("lon_min", "lon", ">="), ("lon_max", "lon", "<="))
FILTER_KEYS = frozenset((*SAMPLE_DIRECT, *DETECTION_DIRECT, "assay_id", "is_control",
                         "taxon", "time_from", "time_to", *(key for key, _, _ in BOUNDS)))


class QueryUnavailable(ValueError):
    """Retained evidence cannot support the requested exact predicate."""


def normalize_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    """Validate frozen-query parameters without manufacturing or trimming labels."""
    if not isinstance(filters, Mapping) or set(filters) - FILTER_KEYS:
        raise ValueError("Unsupported eDNA filter")
    result = {key: value for key, value in filters.items() if value is not None}
    for key, value in result.items():
        if key == "is_control":
            if type(value) is not bool:
                raise ValueError("is_control must be boolean")
        elif key in {bound[0] for bound in BOUNDS}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("Geographic bounds must be finite numbers")
            limit = 90 if key.startswith("lat") else 180
            if not -limit <= value <= limit:
                raise ValueError("Geographic bound is out of range")
        elif not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise ValueError("eDNA filter labels must be nonempty strings")
    if result.get("assignment_method") not in EDNA_ASSIGNMENT_METHODS | {None}:
        raise ValueError("Unsupported assignment_method")
    if result.get("sample_kind") not in EDNA_SAMPLE_KINDS | {None}:
        raise ValueError("Unsupported sample_kind")
    if result.get("target_status") not in {None, "target", "nontarget"}:
        raise ValueError("Unsupported target_status")
    for axis in ("lat", "lon"):
        if axis + "_min" in result and axis + "_max" in result:
            if result[axis + "_min"] > result[axis + "_max"]:
                raise ValueError("Geographic bounds are reversed")
    time_bounds(result.get("time_from"), result.get("time_to"))
    return dict(sorted(result.items()))


def _clean(value):
    if value is None:
        return None
    try:
        return None if pd.isna(value) else value
    except (ValueError, TypeError):
        return value


def _json_object(value):
    value = _clean(value)
    if value is None:
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise QueryUnavailable("Canonical JSON evidence must be an object")
    return value


def _column(alias, field):
    return alias + "." + ('"' + field + '"' if field in {"class", "order"} else field)


@dataclass(frozen=True)
class _All:
    children: tuple

    def sql(self, params):
        return "(" + " AND ".join(child.sql(params) for child in self.children) + ")"

    def matches(self, context, index):
        return all(child.matches(context, index) for child in self.children)


@dataclass(frozen=True)
class _Any:
    children: tuple

    def sql(self, params):
        return "(" + " OR ".join(child.sql(params) for child in self.children) + ")"

    def matches(self, context, index):
        return any(child.matches(context, index) for child in self.children)


@dataclass(frozen=True)
class _Active:
    alias: str

    def sql(self, params):
        return self.alias + ".active IS TRUE"

    def matches(self, context, index):
        return context[self.alias].get("active") is True


@dataclass(frozen=True)
class _Scalar:
    alias: str
    field: str
    name: str
    value: Any
    operator: str = "="

    def sql(self, params):
        params[self.name] = self.value
        return f"{_column(self.alias, self.field)} {self.operator} :{self.name}"

    def matches(self, context, index):
        observed = _clean(context[self.alias].get(self.field))
        if self.operator == "IS NOT DISTINCT FROM":
            return observed == self.value
        if observed is None:
            return False
        if self.operator == "=":
            return observed == self.value
        if self.operator == ">=":
            return observed >= self.value
        return observed <= self.value


@dataclass(frozen=True)
class _Time:
    start: str | None
    end: str | None

    def sql(self, params):
        clauses, values = sql_time_conditions("s.collection_date_utc", self.start, self.end)
        params.update(values)
        return "(" + " AND ".join(clauses) + ")"

    def matches(self, context, index):
        sample = context["s"]
        if sample.get("temporal_precision") not in {"date", "day", "datetime"}:
            raise QueryUnavailable("Exact time filtering is unavailable for coarse or unresolved dates")
        return matches_time(sample.get("collection_date_utc"), self.start, self.end)


@dataclass(frozen=True)
class _Taxon:
    value: str

    def sql(self, params):
        params["taxon"] = self.value
        return "(" + " OR ".join(
            f"lower({_column('d', column)}) = lower(:taxon)" for column in TAXON_COLUMNS
        ) + ")"

    def matches(self, context, index):
        detection = context["d"]
        taxonomy = _json_object(detection.get("taxonomy_json"))
        # The canonical indexed columns retain source labels, including unknown
        # labels. They are not the resolved-lineage scientific analysis policy.
        return any(isinstance(value, str) and value.lower() == self.value.lower()
                   for value in (detection.get("assigned_taxon_name"),
                                 *(detection.get(rank, taxonomy.get(rank)) for rank in CANONICAL_RANKS)))


@dataclass(frozen=True)
class _Availability:
    method: str | None
    status: str | None

    def sql(self, params):
        clauses = []
        if self.method is not None:
            params["assignment_method"] = self.method
            clauses.append("m.key = :assignment_method")
        if self.status is not None:
            params["target_status"] = self.status
            clauses.append("CASE WHEN m.key LIKE '%_nontarget' THEN 'nontarget' ELSE 'target' END = :target_status")
        return ("EXISTS (SELECT 1 FROM jsonb_object_keys(COALESCE(a.community_availability_json,'{}')::jsonb) AS m(key) WHERE "
                + " AND ".join(clauses) + ")")

    def matches(self, context, index):
        methods = _json_object(context["a"].get("community_availability_json"))
        return any((self.method is None or method == self.method)
                   and (self.status is None or ("nontarget" if method.endswith("_nontarget") else "target") == self.status)
                   for method in methods)


@dataclass(frozen=True)
class _Exists:
    alias: str
    predicate: Any

    def sql(self, params):
        table, relation = (("edna_assay", "a.sample_id=s.sample_id") if self.alias == "a"
                           else ("edna_detection", "d.assay_id=a.assay_id"))
        return f"EXISTS (SELECT 1 FROM {table} {self.alias} WHERE {relation} AND {self.predicate.sql(params)})"

    def matches(self, context, index):
        relation = context["s"]["sample_id"] if self.alias == "a" else context["a"]["assay_id"]
        return any(self.predicate.matches({**context, self.alias: item}, index)
                   for item in index[self.alias].get(relation, ()))


def _predicates(filters):
    """Construct each entity's predicate once for both execution backends."""
    base = [_Active("s")]
    base.extend(_Scalar("s", key, key, filters[key]) for key in SAMPLE_DIRECT if filters.get(key) is not None)
    if filters.get("is_control") is not None:
        base.append(_Scalar("s", "is_control", "is_control", filters["is_control"], "IS NOT DISTINCT FROM"))
    base.extend(_Scalar("s", field, key, filters[key], operator)
                for key, field, operator in BOUNDS if filters.get(key) is not None)
    if filters.get("time_from") is not None or filters.get("time_to") is not None:
        base.append(_Time(filters.get("time_from"), filters.get("time_to")))
    assay = [_Active("a")]
    if filters.get("assay_id") is not None:
        assay.append(_Scalar("a", "assay_id", "assay_id", filters["assay_id"]))
    detection = [_Active("d")]
    detection.extend(_Scalar("d", key, key, filters[key]) for key in DETECTION_DIRECT if filters.get(key) is not None)
    if filters.get("taxon") is not None:
        detection.append(_Taxon(filters["taxon"]))
    samples = list(base)
    if filters.get("assay_id") is not None:
        samples.append(_Exists("a", _All(tuple(assay))))
    qualified_assay = list(assay)
    if any(filters.get(key) is not None for key in (*DETECTION_DIRECT, "taxon")):
        match = _Exists("d", _All(tuple(detection)))
        if filters.get("taxon") is None:
            match = _Any((match, _Availability(filters.get("assignment_method"), filters.get("target_status"))))
        qualified_assay.append(match)
        samples.append(_Exists("a", _All(tuple(qualified_assay))))
    return {
        "occurrences": _All(tuple(samples)),
        "assays": _All(tuple([*base, *qualified_assay])),
        "detections": _All(tuple([*base, *assay, *detection])),
    }


def sql_conditions(entity: str, filters: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Canonical SQL compatibility backend; callers retain request validation."""
    params: dict[str, Any] = {}
    return [_predicates(filters)[entity].sql(params)], params


def select_rows(tables: Mapping[str, pd.DataFrame], filters: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    """Select complete active cohorts using the canonical relational predicates.

    Inputs are validated frozen canonical tables. Classification is joined one to
    one by source occurrence, never inferred from a detection or provider label.
    """
    normalized = normalize_filters(filters)
    predicates = _predicates(normalized)
    occurrences = tables["occurrences"].merge(
        tables["classifications"].drop(columns=["source_snapshot_id", "provider_sample_id"], errors="ignore"),
        on="sample_id", how="inner", validate="one_to_one",
    )
    records = {key: frame.to_dict("records") for key, frame in {
        "occurrences": occurrences, "assays": tables["assays"], "detections": tables["detections"],
    }.items()}
    samples = {row["sample_id"]: row for row in records["occurrences"]}
    assays = {row["assay_id"]: row for row in records["assays"]}
    index: dict[str, dict[str, list]] = {"a": {}, "d": {}}
    for row in records["assays"]:
        index["a"].setdefault(row["sample_id"], []).append(row)
    for row in records["detections"]:
        index["d"].setdefault(row["assay_id"], []).append(row)
    selected = {key: [] for key in records}
    for position, sample in enumerate(records["occurrences"]):
        if predicates["occurrences"].matches({"s": sample}, index):
            selected["occurrences"].append(position)
    for position, assay in enumerate(records["assays"]):
        sample = samples.get(assay["sample_id"])
        if sample is not None and predicates["assays"].matches({"s": sample, "a": assay}, index):
            selected["assays"].append(position)
    for position, detection in enumerate(records["detections"]):
        assay = assays.get(detection["assay_id"])
        sample = samples.get(assay["sample_id"]) if assay is not None else None
        if sample is not None and predicates["detections"].matches({"s": sample, "a": assay, "d": detection}, index):
            selected["detections"].append(position)
    return {key: frame.iloc[selected[key]].copy().reset_index(drop=True) for key, frame in {
        "occurrences": occurrences, "assays": tables["assays"], "detections": tables["detections"],
    }.items()}
