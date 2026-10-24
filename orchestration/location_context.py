"""Optional example/map context intents, isolated from ordinary sample retrieval."""

from dataclasses import replace
import re

from orchestration.catalogue_geography import (
    _named_area_question,
    plan_catalogue_geography,
)
from orchestration.edna_aggregation import plan_location_count, LOCATION_COUNT

NUMBERS = {
    name: index
    for index, name in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
}
NUMBER = r"(?:[0-9]+|" + "|".join(NUMBERS) + r")"
EXAMPLES = re.compile(
    r"(?:(?:and|please)\s+)*(?:show|list|give)(?:\s+me)?\s+(?:(?P<n>"
    + NUMBER
    + r")\s+)?(?:(?:example|sample)\s+)?(?:sampling\s+)?(?:locations?|sites?|coordinate positions?|coordinates?)(?:\s+(?:as examples|for example))?",
    re.I,
)
JP_EXAMPLES = re.compile(
    r"(?:(?P<n>[0-9]+)(?:か所|箇所|地点)(?:の)?(?:例|具体例)(?:を)?|(?:採水地点|地点)?(?:の)?(?:例|具体例)(?:を)?(?P<after>[0-9]+)?(?:か所|箇所|地点)?)(?:示してください|教えてください|見せてください|挙げてください)"
)
MODIFIERS = re.compile(
    r"\b(?:mapped|generalized|generalised|approximate|approximately|map-derived|map based|map-based)\b|地図から推定した|地図由来の|概略の|おおよその",
    re.I,
)


def plan_context(request):
    query = request.get("query", "")
    clean = MODIFIERS.sub(" ", query)
    matches = list(EXAMPLES.finditer(clean)) + list(JP_EXAMPLES.finditer(clean))
    named = _named_area_question(clean)
    if not matches and not named:
        return None
    count = 0
    if matches:
        values = []
        for match in matches:
            number = match.groupdict().get("n") or match.groupdict().get("after")
            values.append(
                NUMBERS.get(number.casefold(), None)
                if number and not number.isdigit()
                else int(number)
                if number
                else 10
            )
        count = values[0]
        # Remove only the recognized presentation clause; retain all scope words.
        for match in sorted(matches, key=lambda item: item.start(), reverse=True):
            clean = clean[: match.start()] + " " + clean[match.end() :]
        clean = re.sub(r"^[\s.,;!?。？]+|[\s.,;!?。？]+$", "", clean)
        clean = re.sub(r"\b(?:and|please)\s*$", "", clean, flags=re.I)
    if named:
        base = plan_catalogue_geography({**request, "query": clean})
    else:
        if not LOCATION_COUNT.search(clean):
            clean = clean + " How many sampling locations?"
        base = plan_location_count({**request, "query": clean})
    if base is None:
        return None
    plan = replace(
        base,
        metric="location_context",
        context_options={"example_limit": count, "area_groups": named},
    )
    if matches and (len(set(values)) != 1 or not 1 <= count <= 20):
        return replace(
            plan,
            clarification="地点の例は1～20か所を指定してください。総数の対象範囲は変更していません。"
            if re.search(r"[ぁ-んァ-ン一-龯]", query)
            else "Please request between 1 and 20 example locations with one consistent example limit. The total-count scope has not been changed.",
        )
    return plan


def label(value):
    return re.sub(
        r"([\\`*{}\[\]()<>|])",
        r"\\\1",
        str(value).replace("\n", " ").replace("\r", " ").replace("|", "｜"),
    )


