"""
Expert reference answers for the 15 benchmark questions.

Each reference answer is curated from the actual data in the system
(CTD, metagenome, SST) and includes key facts that a correct answer
must mention. Used by quality_metrics.py for ROUGE-L, completeness,
and LLM-as-judge scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ReferenceAnswer:
    """Ground-truth reference for one benchmark question."""
    question_id: str
    reference_text: str
    key_facts: List[str]
    expected_citation_patterns: List[str] = field(default_factory=list)


REFERENCE_ANSWERS: Dict[str, ReferenceAnswer] = {
    # ── Single-source: CTD (3) ──
    "ctd_01": ReferenceAnswer(
        question_id="ctd_01",
        reference_text=(
            "In April 2024 at Onagawa Bay, CTD profiles show a mean temperature of "
            "approximately 14.89°C with a salinity around 33.89 PSU. The dissolved "
            "oxygen was about 109.36% and chlorophyll-a was elevated at 3.58 µg/L, "
            "which was among the highest monthly values recorded. Profiles were "
            "collected at stations s1, s4, and s8 with depth points extending from "
            "surface to the bottom of the water column."
        ),
        key_facts=[
            "temperature", "14", "salinity", "33", "Onagawa",
            "April", "2024", "chlorophyll", "dissolved oxygen",
        ],
        expected_citation_patterns=["ctd_2024-04-O"],
    ),
    "ctd_02": ReferenceAnswer(
        question_id="ctd_02",
        reference_text=(
            "Dissolved oxygen in Onagawa Bay shows vertical variation with depth. "
            "Surface waters generally have higher DO saturation than bottom waters "
            "due to atmospheric exchange and photosynthesis. Mean DO ranges from "
            "approximately 90% to over 120% across different months. The seasonal "
            "pattern shows higher DO in spring (March-April) with values exceeding "
            "105%, and lower values in autumn (September-October) around 90-98%."
        ),
        key_facts=[
            "dissolved oxygen", "depth", "surface", "bottom",
            "Onagawa", "seasonal", "percent",
        ],
        expected_citation_patterns=["ctd_"],
    ),
    "ctd_03": ReferenceAnswer(
        question_id="ctd_03",
        reference_text=(
            "Surface chlorophyll-a concentrations at Onagawa Bay during summer "
            "(June-August) show monthly means of 1.69 µg/L (June), 2.53 µg/L "
            "(July), and 1.99 µg/L (August) in 2024. July had the highest "
            "summer chlorophyll-a. The elevated values suggest phytoplankton "
            "productivity associated with warmer temperatures and nutrient "
            "availability during the summer months."
        ),
        key_facts=[
            "chlorophyll", "surface", "summer", "Onagawa",
            "µg/L", "July", "phytoplankton",
        ],
        expected_citation_patterns=["ctd_2024-0"],
    ),

    # ── Single-source: Metagenome (3) ──
    "meta_01": ReferenceAnswer(
        question_id="meta_01",
        reference_text=(
            "The dominant microbial genera found in Ishinomaki Bay based on "
            "Kraken classification include copepod genera such as Oncaea, "
            "as well as dinoflagellates like Gyrodinium, and diatoms such as "
            "Seminavis. The community composition varies by sampling date, "
            "with seasonal shifts in dominance between these groups."
        ),
        key_facts=[
            "Ishinomaki", "genera", "Kraken", "dominant",
            "microbial", "community",
        ],
        expected_citation_patterns=["meta_"],
    ),
    "meta_02": ReferenceAnswer(
        question_id="meta_02",
        reference_text=(
            "Kraken and MetaEuk classifiers show differences in community "
            "composition detection. Kraken, based on k-mer matching, identifies "
            "82 samples with a mean Shannon diversity H' of 3.884 and mean "
            "richness of 394 genera. MetaEuk, based on protein-level classification, "
            "reports a mean Shannon H' of 4.305 and richness of 373 genera across "
            "the same 82 samples. MetaEuk generally shows higher diversity indices, "
            "suggesting it captures a broader taxonomic range at the protein level."
        ),
        key_facts=[
            "Kraken", "MetaEuk", "Shannon", "diversity",
            "richness", "classifier", "genera",
        ],
        expected_citation_patterns=["meta_"],
    ),
    "meta_03": ReferenceAnswer(
        question_id="meta_03",
        reference_text=(
            "Metagenome samples from Mutsu Bay (code M) are available in the "
            "dataset. These samples follow the naming convention YYYY-MM-M-sN and "
            "include both Kraken and MetaEuk genus-level classifications. The samples "
            "cover multiple time points and include stations s0 and s4."
        ),
        key_facts=[
            "Mutsu", "metagenome", "samples", "available",
        ],
        expected_citation_patterns=["meta_"],
    ),

    # ── Dual-source: CTD + SST (3) ──
    "dual_01": ReferenceAnswer(
        question_id="dual_01",
        reference_text=(
            "Satellite SST and CTD surface temperature measurements at Onagawa Bay "
            "show strong agreement. Cross-validation of 24 paired observations shows "
            "100% agreement within the ±2.0°C threshold, with a mean absolute "
            "difference (|ΔT|) of 0.92°C. The mean reliability score is 0.771. "
            "Small discrepancies are expected because satellite SST measures the "
            "skin layer (~10µm) while CTD measures at ~0.5m depth."
        ),
        key_facts=[
            "SST", "CTD", "surface temperature", "agreement",
            "0.92", "24", "paired", "Onagawa",
        ],
        expected_citation_patterns=["ctd_", "sst_"],
    ),
    "dual_02": ReferenceAnswer(
        question_id="dual_02",
        reference_text=(
            "The seasonal temperature trend from both CTD profiles and satellite "
            "observations shows clear seasonality at Onagawa Bay. CTD monthly means "
            "range from winter lows of about 7-8°C (February-March) to summer peaks "
            "of 22-23°C (September). Satellite SST daily observations during the "
            "December 2025 to February 2026 period show temperatures ranging from "
            "approximately 6.5 to 12.8°C, consistent with the winter CTD measurements."
        ),
        key_facts=[
            "seasonal", "temperature", "CTD", "SST",
            "winter", "summer", "trend", "Onagawa",
        ],
        expected_citation_patterns=["ctd_", "sst_"],
    ),
    "dual_03": ReferenceAnswer(
        question_id="dual_03",
        reference_text=(
            "Comparison of in-situ CTD surface temperature and remote sensing SST "
            "data shows good correspondence. CTD surface measurements at Onagawa Bay "
            "across all months range from about 7.5°C to 23.4°C. Satellite SST "
            "observations over the region show consistent values with a mean absolute "
            "difference of 0.92°C across 24 paired observations. The 100% agreement "
            "rate within ±2.0°C validates the satellite data for this region."
        ),
        key_facts=[
            "CTD", "SST", "surface", "temperature", "comparison",
            "agreement", "in-situ", "remote sensing",
        ],
        expected_citation_patterns=["ctd_", "sst_"],
    ),

    # ── Analysis-dependent (3) ──
    "analysis_01": ReferenceAnswer(
        question_id="analysis_01",
        reference_text=(
            "Taxa-environment correlation analysis (Spearman, n=37 samples) identifies "
            "21 significant correlations (p<0.05). Key findings include: Gyrodinium "
            "shows strong negative correlation with temperature (ρ=-0.599, p=0.0001), "
            "Oncaea shows strong positive correlation with temperature (ρ=0.591, "
            "p=0.0001), Seminavis negatively correlates with temperature (ρ=-0.524, "
            "p=0.0009), and Levanderina negatively correlates with salinity (ρ=-0.504, "
            "p=0.0015). These suggest dinoflagellates decline with warming while "
            "copepods increase."
        ),
        key_facts=[
            "Gyrodinium", "temperature", "correlation", "Oncaea",
            "Spearman", "significant", "negative", "positive",
        ],
        expected_citation_patterns=["analysis_taxa"],
    ),
    "analysis_02": ReferenceAnswer(
        question_id="analysis_02",
        reference_text=(
            "Microbial diversity varies seasonally in both bays. Kraken-based Shannon "
            "H' across 82 samples shows a mean of 3.884 with range [0.621, 5.163]. "
            "The most diverse samples include 2024-11-O-s0 (Onagawa Bay, November) "
            "and 2025-01-I-og (Ishinomaki Bay, January). The least diverse samples "
            "include 2024-10-M-s4 and 2024-07-O-s1 (Onagawa Bay, July), the latter "
            "being a detected anomaly with Shannon H' of 1.601 versus predicted 3.453 "
            "(−2.3σ deviation), suggesting a possible bloom event."
        ),
        key_facts=[
            "diversity", "seasonal", "Shannon", "Onagawa",
            "Ishinomaki", "3.884", "anomaly",
        ],
        expected_citation_patterns=["analysis_diversity"],
    ),
    "analysis_03": ReferenceAnswer(
        question_id="analysis_03",
        reference_text=(
            "Co-occurrence analysis using Jaccard similarity examines pairwise "
            "relationships between genera with variable prevalence (10-90% of samples). "
            "Dinoflagellate genera like Gyrodinium and diatom genera like Seminavis "
            "both show negative correlation with temperature, suggesting they may "
            "co-occur in cooler conditions. The co-occurrence matrix computed from "
            "30 genera across all samples provides quantitative Jaccard indices "
            "for these relationships."
        ),
        key_facts=[
            "co-occurrence", "dinoflagellate", "diatom",
            "Jaccard", "pattern", "genera",
        ],
        expected_citation_patterns=["analysis_"],
    ),

    # ── Reliability-dependent (3) ──
    "reliability_01": ReferenceAnswer(
        question_id="reliability_01",
        reference_text=(
            "SST data reliability is high when validated against CTD measurements. "
            "Cross-validation of 24 paired observations at Onagawa Bay shows 100% "
            "agreement within the ±2.0°C threshold. The mean absolute temperature "
            "difference is 0.92°C with a mean reliability score of 0.771. All 24 "
            "paired observations at Onagawa Bay agree, confirming the satellite SST "
            "data is reliable for this study region."
        ),
        key_facts=[
            "reliable", "SST", "CTD", "100%", "agreement",
            "0.92", "24", "validation", "Onagawa",
        ],
        expected_citation_patterns=["reliability_sst_ctd"],
    ),
    "reliability_02": ReferenceAnswer(
        question_id="reliability_02",
        reference_text=(
            "Diversity prediction analysis identifies 1 anomalous measurement out of "
            "37 samples evaluated. Sample 2024-07-O-s1 from Onagawa Bay (July 2024) "
            "has a predicted Shannon H' of 3.453 based on environmental conditions "
            "but an actual H' of only 1.601, representing a −2.3σ deviation exceeding "
            "the 2.0σ anomaly threshold. This suggests a possible bloom event or "
            "dominance shift during summer. The mean absolute deviation across all "
            "samples is 0.80σ."
        ),
        key_facts=[
            "anomaly", "2024-07-O-s1", "diversity", "deviation",
            "predicted", "actual", "Shannon", "bloom",
        ],
        expected_citation_patterns=["reliability_diversity"],
    ),
    "reliability_03": ReferenceAnswer(
        question_id="reliability_03",
        reference_text=(
            "Cross-source corroboration assessment of 207 total observations assigns "
            "reliability tiers: 37 are 'verified' (multi-source agreement from CTD + "
            "metagenome with diversity prediction matching), 20 are 'supported' "
            "(partial corroboration), and 150 are 'standalone' (single source only). "
            "The mean reliability score is 0.435. Verified observations include "
            "multi-modal samples where both CTD and metagenome data are available "
            "and diversity predictions match actual values."
        ),
        key_facts=[
            "corroboration", "verified", "supported", "standalone",
            "207", "37", "reliability", "confidence",
        ],
        expected_citation_patterns=["reliability_corroboration"],
    ),
}


def get_reference(question_id: str) -> ReferenceAnswer | None:
    """Look up a reference answer by question ID."""
    return REFERENCE_ANSWERS.get(question_id)
