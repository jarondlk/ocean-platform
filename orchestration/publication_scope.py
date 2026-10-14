"""Deterministic eligibility for immutable published workflows, independent of LLMs.

Only complete supported questions and bounded literal qualifiers are resolved.
Unconsumed text is unresolved: a model's ready status never proves compatibility.
This contract selects existing results; it cannot narrow or recompute a cohort.
"""
from dataclasses import asdict, dataclass
from datetime import date
import re
from typing import Literal

VERSION = "publication-scope-v1"
Outcome = Literal["compatible", "incompatible", "unresolved"]

# Positive aliases for the registered publication geography, not a place denylist.
# Other registered regions accept their exact identity until reviewed aliases exist.
REGION_ALIASES = {
    "miyagi-regional-demo": (
        "Miyagi", "Miyagi coast", "Miyagi coastal waters", "Miyagi Prefecture",
        "宮城", "宮城県", "宮城沿岸", "宮城県沿岸",
    ),
}
METHOD_ALIASES = {"3nn": "qcauto_95pct_3nn_target"}
PANEL_SIZE = {"fish_frequency": 10, "temperature_comparison": 10,
              "distribution_change": 3, "follow_through": 3}
SPATIAL = {"monthly_spatial", "spatial_temperature"}
SST = {"temperature_comparison", "spatial_temperature", "follow_through"}


@dataclass(frozen=True)
class ScopeEvidence:
    field: str
    outcome: Outcome
    requested: str
    registered: str
    quote: str | None
    source: Literal["question", "selection", "publication"]
    reason: str


@dataclass(frozen=True)
class ScopeCompatibility:
    outcome: Outcome
    reason: str
    workflow: str
    analysis_id: str | None
    evidence: tuple[ScopeEvidence, ...]
    version: str = VERSION

    def as_dict(self):
        return {**asdict(self), "evidence": [asdict(e) for e in self.evidence]}


def _norm(value):
    return re.sub(r"\s+", " ", str(value).casefold().strip()).rstrip(".?!。？！")


def _finish(kind, option, evidence):
    failed = next((e for e in evidence if e.outcome == "incompatible"), None)
    failed = failed or next((e for e in evidence if e.outcome == "unresolved"), None)
    return ScopeCompatibility(failed.outcome if failed else "compatible",
                              failed.reason if failed else "All explicit qualifiers match the registered publication.",
                              kind, option.get("analysis_id"), tuple(evidence))


def registered_filter_values(recipe, samples=(), *, provisional=False):
    values = {key: recipe[key] for key in ("assignment_method", "time_from", "time_to") if key in recipe}
    if not provisional:
        values.update(sample_kind="environmental", is_control=False)
    for key in ("provider", "provider_project_id", "provider_run_id"):
        choices = {sample.get(key) for sample in samples}
        if len(choices) == 1 and None not in choices:
            values[key] = choices.pop()
    return values


def fixed_spatial_taxon(recipe, detections):
    from ingestion.immutable_bundle import digest
    from preprocessing.edna_analysis import taxon_key
    names = {row.get("species") for row in detections if taxon_key(row, "species") is not None
             and digest(taxon_key(row, "species")) == recipe.get("spatial_taxon_key")}
    return next(iter(names)) if len(names) == 1 else None


def scope_option_from_bundle(bundle):
    """Project the same contract metadata used by the planning catalogue."""
    from ingestion.immutable_bundle import digest
    from preprocessing.edna_analysis import protocol
    ids = sorted({row["protocol_id"] for row in bundle["tables"]["membership"]})
    recipe = bundle["recipe"]
    provisional = bundle["manifest"].get("schema_version") == 3
    return {
        "analysis_id": bundle["manifest"]["id"], "recipe_scope": recipe,
        "assignment_methods": [recipe["assignment_method"]], "protocol_ids": ids,
        "protocols": {digest(protocol(a)): protocol(a) for a in bundle["inputs"]["canonical"]["edna_assay"]
                      if digest(protocol(a)) in ids},
        "cohort_filters": registered_filter_values(recipe, bundle["inputs"]["canonical"]["edna_sample"],
                                                  provisional=provisional),
        "sst_dataset_id": "mur-miyagi-2020-2023" if provisional else None,
        "spatial_taxon": fixed_spatial_taxon(recipe, bundle["inputs"]["canonical"]["edna_detection"]),
    }


