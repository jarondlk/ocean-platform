"""Scoped catalogue geography, with unknown area membership kept explicit.

This answers coverage questions from immutable full-cohort evidence. It does
not turn provider labels or reverse-geocoded guesses into bay memberships.
"""

from dataclasses import replace
import re

from orchestration.comparison_guard import mentioned_source_types
from orchestration.edna_aggregation import plan_location_count

# Geographic nouns alone are not intent: "Otsuchi Bay" is also a normal
# sample-search qualifier. Match the requested unit and relationship first;
# only then do the existing scope checks decide whether it is answerable.
NAMED_TARGET = (
    r"(?:named\s+(?:sampling\s+)?(?:areas?|regions?|locations?|sites?)"
    r"|bays?|coastal\s+(?:areas?|regions?))"
)
AREA = re.compile(
    r"\b(?:areas?|regions?|locations?|sites?|coordinates?|positions?|bays?)\b",
    re.I,
)
SAMPLING = re.compile(
    r"\bsampl(?:e|es|ing)\b|anemone|edna|\b(?:locations?|coordinates?|positions?)\b|採水|採取|サンプリング|座標|地点",
    re.I,
)
WORDS = set(
    """a an the all any are is does do our your these those this that their its there available have has we they it please can could would you tell me show give what which how many number of total named names name sampling sample samples data dataset datasets catalogue catalog database db anemone edna environmental dna mifish metabarcoding ocean platform published recorded reported represented geographic geographical geographically geography area areas region regions bay bays coastal coast locations location sites site positions position coordinates coordinate and or from around in at to for with by per each same one single only just different multiple close together near nearby where cover covered covering covers coverage collected collection collect distributed distribution spread extent widely far across latitude longitude selected filtered current filters scope matching project run taxon date time range period during""".split()
)
JP = {
    "名前のついた": " named ",
    "名前がある": " named ",
    "名称がある": " named ",
    "名前のある": " named ",
    "名称付き": " named ",
    "名前付き": " named ",
    "採水エリア": " sampling areas ",
    "採水地域": " sampling regions ",
    "採水データ": " sampling data ",
    "採取データ": " sampling data ",
    "採水地点": " locations ",
    "採取地点": " locations ",
    "サンプリング": " sampling ",
    "どの地域": " which regions ",
    "同じ地域": " same area ",
    "同じ場所": " same area ",
    "同じ湾": " same bay ",
    "すべて": " all ",
    "全て": " all ",
    "全部": " all ",
    "いくつ": " how many ",
    "何か所": " how many ",
    "何箇所": " how many ",
    "どこ": " where ",
    "分布していますか": " distributed ",
    "分布している": " distributed ",
    "ありますか": " available ",
    "利用可能な": " available ",
    "利用できる": " available ",
    "教えてください": " please tell me ",
    "示してください": " please show ",
    "ものですか": " ",
    "からですか": " from ",
    "ですか": " ",
    "周辺": " around ",
    "周り": " around ",
    "地域": " regions ",
    "エリア": " areas ",
    "湾": " bays ",
    "地点": " locations ",
    "座標": " coordinates ",
    "データ": " data ",
    "近く": " near ",
    "範囲": " extent ",
    "に": " ",
    "の": " ",
    "は": " ",
    "が": " ",
    "を": " ",
    "で": " ",
    "と": " and ",
    "か": " ",
}


def _intent_text(query):
    """Normalize supported Japanese geography phrases for intent only."""
    text = query.casefold()
    for phrase, value in sorted(JP.items(), key=lambda item: -len(item[0])):
        text = text.replace(phrase, value)
    return " ".join(text.split())


