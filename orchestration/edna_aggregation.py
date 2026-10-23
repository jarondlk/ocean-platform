"""Conservative routing and deterministic answers for exact catalogue questions.

This is a bounded vocabulary, not a natural-language-to-SQL interface. Any
unresolved qualifier fails closed rather than silently querying a wider cohort.
"""

from dataclasses import dataclass
import json
import re

from orchestration.comparison_guard import mentioned_source_types

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
    r"\b(how many|number of|counts?|totals?|summary|summarize|summarise|breakdown|proportion|percentage)\b|何件|いくつ|何サンプル|何個|何種類|何回",
    re.I,
)
EXPLICIT_COUNT = re.compile(
    r"\b(how many|number of|counts?|totals?|breakdown|proportion|percentage)\b|何件|いくつ|何サンプル|何個|何種類|何回",
    re.I,
)
TOPIC = re.compile(r"(?<![a-z])(anemone|edna|mifish|metabarcoding)(?![a-z])", re.I)
WORDS = set(
    """give please tell me you how many what is are the a an of in on from for do we have there and or with without versus vs compare can i add them their these those this that our currently available included include published imported detected recorded reported overall entire whole all database db catalogue catalog ocean platform anemone edna mifish metabarcoding data dataset sample samples sampling physical independent unique source sources occurrence occurrences assay assays assignment assignments detection detections row rows reads read sequencing count counts total totals number summary summarize summarise breakdown proportion percentage coverage locus loci team teams project projects run runs by per each both methods method qcauto qc 3nn nn auto target nontarget non targets controls control negative positive mock community environmental classified classifications classification unknown status empty missing unavailable tables table standards standard internal concentration concentrations copies ml column columns selected current filters filtered scope cohort date range time period location coordinates taxon taxonomy results records versus between anemone's what's what's""".split()
)
WORDS.update({"contain", "contains", "containing", "under", "support", "supported"})


@dataclass(frozen=True)
class AggregatePlan:
    filters: dict
    group_by: tuple = ()
    clarification: str | None = None
    metric: str | None = None


SCOPE_MESSAGE = (
    "I need an explicit scope for that exact count. Set the project, run, taxon, "
    "date or coordinate filters, then ask for a catalogue summary. I can count "
    "source occurrences, assays, classifications, assignments and reads; I cannot "
    "infer physical-sample counts, species richness or ecological abundance from "
    "these records. No database-wide total was substituted."
)
UNSUPPORTED_MESSAGE = (
    "That exact-count request contains unsupported wording or a qualifier that "
    "the selected filters do not resolve. The existing filters were retained. "
    "Use source occurrences, assays, assignment rows or reads, and express "
    "taxon, place and date restrictions in the source filters. No database-wide "
    "total was substituted."
)
CONFLICT_MESSAGE = (
    "The requested method or classification conflicts with the selected filters. "
    "Review the assignment method, sample kind and control status before asking "
    "again. The existing filters were retained; no wider count was substituted."
)


def freshness_question(request: dict) -> bool:
    query = request.get("query", "")
    return bool(TOPIC.search(query) and re.search(
        r"\b(arriv(?:e|ed|al|als)|newly|latest|freshness|recently (?:added|imported|updated))\b|新着|更新|追加|到着", query, re.I))


LOCATION_NOUN = re.compile(
    r"\b(?:(?:sampling|geographic|recorded)\s+)?(?:areas?|locations?|sites?|stations?|points?|positions?|coordinates?(?:\s+(?:pairs?|positions?))?)\b"
    r"|(?:採水|採取|調査|観測)?(?:地点|場所)|サンプリング(?:地点|場所|エリア)|座標(?:位置|組)?", re.I)
LOCATION_COUNT = re.compile(r"\b(?:how many|number of|counts?|totals?)\b|いくつ|何(?:地点|か所|箇所|ヶ所|カ所)|地点数|の(?:総)?数", re.I)
LOCATION_WORDS = set("how many what is are the a an of in on from for do we have there and can could would you please tell me show give available currently recorded reported geographic sampling positions locations ocean platform anemone edna environmental dna mifish metabarcoding catalogue catalog database data dataset datasets count counts total totals number distinct unique selected filtered current project run taxon date time range period scope under by at".split())