def render(bundle, query=""):
    from orchestration.edna_aggregation import render_location_answer

    payload = bundle["payload"]
    context = payload["summary"]["location_context"]
    geography = payload["summary"]["geography"]
    locations = geography["locations"]
    opts = context["options"]
    ja = bool(re.search(r"[ぁ-んァ-ン一-龯]", query))
    cite = "[aggregate_edna_" + bundle["aggregate_id"] + "]"
    count = locations["distinct_coordinate_pairs"]
    lines = [
        f"選択条件に一致する公表済みANEMONEデータには、**異なる記録座標位置が{count:,}か所**あります。{cite}"
        if ja
        else f"The published ANEMONE catalogue matching the selected filters contains **{count:,} distinct reported coordinate positions**. {cite}"
    ]
    groups = context["groups"]
    if opts["area_groups"]:
        from orchestration.catalogue_geography import render_geography_answer

        original = render_geography_answer(bundle, query).split("\n\n")
        # Preserve the canonical named-area caveat, extent and separation facts.
        lines = original[:2]
        n = len(groups["generalized_area_groups"])
        lines.append(
            (
                f"地図から一般化した参考地域名のグループは**{n:,}種類**です。{groups['mapped_positions']:,}座標位置に参考地域名を対応付け、{groups['unassigned_positions']:,}座標位置は未割り当てです。これはANEMONEが確認した地域総数ではありません。"
                if ja
                else f"The map-derived layer supplies **{n:,} generalized reference-name groups** for {groups['mapped_positions']:,} coordinate positions; {groups['unassigned_positions']:,} positions remain unassigned. This is not a complete or ANEMONE-verified named-area total."
            )
            + " "
            + cite
        )
        if n:
            table = [
                "| 地図由来の参考地域 | 記録座標位置数 |"
                if ja
                else "| Generalized map area | Recorded positions |",
                "| --- | ---: |",
            ]
            ordered_groups = sorted(
                groups["generalized_area_groups"],
                key=lambda row: (
                    -row["coordinate_positions"],
                    context["features"][row["feature_id"]]["name"],
                ),
            )
            for row in ordered_groups[:20]:
                feature = context["features"][row["feature_id"]]
                name = (
                    feature.get("name_ja")
                    if ja and feature.get("name_ja")
                    else feature["name"]
                )
                table.append(f"| {label(name)} | {row['coordinate_positions']} |")
            lines.append("\n".join(table) + "\n\n" + cite)
            if n > 20:
                lines.append(
                    (
                        f"{n}グループ中20グループを表示しています。すべての対応関係は引用の詳細で確認できます。"
                        if ja
                        else f"Showing 20 of {n} groups; all associations are retained in the cited evidence."
                    )
                    + " "
                    + cite
                )
    if opts["example_limit"]:
        examples = context["positions"][: opts["example_limit"]]
        lines.append(
            (
                f"**地点の例：{len(examples)}か所**（指定：{opts['example_limit']}か所）。緯度・経度の昇順で選び、同じ座標の繰り返し採取は1行にまとめています。各行は対象条件に一致する1件のソース記録で裏付けています。"
                if ja
                else f"**{len(examples)} example locations** (requested: {opts['example_limit']}). Selected in latitude/longitude order, with one matching source record per distinct stored position; these examples are not random or representative of every area."
            )
            + " "
            + cite
        )
        if examples:
            table = [
                "| 緯度 | 経度 | 地図由来の参考地域（概略） | ソース記録のラベル・日付 |"
                if ja
                else "| Latitude | Longitude | Generalized map area (approximate) | Source label and date |",
                "| ---: | ---: | --- | --- |",
            ]
            for row in examples:
                association = row["map_context"]
                feature = context["features"].get(association.get("feature_id"))
                if feature:
                    name = (
                        feature.get("name_ja")
                        if ja and feature.get("name_ja")
                        else feature["name"]
                    )
                    area = ("付近：" if ja else "Near ") + label(name)
                    area += f" · [Map source]({feature['source_url']})"
                else:
                    area = "未割り当て" if ja else "Unassigned"
                source_label = row.get("original_sample_label") or row["sample_id"]
                date = row.get("collection_date_utc") or (
                    "日付未記録" if ja else "date not recorded"
                )
                table.append(
                    f"| {row['lat']:.8f} | {row['lon']:.8f} | {area} | {label(source_label)} · {label(date)} {cite} |"
                )
            lines.append("\n".join(table))
    lines.append(
        (
            "**地域名は地図データから推定・一般化した参考情報です。ANEMONEに記録された採水地域名や確認済みの湾への所属ではありません。** 記録座標はプロバイダーのグリッド位置を含み、実際の採水地点の精密な位置は未確認です。未割り当てには内陸・沖合・不明確な地点や地図レイヤーの対象外を含む可能性があります。"
            if ja
            else "**Area labels are approximate geographic context inferred from map data, not sampling-area names supplied by ANEMONE or verified bay membership.** Provider grid coordinates do not establish exact sampling sites. Unassigned positions may be inland, offshore, ambiguous or outside the reviewed map layer."
        )
        + " "
        + cite
    )
    lines.append(
        (
            "参考地域名は湾・入江・海峡・島などを含み、同じ粒度の重複しない調査区域を表すものではありません。距離は地図上の参照点までの距離であり、採水座標の位置誤差を表しません。"
            if ja
            else "Reference names may describe bays, coves, straits or islands, rather than disjoint areas at one geographic scale. Matching distances refer to gazetteer points, not sampling-coordinate uncertainty."
        )
        + " "
        + cite
    )
    lines.append(
        ("地図レイヤー：" if ja else "Map layer: ")
        + label(context["registry_version"])
        + ". "
        + " ".join(f"[{label(s['name'])}]({s['url']})" for s in context["map_sources"])
        + " "
        + cite
    )
    # Reuse unchanged count details for controls, source accounting and filters.
    detail_payload = {
        **payload,
        "summary": {**payload["summary"], "locations": locations},
    }
    details = render_location_answer(
        {"aggregate_id": bundle["aggregate_id"], "payload": detail_payload}, query
    ).split("\n\n")
    lines.extend(original[2:] if opts["area_groups"] else details[2:])
    return "\n\n".join(lines)