def protocol_hints(query, option):
    """Literal reviewed protocol attributes; no instrument or primer inference."""
    # Missing metadata is not an instrument called "None"; only retained
    # nonempty textual attributes supply registered aliases.
    instruments = {name.strip() for protocol in option.get("protocols", {}).values()
                   if isinstance(name := protocol.get("sequencing_method"), str) and name.strip()}
    # Named unavailable instruments must not become a default. Unknown names are
    # additionally rejected by the complete-question consumer below.
    instruments |= {"MiSeq", "NextSeq", "NovaSeq", "Nanopore", "PacBio"}
    def boundary(name):
        return r"(?<![a-z0-9_])" + re.escape(name) + r"(?![a-z0-9_])"
    hints = {
        "sequencing_method": [name for name in sorted(instruments) if name and re.search(boundary(name), query, re.I)],
        "library_layout": (["paired"] if re.search(r"\bpaired(?:[- ]end)?\b|ペアエンド", query, re.I) else [])
                          + (["single"] if re.search(r"\bsingle(?:[- ]end)?\b|シングルエンド", query, re.I) else []),
        "target_gene": [gene for gene in ("12S", "16S", "18S", "COI") if re.search(boundary(gene), query, re.I)],
    }
    return {key: values for key, values in hints.items() if values}


def resolve_protocol(option, query, pin=None):
    ids = option.get("protocol_ids", [])
    named = re.findall(r"(?<![a-f0-9])[a-f0-9]{64}(?![a-f0-9])", query, re.I)
    named = [identity.lower() for identity in named]
    hints = protocol_hints(query, option)
    eligible = [identity for identity in ids if (not named or set(named) == {identity}) and all(
        all(isinstance(attribute := option.get("protocols", {}).get(identity, {}).get(field), str)
            and re.search(r"(?<![a-z0-9_])" + re.escape(value) + r"(?![a-z0-9_])", attribute, re.I)
            for value in values) for field, values in hints.items())]
    if pin:
        return (pin, False) if pin in eligible else (None, False)
    return (eligible[0], not hints and not named) if eligible else (None, False)