def _named_area_question(query):
    text = _intent_text(query)
    # Count/list the *areas*, rather than samples or taxa mentioned near a bay.
    if re.search(
        r"\b(?:how many|number of|counts? of|totals? of)\s+" + NAMED_TARGET
        + r"\b|\b(?:which|what)\s+(?:(?:are|is)\s+)?(?:the\s+)?"
        + NAMED_TARGET + r"\b|\b(?:show|list|name)\s+(?:me\s+)?"
        r"(?:all\s+)?(?:the\s+)?" + NAMED_TARGET + r"\b",
        text,
    ):
        return True
    # Japanese count questions place the quantity after the requested unit.
    if re.search(NAMED_TARGET + r"\s+how many\b", text):
        return True
    if re.search(r"\b(?:fish|species|taxa|taxon|genes|proteins)\b|魚|種名|分類", query, re.I):
        return False
    return bool(re.search(
        r"\b(?:what|which)\s+(?:are\s+)?(?:the\s+)?names?\s+of\s+"
        r"(?:the\s+)?(?:sampling\s+)?(?:areas?|regions?|locations?|sites?)\b"
        r"|\b(?:what|which)\s+(?:sampling\s+)?(?:areas?|regions?|locations?|sites?)"
        r"\s+(?:have\s+names|are\s+named)\b",
        text,
    ))


def _coverage_question(query):
    text = _intent_text(query)
    if not SAMPLING.search(query) or not AREA.search(text):
        return False
    relation = re.search(
        r"\b(?:same|one|single)\s+(?:(?:sampling|coastal|geographic)\s+)?"
        r"(?:area|region|location|site|bay|position)\b|\bclose together\b",
        text,
    )
    # "one sample" and "where was a sample collected" do not ask about
    # collective coverage. Require a geographic relation and collective subject.
    collective = re.search(
        r"^(?:are|is|does|do)\s+(?:(?:all|the|these|those|our|anemone|edna)\s+)*"
        r"(?:samples|sampling\s+(?:data|locations|sites|positions)|locations|coordinates)\b",
        text,
    )
    collective_statement = re.search(
        r"\b(?:all|these|those)\s+(?:(?:the|anemone|edna)\s+)*"
        r"(?:samples|sampling\s+(?:data|locations|sites|positions)|locations|coordinates)\b"
        r"|\b(?:sampling data|locations|coordinates)\s+all\b",
        text,
    )
    if relation and (collective or collective_statement):
        return True
    # A collective place-membership question is geography, but a sample's
    # suitability or fish detections are not. Require the spatial predicate,
    # rather than treating every "samples from <bay>" phrase as coverage.
    if collective and re.search(r"\ball\b", text) and re.search(
        r"\b(?:in|from|around|across)\b[^?.!;\n]*"
        r"\b(?:areas?|regions?|locations?|sites?|bays?)\s*[?.!]*$",
        text,
    ):
        return True
    if collective and re.search(
        r"\bcover(?:age|s|ed|ing)?\b|\b(?:distributed|spread)\s+(?:across|over|throughout|around)\b",
        text,
    ):
        return True
    return bool(re.search(
        r"\b(?:where|how widely|how far apart)\s+(?:are|is)\s+"
        r"(?:(?:the|all|these|our|anemone|edna|sampling|recorded)\s+)*"
        r"(?:locations|sites|coordinates|positions)\b"
        r"|\b(?:geographic(?:al)?\s+(?:coverage|extent|distribution)|coordinate extent)\b"
        r"|\b(?:sampling\s+)?(?:locations|sites|coordinates|positions)\s+"
        r"(?:which regions\s+)?(?:distributed|spread|extent)\b",
        text,
    ))