def plan_location_count(request: dict) -> AggregatePlan | None:
    """COP17 coordinate coverage, never a count inferred from retrieved examples."""
    query = request.get("query", "")
    if not LOCATION_NOUN.search(query) or not LOCATION_COUNT.search(query):
        return None
    ja = bool(re.search(r"[ぁ-んァ-ン一-龯]", query))
    envelope = request.get("evidence_scope")
    selection = envelope["sources"]["edna_metabarcoding"] if envelope else None
    filters = {key:value for key,value in (selection["filters"] if selection else request).items()
               if key in FILTERS and value is not None}
    filters.setdefault("provider", "anemone")
    options = request.get("aggregation") or {}
    filters.update({key:options[key] for key in ("provider_locus", "provider_team", "target_status", "assay_id") if options.get(key) is not None})
    def clarify(en, jp):
        return AggregatePlan(filters, clarification=jp if ja else en, metric="recorded_locations")
    if selection is not None and not selection["enabled"] or not envelope and request.get("source_type") and request["source_type"] not in EDNA_ALIASES:
        return clarify("Enable ANEMONE eDNA to count its reported coordinate positions. SST coverage is separate from field sampling locations.",
                       "記録された座標位置の数を調べるには、ANEMONE環境DNAを有効にしてください。衛星SSTの範囲は採水地点とは別です。")
    if request.get("analysis_id") or selection and selection.get("analysis_id") or request.get("research_intent"):
        return clarify("Return to free-text search to count ANEMONE coordinate positions with source filters. The selected published analysis has its own fixed cohort.",
                       "自由文検索に戻り、ソースのフィルターを指定してANEMONEの座標位置を数えてください。選択中の公表済み解析は固定の対象データを使用します。")
    if filters["provider"] != "anemone" or request.get("bay") or options.get("group_by"):
        return clarify("This count supports ANEMONE source filters without grouped totals. Review the provider and source filters before asking again.",
                       "この集計はANEMONEのソースフィルターに対応します。グループ別集計には対応していません。プロバイダーとフィルターを確認してください。")
    if len(mentioned_source_types(query)) > 1 or re.search(r"\bsst\b|satellite|sea surface temperature|衛星|海面水温", query, re.I):
        return clarify("ANEMONE reported coordinate positions and SST coverage have different units. Ask for ANEMONE locations separately; SST pixels, dates and regions are not added to sampling positions.",
                       "ANEMONEの記録座標位置とSSTの範囲は単位が異なります。ANEMONEの地点数を別に質問してください。SSTの画素・日付・領域は採水位置に加算しません。")
    if re.search(r"\bdata\s+points?\b", query, re.I) or (re.search(r"\bpoints?\b", query, re.I) and not re.search(r"\b(sampling|geographic|recorded|coordinate)\b", query, re.I)):
        return clarify("Please specify whether points means recorded sampling coordinate positions, source records or SST observations. These units have different totals; no coordinate count was substituted.",
                       "ポイントが採水の記録座標位置・ソース記録・SST観測のどれを指すか指定してください。単位によって総数が異なるため、座標位置の数に置き換えていません。")
    if re.search(r"\b(physical|named|verified|actual|precise)\b|物理|実際|名称|地名|名前|実地点|独立", query, re.I):
        return clarify("Verified physical sites and named sampling areas are not yet curated. I can count distinct reported coordinate positions, with their coordinate-precision limitations.",
                       "物理的な採水地点や名称付き調査区域の対応関係は未確認です。座標の精度上の制約を示して、記録された座標位置の種類数を集計できます。")
    clean = re.sub(r"\benvironmental\s+dna\b", " edna ", query.casefold())
    for value in filters.values():
        if isinstance(value, str) and value:
            clean = re.sub(r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", " ", clean)
    for phrase, token in sorted({"環境dna":"edna", "利用可能な":"available", "利用できる":"available",
                                "記録されている":"recorded", "記録された":"recorded", "データセット":"dataset",
                                "データ":"data", "選択中の":"selected", "選択した":"selected", "教えてください":"please tell me", "示してください":"please show"}.items(), key=lambda item:-len(item[0])):
        clean = clean.replace(phrase, " " + token + " ")
    if re.search(r"\benvironmental\b|環境サンプル|環境試料", clean) and not (filters.get("sample_kind") == "environmental" and filters.get("is_control") is False):
        return clarify("For confirmed environmental samples, set sample kind to environmental and control status to non-control. Unknown classifications are not assumed to be environmental; no wider location count was substituted.",
                       "確認済みの環境サンプルを集計するには、ソースフィルターでサンプル種別をenvironmental、コントロール状態を非コントロールに指定してください。不明な分類を環境サンプルとみなした集計は行いません。")
    clean = re.sub(r"(?:採水|採取|調査|観測)?地点数", " locations count ", clean)
    clean = re.sub(r"の(?:総)?数", " count ", clean)
    clean = LOCATION_COUNT.sub(" count ", clean)
    clean = LOCATION_NOUN.sub(" locations ", clean)
    clean = re.sub(r"には|では|の|は|が|を|に|ですか|ありますか|ある|あります|？|。", " ", clean)
    words = re.findall(r"[\w]+(?:'[\w]+)?", clean)
    unsupported = not words or any(word not in LOCATION_WORDS for word in words)
    # Qualifiers must already have concrete source filters, not just filler words.
    required = ((r"\bproject\b", ("provider_project_id",)), (r"\brun\b", ("provider_run_id",)),
                (r"\btaxon\b", ("taxon",)), (r"\b(date|time|range|period)\b", ("time_from", "time_to")))
    missing = any(re.search(pattern, clean) and not any(key in filters for key in keys) for pattern,keys in required)
    if ("selected" in words or "filtered" in words or "current" in words) and set(filters) == {"provider"}:
        missing = True
    if unsupported or missing or re.search(r"[<>!=]|\b(by|per|each)\b", clean):
        return clarify("I can count distinct reported ANEMONE coordinate positions. Set project, run, taxon, date or coordinate restrictions in the source filters; unsupported place names, thresholds and other qualifiers need clarification. No total was inferred from retrieved examples.",
                       "ANEMONEに記録された座標位置の種類数を集計できます。プロジェクト・ラン・分類群・日付・座標範囲はソースのフィルターで指定してください。未対応の地名・閾値などは条件の確認が必要です。検索結果の一部から総数を推定していません。")
    if "is_control" not in filters and "sample_kind" not in filters:
        filters["exclude_explicit_controls"] = True
    return AggregatePlan(filters, metric="recorded_locations")


def render_location_answer(bundle, query=""):
    payload = bundle["payload"]
    value = payload["summary"]["locations"]
    cite = "[aggregate_edna_" + bundle["aggregate_id"] + "]"
    def label(v):
        return re.sub(r"([\\`*{}\[\]()<>|])", r"\\\1", str(v).replace("\n", " ").replace("\r", " "))
    count = value["distinct_coordinate_pairs"]
    ja = bool(re.search(r"[ぁ-んァ-ン一-龯]", query))
    excludes = value["control_policy"] == "exclude_explicit_controls"
    fields = {"provider":"Provider", "sample_id":"Sample ID", "provider_project_id":"Project", "provider_run_id":"Run",
              "assignment_method":"Assignment method", "taxon":"Taxon", "sample_kind":"Sample kind", "is_control":"Control status",
              "time_from":"From", "time_to":"To", "lat_min":"Minimum latitude", "lat_max":"Maximum latitude",
              "lon_min":"Minimum longitude", "lon_max":"Maximum longitude", "provider_locus":"Marker namespace",
              "provider_team":"Team", "assay_id":"Assay", "target_status":"Target status"}
    scope = "; ".join(f"{fields.get(key,key)}={label(v)}" for key,v in sorted(payload["filters"].items()) if key != "exclude_explicit_controls")
    precision = "; ".join(f"{label(k)}={v:,}" for k,v in sorted(value["coordinate_precision"].items())) or ("なし" if ja else "none")
    if ja:
        lines = [f"選択条件に一致する公表済みANEMONEデータには、**異なる記録座標位置が{count:,}か所**あります。{cite}",
                 f"同じ緯度・経度における繰り返し採取や複数のアッセイ・解析手法は重複して数えません。物理的な採水地点や名称付き調査区域の種類数は未確認です。{cite}",
                 ("明示的にコントロールと分類された記録を除外しています。" if excludes else "コントロール・分類状態は指定したソースフィルターに従います。") +
                 f"対象のソース記録は{value['source_occurrences']:,}件、うち有効な座標が{value['valid_coordinate_occurrences']:,}件、座標欠損が{value['missing_coordinate_occurrences']:,}件、無効な座標が{value['invalid_coordinate_occurrences']:,}件です。欠損・無効な座標は地点数に含みません。{cite}",
                 f"コントロール状態が不明な記録は{value['unknown_control_status']:,}件あり、確認済みの環境サンプルとはみなしていません。座標精度の記録件数：{precision}。{cite}"]
        if value["coordinate_precision"].get("provider_grid_unconfirmed"):
            lines.append(f"プロバイダーのグリッド座標を含みます。異なる座標位置の数は、厳密な物理的採水地点の数を保証しません。{cite}")
        lines.append(f"適用条件：{scope}。{cite}")
    else:
        lines = [f"The published ANEMONE catalogue matching the selected filters contains **{count:,} distinct reported coordinate positions**. {cite}",
                 f"Exact stored latitude/longitude pairs are counted once across repeated sampling dates, assays and assignment methods. Physical-site identities and named sampling areas remain unverified. {cite}",
                 ("Explicitly classified controls are excluded. " if excludes else "Control/classification scope follows the explicit source filters. ") +
                 f"There are {value['source_occurrences']:,} matching source records: {value['valid_coordinate_occurrences']:,} with valid coordinates, {value['missing_coordinate_occurrences']:,} with missing coordinates and {value['invalid_coordinate_occurrences']:,} with invalid coordinates. Missing/invalid positions are excluded. {cite}",
                 f"Control status is unknown for {value['unknown_control_status']:,} records; they are not assumed to be confirmed environmental samples. Coordinate-precision record counts: {precision}. {cite}"]
        if value["coordinate_precision"].get("provider_grid_unconfirmed"):
            lines.append(f"This includes provider grid coordinates, which do not establish distinct physical sampling sites. {cite}")
        lines.append(f"Applied source filters: {scope}. {cite}")
    return "\n\n".join(lines)


def plan_aggregation(request: dict) -> AggregatePlan | None:
    query = request.get("query", "")
    envelope = request.get("evidence_scope")
    if envelope:
        selected = [family for family, selection in envelope["sources"].items() if selection["enabled"]]
        if request.get("aggregation") is None and selected != ["edna_metabarcoding"] and not TOPIC.search(query):
            return None
        selection = envelope["sources"]["edna_metabarcoding"]
        if not selection["enabled"]:
            return None
        request = {**request, **selection["filters"], "analysis_id": selection.get("analysis_id"),
                   "source_type": "edna_metabarcoding"}
    options = request.get("aggregation")
    forced = options is not None
    # A summary of explicitly named families is ordinary evidence synthesis.
    # Preserve fail-closed catalogue routing for explicit counts and forced
    # aggregation; selecting siblings alone does not change eDNA summaries.
    if not forced and len(mentioned_source_types(query)) > 1 and not EXPLICIT_COUNT.search(query):
        return None
    if not forced and re.search(r"\b(mean|imply|indicate|interpret|higher|more fish|abundance)\b|意味|魚が多|個体数", query, re.I):
        return None
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
    # Resolve only a bounded set of Japanese catalogue questions. Unrecognized
    # qualifiers still require explicit filters instead of a wider total.
    if re.search(r"[ぁ-んァ-ン一-龯]", query):
        replacements = {"ANEMONE": "anemone", "アッセイ": "assays", "サンプル": "samples",
                        "読み取り": "reads", "リード": "reads", "コントロール": "controls",
                        "件数": "count", "何件": "how many", "いくつ": "how many",
                        "何サンプル": "how many samples", "物理的な": "physical", "未知": "unknown"}
        for phrase in sorted(replacements, key=len, reverse=True):
            query = query.replace(phrase, " " + replacements[phrase] + " ")
        query = re.sub(r"には|では|の|は|が|を|に|ですか|ありますか|ある|あります|？|。", " ", query)
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
    if any(key in filters and filters[key] != value for key, value in enums.items()):
        return AggregatePlan(filters, clarification=CONFLICT_MESSAGE)
    resolved_filters = {**filters, **enums}
    if (
        resolved_filters.get("sample_kind") == "environmental"
        and resolved_filters.get("is_control") is True
        or resolved_filters.get("assignment_method")
        and resolved_filters.get("target_status")
        and not resolved_filters["assignment_method"].endswith("_" + resolved_filters["target_status"])
    ):
        return AggregatePlan(filters, clarification=CONFLICT_MESSAGE)
    filters = resolved_filters
    inferred = []
    grouping = re.search(r"\b(?:by|per|in each|for each)\s+(.+)", query)
    if grouping:
        tail = re.findall(r"[a-z]+", grouping[1])
        if any(
            word not in {*GROUPS, "and", "then", "per", "method", "methods"}
            for word in tail
        ):
            return AggregatePlan(filters, clarification=UNSUPPORTED_MESSAGE)
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
    # "Occurrences containing <selected taxon>" has an exact canonical
    # predicate. "Samples containing reads" could instead exclude empty
    # tables; never infer that different cohort from a filler verb.
    if any(word in words for word in ("contain", "contains", "containing")) and "taxon" not in filters:
        return AggregatePlan(filters, tuple(group_by), UNSUPPORTED_MESSAGE)
    if not words or any(word not in WORDS for word in words):
        return AggregatePlan(filters, tuple(group_by), UNSUPPORTED_MESSAGE)
    if any(word in words for word in ("selected", "filtered")) and set(filters) == {"provider"}:
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
        return AggregatePlan(filters, tuple(group_by), UNSUPPORTED_MESSAGE)
    return AggregatePlan(filters, tuple(group_by))


def evidence_document(bundle):
    identity, payload = bundle["aggregate_id"], bundle["payload"]
    return {
        "id": "aggregate_edna_" + identity,
        "title": "Exact ANEMONE geographic coverage" if payload.get("metric") == "catalogue_geography" else "Exact ANEMONE recorded-coordinate count" if payload.get("metric") == "recorded_locations" else "Exact ANEMONE catalogue summary",
        "source_type": "analysis",
        "source_family": "edna_metabarcoding",
        "covered_source_types": ["edna_metabarcoding"],
        "analysis_type": "edna_catalogue_geography" if payload.get("metric") == "catalogue_geography" else "edna_recorded_location_count" if payload.get("metric") == "recorded_locations" else "edna_catalogue_summary",
        "aggregate_id": identity,
        "metadata": payload["filters"],
        "text": json.dumps({"filters": payload["filters"], "summary": payload["summary"],
                            "limitations": "Exact catalogue records for these filters. Reads are not organism counts; unknown controls are not environmental. Collection dates do not establish data arrival."}, sort_keys=True, ensure_ascii=False),
    }


def _asks_unknown_control_status(query):
    if "未知" in query:
        return True
    # Search each line once. A greedy regex starting at every repeated
    # "unknown" can take quadratic time when no control/status follows.
    for line in query.casefold().split("\n"):
        _, marker, suffix = line.partition("unknown")
        if marker and ("control" in suffix or "status" in suffix):
            return True
    return False


def render_answer(bundle, query=""):
    if bundle["payload"].get("metric") == "catalogue_geography":
        from orchestration.catalogue_geography import render_geography_answer
        return render_geography_answer(bundle, query)
    if bundle["payload"].get("metric") == "recorded_locations":
        return render_location_answer(bundle, query)
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
    lead = None
    if re.search(r"physical|物理|independent|unique samples", query, re.I):
        lead = "The number of distinct physical samples is unresolved: source occurrences and assays do not establish unique physical samples. " + cite
    elif _asks_unknown_control_status(query):
        lead = f"**{summary['unknown_control_status']:,} source occurrences have unknown control status**. Unknown does not mean environmental or non-control. {cite}"
    elif re.search(r"\bstandards?\b", query, re.I):
        standards = summary['internal_standards']
        lead = f"**{standards['reads']:,} internal-standard reads across {standards['rows']:,} rows** in the matching assays. Standards are separate from biological assignments and do not establish calibration validity. {cite}"
    elif re.search(r"\bconcentrations?\b|copies", query, re.I):
        lead = "Concentration records by assignment method: " + ("; ".join(
            f"{label(row['assignment_method'])}: {row.get('concentration_records', 0):,} reported, {row.get('concentration_missing', 0):,} missing, {row.get('concentration_column_absent', 0):,} with the source column absent"
            for row in summary['methods']) or "no matching assignment records for this scope") + ". Missing or absent does not mean zero. " + cite
    elif re.search(r"\btables?\b", query, re.I):
        lead = "Community tables by assignment method: " + ("; ".join(
            f"{label(row['assignment_method'])}: {row['empty_tables']:,} valid empty tables of {row['available_tables']:,} available tables"
            for row in summary['community_availability']) or "no documented available tables for this scope") + ". Valid empty tables are distinct from unavailable tables. " + cite
    elif re.search(r"\benvironmental\b", query, re.I):
        lead = f"**{summary['environmental_classified']:,} explicitly classified environmental source occurrences**. This is recorded classification, not biological absence. {cite}"
    elif re.search(r"\bcontrols?\b", query, re.I):
        lead = f"**{summary['controls']:,} explicitly classified control source occurrences**. Controls do not establish contamination-free samples. {cite}"
    elif re.search(r"\bassignments?|assays?|occurrences?\b", query, re.I) and re.search(r"\breads?\b", query, re.I):
        lead = f"**{summary['source_occurrences']:,} source occurrences and {summary['assays']:,} matching assays**; " + ("; ".join(
            f"{label(row['assignment_method'])}: {row.get('assignment_rows', 0):,} assignment rows and {row.get('read_count_sum', 0):,} sequencing reads"
            for row in summary['methods']) or "0 matching assignment rows and sequencing reads recorded") + ". Physical sample identity remains unresolved; reads are not organism counts. " + cite
    elif re.search(r"\bassignments?\b", query, re.I):
        lead = "Assignment rows by method: " + ("; ".join(
            f"{label(row['assignment_method'])}={row.get('assignment_rows', 0):,}"
            for row in summary['methods']) or "0 matching assignment rows") + ". Alternative methods share sequence evidence. " + cite
    elif re.search(r"\breads?\b|リード|読み取り", query, re.I):
        lead = "Sequence reads by assignment method: " + ("; ".join(
            f"{label(row['assignment_method'])}={row.get('read_count_sum', 0):,}"
            for row in summary['methods']) or "0 sequencing reads recorded in matching assignments") + ". Methods share reads and must not be added. Reads are not organism counts. " + cite
    lines = [
        f"For the published OCEAN catalogue with filters {scope}: **{summary['source_occurrences']:,} source occurrences and {summary['assays']:,} matching assays**. The number of distinct physical samples is unresolved. {cite}",
        f"Classifications: {summary['controls']:,} controls, {summary['unknown_control_status']:,} with unknown control status, and {summary['environmental_classified']:,} explicitly classified environmental occurrences. Kinds: "
        + (
            ", ".join(label(k) + f"={v:,}" for k, v in summary["sample_kinds"].items())
            or "none"
        )
        + f". {cite}",
    ]
    if payload['filters'].get('sample_kind') == 'environmental' or payload['filters'].get('is_control') is False:
        lines.append(
            "Unclassified source occurrences are excluded by the selected environmental/non-control filter. "
            "Zero unknowns within this cohort does not mean the published catalogue has no unclassified records. "
            + cite
        )
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
    return "\n\n".join(([lead] if lead else []) + lines)
