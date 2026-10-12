"""Bounded bilingual publication questions; no geographic or taxon inference."""
import re

FREQUENCY_JA = "2020年から2023年の宮城県沿岸で、環境DNAによる検出頻度が高い魚の上位10種を教えてください。年ごと、季節ごとの変化も示してください。"
SPATIAL_JA = "2023年の宮城県沿岸で、採水地点が最も多かった月はいつですか？その月にマイワシが検出された地域を示してください。"
MIYAGI_REGIONS = {"miyagi-regional-demo"}


def japanese(query):
    return bool(re.search(r"[ぁ-んァ-ン一-龯]", query))


def calendar_years(query):
    # Unicode word boundaries exclude years adjacent to 年; digit boundaries do not.
    return re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", query)


def conference_question(query):
    """Recognize complete templates, retaining the literal requested scope."""
    query = re.sub(r"\s+", "", query.strip())
    for heading, template, kind in (
        ("よく見つかる魚は何か？", FREQUENCY_JA, "fish_frequency"),
        ("イワシはどこで見つかるか？", SPATIAL_JA, "monthly_spatial"),
    ):
        if query.startswith(heading):
            query = query[len(heading):]
        pattern = re.escape(template)
        if kind == "fish_frequency":
            pattern = pattern.replace("2020", r"(?P<first>\d{4})").replace("2023", r"(?P<last>\d{4})")
        else:
            pattern = pattern.replace("2023", r"(?P<year>\d{4})")
        match = re.fullmatch(pattern, query)
        if match:
            return {"kind": kind, "region": "miyagi", **match.groupdict()}
    return None


def publication_question_error(query, kind, recipe):
    if re.search(r'\b(?:except|excluding|omit)\b|除外|以外|除く', query, re.I):
        return 'This immutable workflow cannot apply an additional exclusion.'
    if recipe.get('region_id') == 'miyagi-regional-demo' and re.search(
        r'\b(?:Onagawa|Otsuchi|Iwate|Mutsu|Ishinomaki)\b|女川|大槌|岩手|陸奥|石巻', query, re.I
    ):
        return 'The requested place is narrower than or outside the published Miyagi region.'
    spec = conference_question(query)
    if spec:
        if spec['kind'] != kind or recipe.get('region_id') not in MIYAGI_REGIONS:
            return "The requested workflow or Miyagi region differs from the published cohort."
        if kind == 'fish_frequency' and (
            str(recipe.get('time_from')) != spec['first'] + '-01-01'
            or str(recipe.get('time_to')) != spec['last'] + '-12-31'
        ):
            return "The requested calendar range differs from the published cohort."
        if kind == 'monthly_spatial' and recipe.get('spatial_year') != int(spec['year']):
            return "The requested spatial year differs from the published workflow."
    top = re.search(r"\btop\s+(\d+)\b|上位\s*(\d+)\s*種", query, re.I)
    if kind == 'fish_frequency' and top and int(next(v for v in top.groups() if v)) != 10:
        return "This published workflow has a fixed top-ten panel."
    if kind == 'monthly_spatial' and calendar_years(query):
        years = calendar_years(query)
        if len(years) != 1 or str(recipe.get('spatial_year')) != years[0]:
            return 'The requested spatial year differs from the published workflow.'
    return None