def plan_catalogue_geography(request):
    query = request.get("query", "")
    if not (_named_area_question(query) or _coverage_question(query)):
        return None
    ja = bool(re.search(r"[ぁ-んァ-ン一-龯]", query))
    base = plan_location_count(
        {
            **request,
            "query": "採水地点はいくつありますか？"
            if ja
            else "How many sampling locations?",
        }
    )
    plan = replace(base, metric="catalogue_geography")
    if plan.clarification:
        return plan

    def clarify(en, jp):
        return replace(plan, clarification=jp if ja else en)

    if re.search(
        r"\b(?:physical|verified|actual|precise)\b|物理|実際|実地点", query, re.I
    ):
        return clarify(
            "Verified physical-site and named-area membership is not established by this catalogue. Ask about the recorded coordinate coverage instead.",
            "このカタログでは物理的な採水地点や名称付き地域の対応関係は未確認です。記録された座標の範囲について質問してください。",
        )
    if len(mentioned_source_types(query)) > 1 or re.search(
        r"\bsst\b|satellite|sea surface temperature|衛星|海面水温", query, re.I
    ):
        return clarify(
            "Ask about ANEMONE sampling geography separately. Field positions and satellite SST coverage have different units; no combined area count was substituted.",
            "ANEMONEの採水地理について別に質問してください。採水位置と衛星SSTの範囲は単位が異なるため、合計の地域数には置き換えていません。",
        )
    clean = re.sub(r"\benvironmental\s+dna\b", " edna ", query.casefold())
    for value in plan.filters.values():
        if isinstance(value, str) and value:
            clean = re.sub(
                r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)", " ", clean
            )
    for phrase, value in sorted(JP.items(), key=lambda item: -len(item[0])):
        clean = clean.replace(phrase, value)
    words = re.findall(r"[\w]+(?:'[\w]+)?", clean)
    if "environmental" in words and not (
        plan.filters.get("sample_kind") == "environmental"
        and plan.filters.get("is_control") is False
    ):
        return clarify(
            "For confirmed environmental samples, set sample kind to environmental and control status to non-control. Unknown classifications are not treated as environmental.",
            "確認済み環境サンプルには、サンプル種別environmentalと非コントロールの条件を指定してください。不明な分類を環境サンプルとはみなしません。",
        )
    required = (
        (r"\bproject\b", ("provider_project_id",)),
        (r"\brun\b", ("provider_run_id",)),
        (r"\btaxon\b", ("taxon",)),
        (r"\b(?:date|time|range|period|during)\b", ("time_from", "time_to")),
    )
    missing = any(
        re.search(pattern, clean) and not any(key in plan.filters for key in keys)
        for pattern, keys in required
    )
    if any(word in words for word in ("selected", "filtered", "current")) and set(
        plan.filters
    ) <= {"provider", "exclude_explicit_controls"}:
        missing = True
    if (
        not words
        or missing
        or any(word not in WORDS for word in words)
        or re.search(r"[<>!=]", clean)
    ):
        return clarify(
            "I can describe the selected ANEMONE catalogue's recorded coordinate coverage and explain whether a named-area total is established. Place-name, date and ecological restrictions must be resolved in source filters; no wider-area result was substituted.",
            "選択したANEMONEカタログの記録座標の範囲と、名称付き地域数を確定できるかを説明できます。地名・日付・生態条件はソースフィルターで指定してください。広い範囲の結果には置き換えていません。",
        )
    return plan