def publication_compatibility(query, kind, option, *, protocol_id=None, scope=None, question_only=False):
    """Return traceable eligibility, checking original text and effective selections.

    Planning and execution supply independently obtained publication descriptors.
    Missing metadata and unsupported residual text fail closed. Unqualified
    supported aliases bind the selected publication, not an invented geography.
    """
    from orchestration.research_intents import QUESTIONS
    from orchestration.research_question import FREQUENCY_JA, SPATIAL_JA
    recipe = option.get("recipe_scope", {})
    evidence = []

    def record(field, requested, registered, quote=None, source="question", *, outcome=None, reason=None):
        status = outcome or ("compatible" if requested == registered else "incompatible")
        evidence.append(ScopeEvidence(field, status, str(requested), str(registered), quote, source,
                                      (f"The requested {field} matches the registered publication." if status == "compatible" else reason or f"The requested {field} differs from the immutable publication; select a matching analysis or revise the qualifier.")))

    for field in ("region_id", "time_from", "time_to", "rank", "fish_classes"):
        if not recipe.get(field):
            record(field, "required", "unregistered", source="publication", outcome="unresolved",
                   reason="The publication scope is incomplete. Select a verified analysis.")
    if not question_only and not option.get("assignment_methods") and not recipe.get("assignment_method"):
        record("assignment_method", "required", "unregistered", source="publication", outcome="unresolved",
               reason="The publication assignment method is unregistered. Select a verified analysis.")
    if not question_only:
        if recipe.get("rank"):
            record("rank", "species", recipe["rank"], source="publication")
        if recipe.get("calendar") != "Asia/Tokyo":
            record("calendar", "Asia/Tokyo", recipe.get("calendar"), source="publication", outcome="unresolved")
        required = ("spatial_taxon_key", "spatial_year") if kind in SPATIAL else ()
        required += ("sst_panel_id",) if kind in SST else ()
        required += ("endpoint_from", "endpoint_to") if kind in {"distribution_change", "follow_through"} else ()
        for field in required:
            if not recipe.get(field):
                record(field, "required", "unregistered", source="publication", outcome="unresolved",
                       reason=f"The {field} is not registered for this workflow. Select a verified analysis.")
        if kind in SPATIAL and option.get("spatial_taxon") != "Sardinops melanostictus":
            record("spatial_taxon", "Sardinops melanostictus", option.get("spatial_taxon"), source="publication", outcome="unresolved",
                   reason="This analysis does not establish species-resolved Sardinops melanostictus evidence. No taxon was substituted.")
    if protocol_id is None and scope is not None and len(option.get("protocol_ids", [])) != 1:
        record("protocol_id", "unselected", "one registered protocol", source="selection", outcome="unresolved",
               reason="Select one registered assay protocol; unresolved protocols cannot authorize a published result.")
    if protocol_id and protocol_hints(query, option):
        resolved, _ = resolve_protocol(option, query, protocol_id)
        record("protocol", query, protocol_id, query, outcome="compatible" if resolved else "incompatible",
               reason="The requested assay protocol conflicts with the selected registered protocol.")
    if kind not in QUESTIONS:
        record("workflow", kind, "registered workflow", outcome="unresolved")
        return _finish(kind, option, evidence)

    def geography(value, quote):
        expected = recipe.get("region_id")
        aliases = [expected, *REGION_ALIASES.get(expected, ())]
        if _norm(value) in {_norm(a) for a in aliases if a}:
            record("geography", expected, expected, quote)
        else:
            # A literal registered identity can conflict; a new place is unresolved.
            known = any(_norm(value) in {_norm(k), *map(_norm, v)} for k, v in REGION_ALIASES.items())
            record("geography", value, expected, quote, outcome="incompatible" if known else "unresolved",
                   reason="The requested place does not resolve to this registered publication region. Select a matching analysis or clarify the place.")

    def dates(first, last, quote, *, spatial=False):
        if spatial and len(first) == 4 and first == last:
            record("spatial_year", first, str(recipe.get("spatial_year")), quote)
            return
        if kind in {"distribution_change", "follow_through"}:
            if len(first) != 4 or len(last) != 4:
                record("endpoint_years", quote, "explicit endpoint years", quote, outcome="unresolved")
            else:
                record("endpoint_years", first + "/" + last,
                       str(recipe.get("endpoint_from")) + "/" + str(recipe.get("endpoint_to")), quote)
            return
        start = first + "-01-01" if len(first) == 4 else first
        end = last + "-12-31" if len(last) == 4 else last
        try:
            valid = date.fromisoformat(start) <= date.fromisoformat(end)
        except ValueError:
            valid = False
        if not valid:
            record("dates", quote, "valid ordered calendar dates", quote, outcome="unresolved",
                   reason="Use valid explicit calendar dates in chronological order.")
        else:
            record("dates", start + "/" + end, str(recipe.get("time_from")) + "/" + str(recipe.get("time_to")), quote)

    def panel(value, quote):
        expected = PANEL_SIZE.get(kind)
        count = {"three": 3, "ten": 10}.get(value.casefold())
        count = count if count is not None else int(value)
        record("panel_size", count, expected, quote,
               reason="This immutable workflow uses a fixed top-ten or endpoint-selected three-fish panel; it cannot change the ranking or panel size.")

    remaining = query.strip()
    matched_kind = None
    # Complete Japanese templates resolve fields individually, even when changed.
    for heading, template, workflow in (
        ("よく見つかる魚は何か？", FREQUENCY_JA, "fish_frequency"),
        ("イワシはどこで見つかるか？", SPATIAL_JA, "monthly_spatial"),
    ):
        pattern = re.escape(template).replace("宮城県", r"(?P<region>[^、。]+?)")
        if workflow == "fish_frequency":
            pattern = pattern.replace("2020", r"(?P<first>\d{4})").replace("2023", r"(?P<last>\d{4})").replace("魚の", r"(?P<taxon>[^、。]+?)の").replace("10", r"(?P<top>\d+)")
        else:
            pattern = pattern.replace("2023", r"(?P<year>\d{4})").replace("マイワシ", r"(?P<taxon>[^、。]+?)")
        positions = [i for i, char in enumerate(remaining) if not char.isspace()]
        compact = "".join(remaining[i] for i in positions)
        match = re.match(r"(?:" + re.escape(heading) + r")?" + pattern, compact)
        def original_quote(group):
            start, end = match.span(group)
            return remaining[positions[start]:positions[end - 1] + 1]
        if match:
            matched_kind = workflow
            geography(match["region"], original_quote("region"))
            dates(match["first"], match["last"], original_quote(0)) if workflow == "fish_frequency" else dates(match["year"], match["year"], original_quote("year"), spatial=True)
            record("taxon_panel", match["taxon"], "魚" if workflow == "fish_frequency" else "マイワシ", original_quote("taxon"))
            if workflow == "fish_frequency":
                panel(match["top"], original_quote("top"))
            remaining = remaining[positions[match.end() - 1] + 1:]
            break

    if not matched_kind:
        bases = {workflow: list(aliases) for workflow, aliases in QUESTIONS.items()}
        bases["fish_frequency"] += [
            "Explain what the published fish detections tell us and their uncertainty",
            "Interpret the published fish frequencies", "Interpret published fish frequencies",
            "Show published fish frequency", "Show fish frequencies", "Show the top 10 fish",
            "Show the top 10 fish by detection frequency",
            "公表済みの魚の検出頻度を解釈してください", "魚の検出頻度を解釈してください",
        ]
        bases["temperature_comparison"] += ["Compare fish detections in high and low SST"]
        bases["monthly_spatial"] += ["採水地点が最も多かった月とマイワシの検出地域を示してください"]
        candidates = sorted(((base, workflow) for workflow, aliases in bases.items() for base in aliases), key=lambda x: len(x[0]), reverse=True)
        for base, workflow in candidates:
            pattern = r"\s+".join(re.escape(word) for word in base.rstrip(".?!。？！").split())
            match = re.match(pattern + r"(?=$|[\s.,?!。？！、])", remaining, re.I)
            if match:
                matched_kind = workflow
                remaining = remaining[match.end():]
                break
        if not matched_kind:
            match = re.match(r"(?:interpret|show)\s+(?:the\s+)?(?:top\s+(?P<top>\d+)\s+)?(?P<taxon>[a-z-]+)\s+detection\s+frequenc(?:y|ies)(?=$|[\s.,?!])", remaining, re.I)
            if match:
                matched_kind = "fish_frequency"
                record("taxon_panel", match["taxon"].casefold(), "fish", match["taxon"])
                if match["top"]:
                    panel(match["top"], match["top"])
                remaining = remaining[match.end():]
    if not matched_kind:
        match = re.match(r"Use\s+(3\s*(?:-\s*)?NN)\s+fish frequenc(?:y|ies)(?=$|[\s.,?!])", remaining, re.I)
        if match:
            matched_kind = "fish_frequency"
            record("assignment_method", "qcauto_95pct_3nn_target", next(iter(option.get("assignment_methods", [])), recipe.get("assignment_method")), match[1])
            remaining = remaining[match.end():]
    if matched_kind:
        record("workflow", matched_kind, kind, query[:len(query) - len(remaining)])
    else:
        record("question", query, "supported published question", query, outcome="unresolved",
               reason="This question contains an unsupported qualifier. Choose a supported published workflow or clarify the scope.")

    exclusion = re.search(r"\b(?:except|excluding|omit|without)\b|除外|以外|除く|含め(?:て|る)|\binclud(?:e|ing)\b.*\bcontrols?\b", remaining if matched_kind else query, re.I)
    if exclusion:
        record("exclusions", exclusion.group(), "fixed publication exclusions", exclusion.group(), outcome="incompatible",
               reason="This immutable workflow cannot apply an additional exclusion or include controls.")

    token = r"((?:19|20)\d{2}(?:-\d{2}-\d{2})?)"
    stop = r"(?=\s+(?:from|during|between|in|using|with|and)\b|[.,?!。？！、]|$)"
    while matched_kind and remaining.strip(" \t\n.,?!。？！、"):
        remaining = remaining.lstrip(" \t\n.,?!。？！、")
        if remaining.startswith("and "):
            remaining = remaining[4:]
        match = re.match(r"(?:from\s+" + token + r"\s+(?:to|through)\s+" + token + r"|between\s+" + token + r"\s+and\s+" + token + r")(?=$|[\s.,?!])", remaining, re.I)
        if match:
            values = [v for v in match.groups() if v]
            dates(values[0], values[1], match.group())
        else:
            match = re.match(r"(?:in|during)\s+" + token + r"(?=$|[\s.,?!])|(?<!\d)((?:19|20)\d{2})年", remaining, re.I)
            if match:
                value = next(v for v in match.groups() if v)
                dates(value, value, match.group(), spatial=kind in SPATIAL)
            else:
                match = re.match(r"(?:in|within|for)\s+(.+?)" + stop, remaining, re.I)
                if match:
                    geography(match[1], match.group())
                else:
                    match = re.match(r"(?:with\s+)?top\s+(\d+)(?:\s+(?:fish|species))?(?:\s+instead)?(?=$|[\s.,?!])|上位\s*(\d+)\s*種", remaining, re.I)
                    if match:
                        panel(next(v for v in match.groups() if v), match.group())
                    else:
                        match = re.match(r"(?:using|with)\s+(.+?)" + stop + r"|(?:手法は|分類手法[:：])([^、。]+)|([^、。]+?)(?:を使用してください|を使用)", remaining, re.I)
                        if match:
                            value = next(v for v in match.groups() if v)
                            method = _norm(value).removesuffix(" assignment method").removesuffix(" method")
                            method = METHOD_ALIASES.get(re.sub(r"[\s-]+", "", method), method)
                            if method in {"qcauto_target", "qcauto_95pct_3nn_target"}:
                                record("assignment_method", method, next(iter(option.get("assignment_methods", [])), recipe.get("assignment_method")), match.group())
                            else:
                                chosen, _ = resolve_protocol(option, value, protocol_id)
                                hints = protocol_hints(value, option)
                                residue = value
                                for name in sorted([*option.get("protocol_ids", []), *[v for values in hints.values() for v in values], "protocol", "protocol_id", "paired-end", "single-end", "paired end", "single end", "rRNA", "ペアエンド", "シングルエンド", "プロトコル", "の", "で"], key=len, reverse=True):
                                    residue = re.sub(re.escape(name), "", residue, flags=re.I)
                                residue = residue.strip(" \t:=：-_")
                                explicit = hints or re.search(r"[a-f0-9]{64}", value, re.I)
                                record("protocol", value, protocol_id, match.group(), outcome="compatible" if chosen and explicit and not residue else "incompatible" if explicit and not residue else "unresolved",
                                       reason="The requested assay protocol does not match the selected registered protocol, or its qualifier is unsupported.")
                        else:
                            record("qualifier", remaining, "registered literal scope qualifiers", remaining, outcome="unresolved",
                                   reason="An explicit qualifier could not be resolved. Clarify it before using fixed publication results.")
                            break
        remaining = remaining[match.end():]

    if protocol_id is not None:
        record("protocol_id", protocol_id, protocol_id if protocol_id in option.get("protocol_ids", []) else "registered protocol", source="selection")
    if scope is not None:
        selections = scope["sources"]
        identity = selections["edna_metabarcoding"].get("analysis_id")
        if identity:
            record("analysis_id", identity, option.get("analysis_id"), source="selection")
        permitted = option.get("cohort_filters", registered_filter_values(recipe))
        for field, value in selections["edna_metabarcoding"]["filters"].items():
            if value is not None:
                record(field, value, permitted.get(field), source="selection",
                       outcome="compatible" if field in permitted and value == permitted[field] else "incompatible")
        if kind in SST:
            for field, value in selections["remote_sensing"]["filters"].items():
                expected = option.get("sst_dataset_id") if field == "dataset_id" else recipe.get(field) if field in {"time_from", "time_to"} else "not supported by this immutable SST panel"
                if value is not None:
                    record("sst." + field, value, expected, source="selection",
                           outcome="compatible" if field in {"dataset_id", "time_from", "time_to"} and expected is not None and value == expected else "incompatible")
    return _finish(kind, option, evidence)
