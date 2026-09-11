"""Interpret provider taxonomy without changing its source labels or lineage."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any


TAXONOMY_POLICY_VERSION = "edna-taxonomy-v1"
ANALYSIS_RANKS = (
    "superkingdom", "kingdom", "phylum", "class", "order", "family", "genus", "species",
)
CANONICAL_RANKS = (*ANALYSIS_RANKS, "subspecies")
SOURCE_RANKS = (
    "superkingdom", "kingdom", "subkingdom", "superphylum", "phylum",
    "subphylum", "superclass", "class", "subclass", "infraclass", "cohort",
    "subcohort", "superorder", "order", "suborder", "infraorder", "parvorder",
    "superfamily", "family", "subfamily", "tribe", "subtribe", "genus",
    "subgenus", "section", "subsection", "series", "species group",
    "species subgroup", "species", "subspecies", "varietas", "forma",
    "forma specialis", "strain", "isolate",
)
_UNRESOLVED = re.compile(r"^(?:unidentified|unassigned|unknown|unclassified)(?:\s|$)", re.I)
_MISSING = frozenset({"", "na", "n/a", "null", "nan"})


def resolved_name(value: Any) -> str | None:
    """A placeholder's suffix supplies context, never an assignment at that rank."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if name.casefold() in _MISSING or _UNRESOLVED.match(name):
        return None
    return name


def resolved_lineage(taxonomy: Mapping[str, Any]) -> dict[str, str]:
    """Return usable indexed ranks, without promoting a repeated ancestor label."""
    result: dict[str, str] = {}
    seen: set[str] = set()
    for rank in CANONICAL_RANKS:
        name = resolved_name(taxonomy.get(rank))
        if name is not None and name.casefold() not in seen:
            result[rank] = name
            seen.add(name.casefold())
    return result


def deepest_resolved_assignment(taxonomy: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Choose a source-backed name/rank; padded ranks do not add precision.

    ANEMONE repeats names across intermediate ranks. Prefer the indexed rank
    carrying that same name, or its broadest indexed occurrence if repeated.
    Distinct assignments at other source ranks (e.g. subfamily) remain usable.
    """
    lineage = resolved_lineage(taxonomy)
    canonical_names = {name.casefold(): rank for rank, name in lineage.items()}
    for rank in reversed(SOURCE_RANKS):
        name = resolved_name(taxonomy.get(rank))
        if name is not None:
            resolved_rank = canonical_names.get(name.casefold(), rank)
            return resolved_name(taxonomy.get(resolved_rank)), resolved_rank
    return None, None


def detection_assignment(detection: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Reinterpret older canonical rows when rebuilding retrieval documents."""
    raw = detection.get("taxonomy_json")
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, Mapping) and raw:
        return deepest_resolved_assignment(raw)
    taxonomy = {rank: detection.get(rank) for rank in SOURCE_RANKS}
    # Sparse legacy records may carry a valid assignment without its rank column.
    rank = detection.get("assigned_taxon_rank")
    if (isinstance(rank, str) and rank in SOURCE_RANKS
            and (not isinstance(taxonomy[rank], str) or not taxonomy[rank].strip())):
        taxonomy[rank] = resolved_name(detection.get("assigned_taxon_name"))
    return deepest_resolved_assignment(taxonomy)
