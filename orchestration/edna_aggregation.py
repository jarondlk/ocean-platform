"""Conservative routing and deterministic answers for exact catalogue questions.

This is a bounded vocabulary, not a natural-language-to-SQL interface. Any
unresolved qualifier fails closed rather than silently querying a wider cohort.
"""

from dataclasses import dataclass
import json
import re

FILTERS = (
    "sample_id",
    "provider",
    "provider_project_id",
    "provider_run_id",
    "assignment_method",
    "taxon",
    "sample_kind",
    "is_control",
    "time_from",
    "time_to",
    "lat_min",
    "lat_max",
    "lon_min",
    "lon_max",
)
GROUPS = {
    "locus": "provider_locus",
    "loci": "provider_locus",
    "team": "provider_team",
    "teams": "provider_team",
    "project": "provider_project_id",
    "projects": "provider_project_id",
    "run": "provider_run_id",
    "runs": "provider_run_id",
}
EDNA_ALIASES = {
    "edna",
    "environmental_dna",
    "edna_metabarcoding",
    "metabarcoding",
    "mifish",
    "anemone",
}
COUNT = re.compile(
    r"\b(how many|number of|counts?|totals?|summary|summarize|summarise|breakdown|proportion|percentage)\b|何件|いくつ|何サンプル",
    re.I,
)
TOPIC = re.compile(r"\b(anemone|edna|mifish|metabarcoding)\b", re.I)
WORDS = set(
    """give please tell me how many what is are the a an of in on from for do we have there and or with without versus vs compare can i add them their these those this that our currently available included include published imported detected recorded reported overall entire whole all database db catalogue catalog ocean platform anemone edna mifish metabarcoding data dataset sample samples sampling physical independent unique source sources occurrence occurrences assay assays assignment assignments detection detections row rows reads read sequencing count counts total totals number summary summarize summarise breakdown proportion percentage coverage locus loci team teams project projects run runs by per each both methods method qcauto qc 3nn nn auto target nontarget non targets controls control negative positive mock community environmental classified classifications classification unknown status empty missing unavailable tables table standards standard internal concentration concentrations copies ml column columns selected current filters filtered scope cohort date range time period location coordinates taxon taxonomy results records versus between anemone's what's what's""".split()
)


@dataclass(frozen=True)
class AggregatePlan:
    filters: dict
    group_by: tuple = ()
    clarification: str | None = None


SCOPE_MESSAGE = (
    "I need an explicit scope for that exact count. Set the project, run, taxon, "
    "date or coordinate filters, then ask for a catalogue summary. I can count "
    "source occurrences, assays, classifications, assignments and reads; I cannot "
    "infer physical-sample counts, species richness or ecological abundance from "
    "these records. No database-wide total was substituted."
)