def render_geography_answer(bundle, query=""):
    payload = bundle["payload"]
    geography = payload["summary"]["geography"]
    locations = geography["locations"]
    count = locations["distinct_coordinate_pairs"]
    extent = geography["coordinate_extent"]
    cite = "[aggregate_edna_" + bundle["aggregate_id"] + "]"
    ja = bool(re.search(r"[ぁ-んァ-ン一-龯]", query))
    named = _named_area_question(query)

    def emit(line):
        return line + " " + cite

    if ja:
        area = emit(
            "**名称付きの湾・沿岸地域の数は、この公表済みANEMONEカタログでは確定していません。** この集計は地域境界や確認済みの所属関係を持たないため、記録座標の数を湾の数として数えません。これは地域数がゼロという意味ではありません。"
        )
        lead = emit(
            f"選択条件に一致するデータには**異なる記録座標位置が{count:,}か所**あります。これは検索結果の一部ではなく、対象カタログ全体の集計です。"
        )
        lines = [area, lead] if named else [lead]
        if count:
            lines.append(
                emit(
                    f"保存された座標の範囲は、緯度{extent['lat_min']:.6f}～{extent['lat_max']:.6f}度、経度{extent['lon_min']:.6f}～{extent['lon_max']:.6f}度です。"
                )
            )
            distance = geography["latitude_extreme_separation_km"]
            if distance is not None and distance > 0:
                lines.append(
                    emit(
                        f"記録上の最北・最南の座標位置は約{distance:,.1f} km離れています。この距離は実在する記録座標の2点間の概算であり、全地点間の最大距離や連続して採水した範囲ではありません。"
                    )
                )
            elif count == 1:
                lines.append(
                    emit(
                        "有効な座標を持つ対象記録は同じ保存座標を共有します。これだけで単一の物理的な採水地点や湾とは確認できません。"
                    )
                )
            else:
                lines.append(
                    emit(
                        "異なる記録座標位置を複数含みます。この距離だけで単一の地域や湾への所属は確認できません。"
                    )
                )
        else:
            lines.append(
                emit(
                    "対象記録には利用できる座標がないため、地理的な広がりは評価できません。"
                )
            )
        if not named:
            lines.append(area)
        lines.append(
            emit(
                (
                    "明示的にコントロールと分類された記録は除外しています。"
                    if locations["control_policy"] == "exclude_explicit_controls"
                    else "分類・コントロール条件は指定したフィルターに従います。"
                )
                + f"対象ソース記録は{locations['source_occurrences']:,}件、有効座標は{locations['valid_coordinate_occurrences']:,}件、座標欠損は{locations['missing_coordinate_occurrences']:,}件、無効座標は{locations['invalid_coordinate_occurrences']:,}件です。座標のない記録の場所は未確認です。"
            )
        )
        lines.append(
            emit(
                "境界ボックスは座標の外接範囲を表し、その内部全体が調査済みという意味ではありません。プロバイダーのグリッド座標を含むため、厳密な採水地点の同一性や湾への所属は保証しません。"
            )
        )
    else:
        area = emit(
            "**The number of named bays or coastal areas is not established by this published ANEMONE catalogue.** This aggregate has no reviewed area boundaries or memberships, so recorded coordinate positions are not counted as bays. This does not mean there are zero geographic areas."
        )
        lead = emit(
            f"The data matching the selected filters contain **{count:,} distinct reported coordinate positions**, counted across the full matching catalogue rather than a few retrieved examples."
        )
        lines = [area, lead] if named else [lead]
        if count:
            lines.append(
                emit(
                    f"Stored coordinates range from latitude {extent['lat_min']:.6f} to {extent['lat_max']:.6f} degrees and longitude {extent['lon_min']:.6f} to {extent['lon_max']:.6f} degrees."
                )
            )
            distance = geography["latitude_extreme_separation_km"]
            if distance is not None and distance > 0:
                lines.append(
                    emit(
                        f"The northernmost and southernmost recorded positions are approximately **{distance:,.1f} km apart**. This is an approximate great-circle separation between two recorded positions, not the maximum distance between every pair or continuous sampled coverage."
                    )
                )
            elif count == 1:
                lines.append(
                    emit(
                        "All matching records with usable coordinates share one stored position. That alone does not verify one physical site or bay."
                    )
                )
            else:
                lines.append(
                    emit(
                        "The records contain multiple distinct coordinate positions. This distance alone does not establish whether they belong to a single area or bay."
                    )
                )
        else:
            lines.append(
                emit(
                    "No matching records have usable coordinates, so their geographic spread cannot be assessed."
                )
            )
        if not named:
            lines.append(area)
        lines.append(
            emit(
                (
                    "Explicitly classified controls are excluded. "
                    if locations["control_policy"] == "exclude_explicit_controls"
                    else "Classification and control scope follows the selected filters. "
                )
                + f"The scope contains {locations['source_occurrences']:,} source records: {locations['valid_coordinate_occurrences']:,} with valid coordinates, {locations['missing_coordinate_occurrences']:,} with missing coordinates and {locations['invalid_coordinate_occurrences']:,} with invalid coordinates. Records without usable coordinates remain unlocated."
            )
        )
        lines.append(
            emit(
                "The bounding box describes the extent of recorded coordinates; its interior is not necessarily sampled. Provider grid coordinates do not establish precise physical sites or membership in named bays."
            )
        )
    # Reuse the existing renderer for exact applied filters and classification
    # caveats, without presenting a second location-count answer.
    from orchestration.edna_aggregation import render_location_answer

    location_payload = {
        **payload,
        "summary": {**payload["summary"], "locations": locations},
    }
    detail = render_location_answer(
        {"aggregate_id": bundle["aggregate_id"], "payload": location_payload}, query
    )
    lines.extend([detail.split("\n\n")[3], detail.split("\n\n")[-1]])
    return "\n\n".join(lines)
