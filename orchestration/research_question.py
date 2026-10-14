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
    """Compatibility wrapper for callers that only need the question decision."""
    from orchestration.publication_scope import publication_compatibility
    result = publication_compatibility(query, kind, {
        'recipe_scope': recipe,
        'assignment_methods': [recipe['assignment_method']] if recipe.get('assignment_method') else [],
    }, question_only=True)
    return None if result.outcome == 'compatible' else result.reason