def plan_aggregation(request: dict) -> AggregatePlan | None:
    query = request.get("query", "")
    options = request.get("aggregation")
    forced = options is not None
    source = str(request.get("source_type") or "").lower().strip()
    scoped = source in EDNA_ALIASES or any(
        request.get(k) is not None
        for k in (
            "provider",
            "provider_project_id",
            "provider_run_id",
            "assignment_method",
            "taxon",
            "sample_kind",
            "is_control",
        )
    )
    if not forced and not (COUNT.search(query) and (scoped or TOPIC.search(query))):
        return None
    # Existing analyses have separately validated recipes; never replace them
    # with a global catalogue cohort.
    if request.get("analysis_id") and not forced:
        return None
    filters = {key: request[key] for key in FILTERS if request.get(key) is not None}
    filters.setdefault("provider", "anemone")
    options = options or {}
    filters.update(
        {
            key: options[key]
            for key in ("provider_locus", "provider_team", "target_status", "assay_id")
            if options.get(key) is not None
        }
    )
    if (
        source
        and source not in EDNA_ALIASES
        or request.get("analysis_id")
        or request.get("bay")
        or filters["provider"] != "anemone"
    ):
        return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
    query = re.sub(r"qcauto\s*\+\s*3-?nn", "qcauto 3nn", query.lower())
    query = query.replace("qcauto 95%-3nn", "qcauto 3nn")
    query = re.sub(r"\bnon[ -]+target\b", "nontarget", query)
    # Explicit filter values may be repeated literally in the question. No
    # number, date, named location or taxon is interpreted from free text.
    for value in filters.values():
        if isinstance(value, str) and value:
            query = re.sub(
                r"(?<!\w)" + re.escape(value.lower()) + r"(?!\w)", " ", query
            )
    # Fixed enums can be resolved without guessing scientific or geographic scope.
    enums = {}
    target_words = set(re.findall(r"\b(target|nontarget)\b", query))
    if len(target_words) == 1:
        enums["target_status"] = next(iter(target_words))
    if (
        len(
            set(
                re.findall(r"\b(negative|positive|environmental|unknown|mock)\b", query)
            )
        )
        > 1
    ):
        return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
    kinds = [
        kind
        for phrase, kind in (
            ("negative control", "negative_control"),
            ("positive control", "positive_control"),
            ("mock community", "mock_community"),
            ("environmental", "environmental"),
            ("unknown sample", "unknown"),
        )
        if phrase in query
    ]
    if len(kinds) == 1:
        enums["sample_kind"] = kinds[0]
    elif len(kinds) > 1:
        return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
    if re.search(r"\bcontrols?\b", query) and not re.search(
        r"\b(unknown|classifications?|status|environmental)\b", query
    ):
        enums["is_control"] = True
    if enums.get("sample_kind") == "environmental":
        enums["is_control"] = False
    three_nn = bool(re.search(r"\bqcauto\s+3nn\b", query))
    qcauto = bool(re.search(r"\bqcauto\b", re.sub(r"\bqcauto\s+3nn\b", "", query)))
    if three_nn != qcauto:
        method = "qcauto_95pct_3nn" if three_nn else "qcauto"
        status = enums.get("target_status", filters.get("target_status", "target"))
        enums["assignment_method"] = method + "_" + status
    for key, value in enums.items():
        if key in filters and filters[key] != value:
            return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
        filters[key] = value
    if (
        filters.get("sample_kind") == "environmental"
        and filters.get("is_control") is True
        or filters.get("assignment_method")
        and filters.get("target_status")
        and not filters["assignment_method"].endswith("_" + filters["target_status"])
    ):
        return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
    inferred = []
    grouping = re.search(r"\b(?:by|per|in each|for each)\s+(.+)", query)
    if grouping:
        tail = re.findall(r"[a-z]+", grouping[1])
        if any(
            word not in {*GROUPS, "and", "then", "per", "method", "methods"}
            for word in tail
        ):
            return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
        inferred = list(dict.fromkeys(GROUPS[word] for word in tail if word in GROUPS))
        query = query[: grouping.start()]
    group_by = options.get("group_by") or inferred
    if inferred and options.get("group_by") and inferred != options["group_by"]:
        return AggregatePlan(filters, clarification=SCOPE_MESSAGE)
    if len(group_by) > 2:
        return AggregatePlan(
            filters,
            clarification="Please group exact counts by at most two of locus, team, project and run.",
        )
    # Remaining punctuation is harmless; remaining numbers or unknown words
    # are not silently treated as filler (e.g. 2020, Japan, >10, species).
    words = re.findall(r"[\w]+(?:'[\w]+)?", query)
    if (
        not words
        or any(word not in WORDS for word in words)
        or any(word in words for word in ("selected", "filtered"))
        and set(filters) == {"provider"}
    ):
        return AggregatePlan(filters, tuple(group_by), SCOPE_MESSAGE)
    if (
        any(
            re.search(
                r"\b(?:selected|filtered|this|that|current|each)\s+" + word + r"\b",
                query,
            )
            and key not in filters
            for word, key in GROUPS.items()
        )
        or re.search(r"\b(date|time|period|range)\b", query)
        and not any(k in filters for k in ("time_from", "time_to"))
        or re.search(r"\b(location|coordinates)\b", query)
        and not any(k in filters for k in ("lat_min", "lat_max", "lon_min", "lon_max"))
        or re.search(r"\b(taxon|taxonomy)\b", query)
        and "taxon" not in filters
        or re.search(r"\b(proportion|percentage)\b", query)
    ):
        return AggregatePlan(filters, tuple(group_by), SCOPE_MESSAGE)
    if re.search(r"\b(without|except|exclude|excluding|only|not)\b", query):
        return AggregatePlan(filters, tuple(group_by), SCOPE_MESSAGE)
    return AggregatePlan(filters, tuple(group_by))


