"""Bounded compositional paraphrases for two immutable COP17 workflows.

Every word must belong to the supported vocabulary. Unknown taxa, locations,
methods, exclusions, metrics and qualifiers fail closed. No model or query
rewriting is involved; execution still validates the original scope and pins.
"""
import re
import unicodedata

from orchestration.research_question import calendar_years, japanese

COMMON = set("a an the please can could would you me us i want to know tell show list give display find identify which what are were is was have has been be by and or with including include their its these those for of in on along coastal coast region prefecture during from between through over under at as across using based published data dataset datasets anemone edna environmental dna cite citations sources evidence denominators denominator eligible units samples counts count number results changes change vary varied varies variation variations yearly annual annually year years seasonal season seasons time series representative ten top 10 rank ranking ranked most more frequently frequent frequency frequencies detected detection detections fish fishes species compare comparing comparison compares conditions condition high higher low lower warm warmer cold colder cool cooler sst sea surface temperature temperatures how do did does".split())
JA_WORDS = sorted({"環境DNA", "環境dna", "検出頻度", "検出された", "検出される", "よく見つかる", "魚種", "魚", "上位10種", "上位10", "10種", "トップ10", "年ごと", "季節ごと", "年別", "季節別", "年次", "季節", "変化", "推移", "分母", "適格単位数", "検出単位数", "含めて", "含む", "比較して", "比較し", "比較", "高い", "低い", "高水温", "低水温", "高温", "低温", "高", "低", "sst", "海面水温", "海水面温度", "条件", "代表的な", "代表的", "代表", "時系列", "データセット", "データ", "出典", "引用して", "引用", "示してください", "教えてください", "表示してください", "示して", "教えて", "表示して", "ください", "について", "どの", "どんな", "何", "ですか", "か", "における", "および", "及び", "それぞれ", "を", "の", "は", "に", "が", "で", "と", "や", "も", "、", "。", "・", "?", "!"}, key=len, reverse=True)


def _literal_scope(query, recipe):
    text = unicodedata.normalize("NFKC", query).casefold()
    years = calendar_years(text)
    if years:
        token = r"((?:19|20)\d{2}(?:-\d{2}-\d{2})?)"
        patterns = [rf"(?:from\s+)?{token}\s*(?:to|through|[-–—])\s*{token}",
                    rf"between\s+{token}\s+and\s+{token}",
                    r"((?:19|20)\d{2})年?\s*から\s*((?:19|20)\d{2})年?"]
        found = False
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            first, last = match.groups()
            start = first if len(first) > 4 else first + "-01-01"
            end = last if len(last) > 4 else last + "-12-31"
            if years != [first[:4], last[:4]] or start != str(recipe.get("time_from")) or end != str(recipe.get("time_to")):
                return None
            text = text[:match.start()] + " " + text[match.end():]
            found = True
            break
        if not found:
            return None
    # Resolve only literal publication names; never infer a smaller location.
    if recipe.get("region_id") in {"miyagi-regional-demo", "miyagi"}:
        text = re.sub(r"\bmiyagi(?:\s+prefecture)?\b|宮城県?沿岸|宮城県?", " ", text)
    region = str(recipe.get("region_id", ""))
    if region:
        text = text.replace(region.casefold(), " ")
    return text


def parse_cop17_intent(query, recipe):
    if not recipe:
        return None
    text = _literal_scope(query, recipe)
    if text is None:
        return None
    if japanese(query):
        compact = re.sub(r"\s+", "", text)
        fish = "魚" in compact and ("検出頻度" in compact or "よく見つかる" in compact)
        temperature = any(word in compact for word in ("sst", "海面水温", "海水面温度"))
        contrast = "高" in compact and "低" in compact and "比較" in compact
        rest = compact
        for word in JA_WORDS:
            rest = rest.replace(word, "")
        if rest or not fish:
            return None
        return "temperature_comparison" if temperature and contrast else "fish_frequency" if not temperature else None
    words = re.findall(r"[a-z0-9_]+|[^\w\s.,?!:;()\-–—]", text)
    if not words or set(words) - COMMON:
        return None
    tokens = set(words)
    fish = bool(tokens & {"fish", "fishes", "species"})
    frequency = bool(tokens & {"frequency", "frequencies", "frequently"}) and bool(tokens & {"detection", "detections", "detected"})
    temperature = "sst" in tokens or {"sea", "surface"}.issubset(tokens) and bool(tokens & {"temperature", "temperatures"})
    contrast = bool(tokens & {"high", "higher", "warm", "warmer"}) and bool(tokens & {"low", "lower", "cool", "cooler", "cold", "colder"})
    if not fish or not frequency:
        return None
    if temperature:
        return "temperature_comparison" if contrast else None
    if tokens & {"temperature", "temperatures", "high", "low", "warm", "cold", "compare", "comparison", "comparing", "compares"}:
        return None
    return "fish_frequency"