def evidence_document(bundle):
    identity, payload = bundle["aggregate_id"], bundle["payload"]
    return {
        "id": "aggregate_edna_" + identity,
        "title": "Exact ANEMONE catalogue summary",
        "source_type": "analysis",
        "source_family": "edna_metabarcoding",
        "covered_source_types": ["edna_metabarcoding"],
        "analysis_type": "edna_catalogue_summary",
        "aggregate_id": identity,
        "text": json.dumps(payload["summary"], sort_keys=True, ensure_ascii=False),
    }


def render_answer(bundle):
    payload = bundle["payload"]
    summary = payload["summary"]
    cite = "[aggregate_edna_" + bundle["aggregate_id"] + "]"

    # JSON values are data; Markdown metacharacters and bracket citation syntax
    # in provider/user labels must not become active UI markup.
    def label(value):
        value = str(value).replace("\n", " ").replace("\r", " ")
        return re.sub(r"([\\`*{}\[\]()<>|])", r"\\\1", value)

    scope = "; ".join(
        label(k) + "=" + label(v) for k, v in sorted(payload["filters"].items())
    )
    lines = [
        f"For the published OCEAN catalogue with filters {scope}: **{summary['source_occurrences']:,} source occurrences and {summary['assays']:,} matching assays**. The number of distinct physical samples is unresolved. {cite}",
        f"Classifications: {summary['controls']:,} controls, {summary['unknown_control_status']:,} with unknown control status, and {summary['environmental_classified']:,} explicitly classified environmental occurrences. Kinds: "
        + (
            ", ".join(label(k) + f"={v:,}" for k, v in summary["sample_kinds"].items())
            or "none"
        )
        + f". {cite}",
    ]
    if summary.get("namespaces"):
        lines.append(
            "Distinct recorded namespaces: "
            + ", ".join(label(k) + f"={v:,}" for k, v in summary["namespaces"].items())
            + ". Counts respect their parent namespaces. "
            + cite
        )
    methods = {row["assignment_method"]: row for row in summary["methods"]}
    availability = {
        row["assignment_method"]: row for row in summary["community_availability"]
    }
    for method in sorted(set(methods) | set(availability)):
        row, available = methods.get(method, {}), availability.get(method)
        message = f"{label(method)}: {row.get('assignment_rows', 0):,} assignment rows; {row.get('read_count_sum', 0):,} sequence reads."
        if available:
            message += f" {available['available_tables']:,} source tables available, including {available['empty_tables']:,} valid empty tables."
        message += f" Copies/mL: {row.get('concentration_records', 0):,} reported, {row.get('concentration_missing', 0):,} missing, {row.get('concentration_column_absent', 0):,} with the source column absent."
        lines.append(message + " " + cite)
    if not methods and not availability:
        lines.append(
            "No matching assignment rows or documented available community tables were found. This does not establish biological absence. "
            + cite
        )
    standards = summary["internal_standards"]
    lines.append(
        f"Internal standards are separate: {standards['rows']:,} rows and {standards['reads']:,} reads across the matching assays. Their presence does not establish calibration validity. "
        + cite
    )
    groups = summary["groups"]
    if groups:
        for row in groups[:25]:
            lines.append(
                "; ".join(
                    label(key) + "=" + label(row[key]) for key in summary["group_by"]
                )
                + f": {row['source_occurrences']:,} source occurrences. {cite}"
            )
        if len(groups) > 25:
            lines.append(
                f"Showing 25 of {len(groups):,} groups; the downloadable aggregate contains every group. {cite}"
            )
    lines.append(
        "Assignment methods describe alternative interpretations of shared reads; do not add them as independent observations. Reads are not organism counts. Missing concentrations are not zero. These are published OCEAN totals; coverage of unpublished or subsequently changed ANEMONE data is not established. "
        + cite
    )
    return "\n\n".join(lines)
