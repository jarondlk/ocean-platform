"""
Pre-Analysis layer – precompute ecological relationships between
CTD, metagenome, and SST data for enriched RAG responses.

Outputs are saved to data/analysis/ as parquet + JSONL text summaries.
"""
from __future__ import annotations

import json
import logging
import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

import config
from preprocessing.derived_artifacts import stamp_document, retain_artifact_history, write_artifact_manifest

logger = logging.getLogger(__name__)

CORRELATION_METHOD_VERSION = "taxa-env-full-abundance-v2"
CORRELATION_COLUMNS = [
    "genus", "method", "env_variable", "spearman_rho", "p_value",
    "n_samples", "n_missing_abundance", "n_missing_environment",
    "n_observed_zero", "significant",
]


def _input_snapshot(path: Path) -> tuple[bytes, str]:
    """Hash the exact immutable bytes later parsed, never reopen a mutable path."""
    payload = path.read_bytes()
    return payload, hashlib.sha256(payload).hexdigest()


def _complete_abundance_matrices(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Read explicit normalized cells, preserving zero, missingness and methods.

    Normalization melts a full genus-by-sample matrix, including missing cells.
    A missing row is therefore an incomplete input, not a documented zero. A
    legacy wide table retains its file-owned Kraken method identity.
    """
    if frame.empty or "genus" not in frame:
        raise ValueError("abundance_schema_unavailable")
    if frame["genus"].isna().any() or (frame["genus"].astype(str).str.strip() == "").any():
        raise ValueError("abundance_genus_unavailable")
    if "sample_id" in frame or "abundance_value" in frame:
        if not {"sample_id", "abundance_value", "method"}.issubset(frame.columns):
            raise ValueError("abundance_schema_unavailable")
        if frame[["sample_id", "method"]].isna().any().any():
            raise ValueError("abundance_identity_unavailable")
        if (frame[["sample_id", "method"]].astype(str).apply(lambda c: c.str.strip()) == "").any().any():
            raise ValueError("abundance_identity_unavailable")
        if frame.duplicated(["method", "genus", "sample_id"]).any():
            raise ValueError("abundance_duplicate_cells")
        matrices = {}
        for method, group in frame.groupby("method", sort=True):
            if len(group) != group["genus"].nunique() * group["sample_id"].nunique():
                raise ValueError("abundance_incomplete_matrix")
            numeric = pd.to_numeric(group["abundance_value"], errors="coerce")
            if (group["abundance_value"].notna() & numeric.isna()).any():
                raise ValueError("abundance_invalid_values")
            measured = numeric.dropna()
            if (~np.isfinite(measured)).any() or (measured < 0).any():
                raise ValueError("abundance_invalid_values")
            matrices[str(method)] = group.assign(abundance_value=numeric).pivot(
                index="sample_id", columns="genus", values="abundance_value",
            )
        return matrices
    if frame["genus"].duplicated().any() or frame.columns.duplicated().any():
        raise ValueError("abundance_duplicate_cells")
    wide = frame.set_index("genus")
    if wide.shape[1] == 0:
        raise ValueError("abundance_schema_unavailable")
    numeric = wide.apply(pd.to_numeric, errors="coerce")
    if (wide.notna() & numeric.isna()).any().any():
        raise ValueError("abundance_invalid_values")
    measured = numeric.to_numpy(dtype=float)
    if np.isinf(measured).any() or (measured < 0).any():
        raise ValueError("abundance_invalid_values")
    return {"kraken": numeric.T}


# ─────────────────────────────────────────────
# 1. CTD Monthly Trends
# ─────────────────────────────────────────────
def compute_ctd_monthly_trends() -> pd.DataFrame:
    """
    Monthly mean ± std for key CTD variables per bay.
    Also computes stratification index (bottom_T - surface_T).
    """
    ctd = pd.read_parquet(config.NORMALIZED_DIR / "ctd_summary.parquet")
    ctd["ctd_date"] = pd.to_datetime(ctd["ctd_date"])
    ctd["year_month"] = ctd["ctd_date"].dt.to_period("M").astype(str)
    ctd["month"] = ctd["ctd_date"].dt.month

    # Extract bay from sample_id (format: YYYY-MM-B-sN)
    ctd["bay"] = ctd["sample_id"].str.extract(r"\d{4}-\d{2}-([A-Z])-")

    variables = [
        "mean_temperature", "mean_salinity", "mean_do_percent", "mean_chl_a",
        "surface_temperature", "bottom_temperature",
        "surface_salinity", "bottom_salinity",
        "mean_turbidity",
    ]
    existing_vars = [v for v in variables if v in ctd.columns]

    agg_dict = {v: ["mean", "std", "min", "max", "count"] for v in existing_vars}
    monthly = ctd.groupby(["bay", "year_month", "month"]).agg(agg_dict)
    monthly.columns = ["_".join(c) for c in monthly.columns]
    monthly = monthly.reset_index()

    # Stratification index
    if "surface_temperature" in ctd.columns and "bottom_temperature" in ctd.columns:
        strat = ctd.groupby(["bay", "year_month"]).apply(
            lambda g: pd.Series({
                "strat_index_mean": (g["surface_temperature"] - g["bottom_temperature"]).mean(),
                "strat_index_std": (g["surface_temperature"] - g["bottom_temperature"]).std(),
            }),
            include_groups=False,
        ).reset_index()
        monthly = monthly.merge(strat, on=["bay", "year_month"], how="left")

    logger.info("CTD monthly trends: %d rows", len(monthly))
    return monthly


# ─────────────────────────────────────────────
# 2. Taxa–Environment Correlations
# ─────────────────────────────────────────────
def compute_taxa_env_correlations(top_n_genera: int = 20) -> pd.DataFrame:
    """
    Spearman correlations from complete normalized abundance and paired CTD.

    Explicit measured zeros are retained, NaN measurements are excluded pairwise,
    and incomplete tables make the operation unavailable. Presentation top-ten
    summaries never supply scientific abundance. Declared methods stay separate.
    """
    context_path = config.SERVING_DIR / "sample_multisource_context.parquet"
    abundance_path = config.NORMALIZED_DIR / "kraken_genus_abundance.parquet"
    operation = {
        "name": "taxa_env_correlation", "method_version": CORRELATION_METHOD_VERSION,
        "status": "unavailable", "reason": None, "inputs": {},
        "input_paths": [str(context_path.resolve()), str(abundance_path.resolve())],
        "unavailable_pairs": [],
        "parameters": {
            "top_n_genera": top_n_genera, "min_samples": 5,
            "min_environment_measurements": 6, "significance_threshold": 0.05,
            "missingness_policy": "explicit_zero_only; missing_measurements_excluded_pairwise; absent_cells_unavailable",
            "input_binding_policy": "hash and parquet parsing use the same frozen bytes",
        },
    }

    def unavailable(reason):
        logger.warning("Taxa-env correlations unavailable: %s", reason)
        operation["reason"] = reason
        result = pd.DataFrame(columns=CORRELATION_COLUMNS)
        result.attrs["operation"] = operation
        return result

    input_failures = []
    snapshots = {}
    for path, role in ((context_path, "paired_context"), (abundance_path, "normalized_abundance")):
        try:
            if not path.is_file():
                input_failures.append(role + "_missing")
            else:
                payload, checksum = _input_snapshot(path)
                snapshots[role] = payload
                operation["inputs"][str(path.resolve())] = checksum
        except OSError:
            input_failures.append(role + "_read_unavailable")
    if input_failures:
        return unavailable(";".join(input_failures))
    try:
        ctx = pd.read_parquet(BytesIO(snapshots["paired_context"]))
        matrices = _complete_abundance_matrices(pd.read_parquet(BytesIO(snapshots["normalized_abundance"])))
    except (ValueError, OSError) as error:
        return unavailable(str(error) if isinstance(error, ValueError) else "input_read_unavailable")
    if not {"sample_id", "has_ctd", "has_kraken"}.issubset(ctx.columns):
        return unavailable("paired_context_schema_unavailable")
    if not ctx[["has_ctd", "has_kraken"]].isin([True, False]).all().all():
        return unavailable("paired_context_availability_unavailable")
    paired = ctx[ctx["has_ctd"] & ctx["has_kraken"]].copy()
    if paired["sample_id"].isna().any() or paired["sample_id"].duplicated().any():
        return unavailable("paired_context_identity_unavailable")
    if len(paired) < 5:
        return unavailable("insufficient_paired_samples")
    paired = paired.set_index("sample_id")
    if any(not paired.index.isin(matrix.index).all() for matrix in matrices.values()):
        return unavailable("abundance_paired_samples_missing")
    env_vars = ["mean_temperature", "mean_salinity", "mean_do_percent", "mean_chl_a", "mean_turbidity"]
    environment = paired[[v for v in env_vars if v in paired]].apply(pd.to_numeric, errors="coerce")
    environment = environment.replace([np.inf, -np.inf], np.nan)
    env_vars = [v for v in environment if environment[v].notna().sum() > 5]
    if not env_vars:
        return unavailable("insufficient_environment_measurements")
    results = []
    for method, matrix in matrices.items():
        cohort = matrix.loc[paired.index]
        top_genera = cohort.mean().nlargest(top_n_genera).index.tolist()
        for genus in top_genera:
            g_values = cohort[genus]
            for env_var in env_vars:
                e_values = environment[env_var]
                mask = g_values.notna() & e_values.notna()
                pair = {"genus": genus, "method": method, "env_variable": env_var,
                        "n_samples": int(mask.sum())}
                if mask.sum() < 5:
                    operation["unavailable_pairs"].append({**pair, "reason": "insufficient_paired_measurements"})
                    continue
                if g_values[mask].nunique() < 2 or e_values[mask].nunique() < 2:
                    operation["unavailable_pairs"].append({**pair, "reason": "constant_series"})
                    continue  # A constant series cannot establish a rank correlation.
                rho, pval = sp_stats.spearmanr(g_values[mask], e_values[mask])
                if not np.isfinite(rho) or not np.isfinite(pval):
                    operation["unavailable_pairs"].append({**pair, "reason": "nonfinite_statistic"})
                    continue
                results.append({
                    "genus": genus, "method": method, "env_variable": env_var,
                    "spearman_rho": round(rho, 4), "p_value": round(pval, 6),
                    "n_samples": int(mask.sum()), "n_missing_abundance": int(g_values.isna().sum()),
                    "n_missing_environment": int(e_values.isna().sum()),
                    "n_observed_zero": int((g_values[mask] == 0).sum()), "significant": bool(pval < 0.05),
                })
    operation.update(n_paired_samples=len(paired), methods=sorted(matrices))
    if not results:
        return unavailable("no_estimable_correlations")
    operation.update(status="computed", reason=None)
    corr_df = pd.DataFrame(results, columns=CORRELATION_COLUMNS)
    corr_df.attrs["operation"] = operation
    logger.info("Taxa-env correlations: %d pairs from full normalized abundance", len(corr_df))
    return corr_df


# ─────────────────────────────────────────────
# 3. Community Diversity Indices
# ─────────────────────────────────────────────
def compute_diversity_indices() -> pd.DataFrame:
    """
    Shannon diversity (H') and Simpson index (1-D) per metagenome sample.
    Computed from Kraken and MetaEuk genus-level abundance.
    """
    kr_path = config.NORMALIZED_DIR / "kraken_genus_abundance.parquet"
    me_path = config.NORMALIZED_DIR / "metaeuk_genus_abundance.parquet"

    results = []

    for source, path in [("kraken", kr_path), ("metaeuk", me_path)]:
        if not path.exists():
            continue
        df = pd.read_parquet(path)

        # Handle long format: (genus, sample_id, abundance_value, method)
        if "sample_id" in df.columns and "abundance_value" in df.columns:
            for sample_id, grp in df.groupby("sample_id"):
                vals = pd.to_numeric(grp["abundance_value"], errors="coerce").dropna()
                vals = vals[vals > 0]

                if vals.empty:
                    continue

                total = vals.sum()
                if total == 0:
                    continue
                props = vals / total

                shannon = -float(np.sum(props * np.log(props)))
                simpson = 1.0 - float(np.sum(props ** 2))
                richness = len(vals)
                evenness = shannon / np.log(richness) if richness > 1 else 0.0

                results.append({
                    "sample_id": sample_id,
                    "source": source,
                    "shannon_h": round(shannon, 4),
                    "simpson_1d": round(simpson, 6),
                    "richness": richness,
                    "evenness": round(evenness, 4),
                })
        else:
            # Wide format fallback: rows=genus, columns=samples
            if "genus" in df.columns:
                df = df.set_index("genus")

            for sample in df.columns:
                vals = pd.to_numeric(df[sample], errors="coerce").dropna()
                vals = vals[vals > 0]

                if vals.empty:
                    continue

                total = vals.sum()
                if total == 0:
                    continue
                props = vals / total

                shannon = -float(np.sum(props * np.log(props)))
                simpson = 1.0 - float(np.sum(props ** 2))
                richness = len(vals)
                evenness = shannon / np.log(richness) if richness > 1 else 0.0

                results.append({
                    "sample_id": sample,
                    "source": source,
                    "shannon_h": round(shannon, 4),
                    "simpson_1d": round(simpson, 6),
                    "richness": richness,
                    "evenness": round(evenness, 4),
                })

    div_df = pd.DataFrame(results)

    # Parse bay and date from sample_id
    if not div_df.empty:
        div_df["bay"] = div_df["sample_id"].str.extract(r"\d{4}-\d{2}-([A-Z])-")
        div_df["year_month"] = div_df["sample_id"].str.extract(r"(\d{4}-\d{2})-")

    logger.info("Diversity indices: %d samples", len(div_df))
    return div_df


# ─────────────────────────────────────────────
# 4. Bay Comparison Summaries
# ─────────────────────────────────────────────
def compute_bay_comparison() -> pd.DataFrame:
    """
    Aggregated CTD statistics per bay for cross-bay comparison.
    """
    ctd = pd.read_parquet(config.NORMALIZED_DIR / "ctd_summary.parquet")
    ctd["bay"] = ctd["sample_id"].str.extract(r"\d{4}-\d{2}-([A-Z])-")

    vars_to_compare = [
        "mean_temperature", "mean_salinity", "mean_do_percent",
        "mean_chl_a", "mean_turbidity",
    ]
    existing = [v for v in vars_to_compare if v in ctd.columns]

    agg = ctd.groupby("bay")[existing].agg(["mean", "std", "min", "max", "count"])
    agg.columns = ["_".join(c) for c in agg.columns]
    agg = agg.reset_index()

    logger.info("Bay comparison: %d bays", len(agg))
    return agg


# ─────────────────────────────────────────────
# 5. Taxa Co-occurrence
# ─────────────────────────────────────────────
def compute_taxa_cooccurrence(top_n: int = 30, min_prev: float = 0.10, max_prev: float = 0.90) -> pd.DataFrame:
    """
    Pairwise co-occurrence (Jaccard similarity) for genera with variable
    occurrence (present in min_prev–max_prev fraction of samples).
    Ubiquitous genera (>90%) are excluded as they add no information.
    """
    kr_path = config.NORMALIZED_DIR / "kraken_genus_abundance.parquet"
    if not kr_path.exists():
        return pd.DataFrame()

    df = pd.read_parquet(kr_path)

    # Handle long format → pivot to wide
    if "sample_id" in df.columns and "abundance_value" in df.columns and "genus" in df.columns:
        wide = df.pivot_table(index="genus", columns="sample_id",
                              values="abundance_value", fill_value=0)
    elif "genus" in df.columns:
        wide = df.set_index("genus")
    else:
        wide = df

    # Convert to numeric
    wide = wide.apply(pd.to_numeric, errors="coerce").fillna(0)

    # Presence/absence
    presence = (wide > 0).astype(int)
    n_samples = presence.shape[1]

    # Filter to genera with variable occurrence
    freq = presence.sum(axis=1)
    prevalence = freq / n_samples
    variable_genera = prevalence[(prevalence >= min_prev) & (prevalence <= max_prev)]

    if len(variable_genera) < 5:
        # Relax constraints if too few genera pass
        variable_genera = prevalence[(prevalence >= 0.05) & (prevalence <= 0.95)]

    # Take top_n by prevalence closest to 50% (most informative)
    variable_genera = variable_genera.sort_values(key=lambda x: abs(x - 0.5))
    selected = variable_genera.head(top_n).index.tolist()
    presence = presence.loc[selected]

    # Jaccard similarity
    n_genera = len(selected)
    jaccard = np.zeros((n_genera, n_genera))

    for i in range(n_genera):
        for j in range(i, n_genera):
            a = presence.iloc[i].values.astype(bool)
            b = presence.iloc[j].values.astype(bool)
            intersection = np.sum(a & b)
            union = np.sum(a | b)
            if union > 0:
                jaccard[i, j] = intersection / union
                jaccard[j, i] = jaccard[i, j]

    cooc_df = pd.DataFrame(jaccard, index=selected, columns=selected)
    logger.info("Co-occurrence matrix: %d × %d genera (prevalence %.0f%%–%.0f%%)",
                n_genera, n_genera, min_prev * 100, max_prev * 100)
    return cooc_df


# ─────────────────────────────────────────────
# 6. Build Analysis Text Documents (for RAG)
# ─────────────────────────────────────────────
def build_analysis_documents(
    trends: pd.DataFrame,
    correlations: pd.DataFrame,
    diversity: pd.DataFrame,
    bay_comp: pd.DataFrame,
) -> List[dict]:
    """
    Convert precomputed analyses into text documents for RAG retrieval.
    """
    docs = []
    bay_names = {"O": "Onagawa Bay", "I": "Ishinomaki Bay", "M": "Mutsu Bay"}

    # Trend summaries per bay per year_month
    if not trends.empty:
        for bay in trends["bay"].dropna().unique():
            bt = trends[trends["bay"] == bay].sort_values("year_month")
            bay_name = bay_names.get(bay, bay)

            text = f"CTD temporal trends for {bay_name}.\n"
            for _, r in bt.iterrows():
                ym = r["year_month"]
                parts = []
                for var in ["mean_temperature", "mean_salinity", "mean_do_percent", "mean_chl_a"]:
                    col_mean = f"{var}_mean"
                    col_std = f"{var}_std"
                    col_count = f"{var}_count"
                    if col_mean in r and pd.notna(r[col_mean]):
                        std_val = f"±{r[col_std]:.1f}" if col_std in r and pd.notna(r[col_std]) else ""
                        n = int(r[col_count]) if col_count in r and pd.notna(r[col_count]) else 0
                        label = var.replace("mean_", "")
                        parts.append(f"{label}={r[col_mean]:.2f}{std_val}")
                if parts:
                    text += f"  {ym} (n={n}): {', '.join(parts)}\n"

            docs.append({
                "id": f"analysis_ctd_trends_{bay}",
                "source_type": "pre_analysis",
                "title": f"CTD monthly trends – {bay_name}",
                "text": text,
                "analysis_type": "ctd_temporal_trends",
                "bay": bay,
            })

    # Correlation summary
    if not correlations.empty:
        sig = correlations[correlations["significant"]].copy()
        if not sig.empty:
            text = "Significant taxa–environment correlations (Spearman, p<0.05):\n"
            for _, r in sig.sort_values("p_value").iterrows():
                direction = "positive" if r["spearman_rho"] > 0 else "negative"
                env_label = r["env_variable"].replace("mean_", "")
                method_label = f" ({r['method']})" if "method" in r else ""
                text += (
                    f"  {r['genus']}{method_label} × {env_label}: ρ={r['spearman_rho']:.3f} "
                    f"(p={r['p_value']:.4f}, n={r['n_samples']}, {direction})\n"
                )
            docs.append({
                "id": "analysis_taxa_env_correlations",
                "source_type": "pre_analysis",
                "title": "Taxa–environment correlations (Spearman)",
                "text": text,
                "analysis_type": "taxa_env_correlation",
            })

    # Diversity summary
    if not diversity.empty:
        for source in diversity["source"].unique():
            sd = diversity[diversity["source"] == source]
            text = f"Community diversity indices ({source}):\n"
            text += f"  Samples: {len(sd)}\n"
            text += f"  Shannon H': mean={sd['shannon_h'].mean():.3f}, range=[{sd['shannon_h'].min():.3f}, {sd['shannon_h'].max():.3f}]\n"
            text += f"  Simpson 1-D: mean={sd['simpson_1d'].mean():.4f}, range=[{sd['simpson_1d'].min():.4f}, {sd['simpson_1d'].max():.4f}]\n"
            text += f"  Richness: mean={sd['richness'].mean():.0f}, range=[{sd['richness'].min()}, {sd['richness'].max()}]\n"
            text += f"  Evenness: mean={sd['evenness'].mean():.3f}\n"

            # Top/bottom by diversity
            top = sd.nlargest(3, "shannon_h")
            bot = sd.nsmallest(3, "shannon_h")
            text += f"  Most diverse: {', '.join(top['sample_id'].tolist())}\n"
            text += f"  Least diverse: {', '.join(bot['sample_id'].tolist())}\n"

            docs.append({
                "id": f"analysis_diversity_{source}",
                "source_type": "pre_analysis",
                "title": f"Community diversity – {source}",
                "text": text,
                "analysis_type": "diversity_indices",
            })

    # Bay comparison
    if not bay_comp.empty:
        text = "Cross-bay CTD comparison:\n"
        for _, r in bay_comp.iterrows():
            bay_name = bay_names.get(r["bay"], r["bay"])
            parts = []
            for var in ["mean_temperature", "mean_salinity", "mean_do_percent", "mean_chl_a"]:
                col_mean = f"{var}_mean"
                col_std = f"{var}_std"
                col_count = f"{var}_count"
                if col_mean in r and pd.notna(r[col_mean]):
                    label = var.replace("mean_", "")
                    parts.append(f"{label}={r[col_mean]:.2f}±{r.get(col_std, 0):.2f} (n={int(r.get(col_count, 0))})")
            text += f"  {bay_name}: {', '.join(parts)}\n"

        docs.append({
            "id": "analysis_bay_comparison",
            "source_type": "pre_analysis",
            "title": "Cross-bay CTD comparison",
            "text": text,
            "analysis_type": "bay_comparison",
        })

    docs = [stamp_document(doc, "taxa_env_correlation", correlations.attrs.get("operation", {}))
            if doc.get("analysis_type") == "taxa_env_correlation" else doc for doc in docs]
    logger.info("Built %d analysis documents", len(docs))
    return docs


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────
def run_all() -> Dict[str, Any]:
    """Run all pre-analyses and save outputs."""
    config.ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    retain_artifact_history(config.ANALYSIS_DIR, ["taxa_env_correlations.parquet", "analysis_documents.jsonl", "derived_artifacts.json"])
    results = {}

    logger.info("Computing CTD monthly trends...")
    trends = compute_ctd_monthly_trends()
    trends.to_parquet(config.ANALYSIS_DIR / "ctd_monthly_trends.parquet", index=False)
    results["trends"] = trends

    logger.info("Computing taxa–environment correlations...")
    correlations = compute_taxa_env_correlations()
    correlations.attrs["operation"]["parameters"]["regeneration_id"] = uuid4().hex
    correlations.to_parquet(config.ANALYSIS_DIR / "taxa_env_correlations.parquet", index=False)
    results["correlations"] = correlations

    logger.info("Computing diversity indices...")
    diversity = compute_diversity_indices()
    diversity.to_parquet(config.ANALYSIS_DIR / "diversity_indices.parquet", index=False)
    results["diversity"] = diversity

    logger.info("Computing bay comparison...")
    bay_comp = compute_bay_comparison()
    bay_comp.to_parquet(config.ANALYSIS_DIR / "bay_comparison.parquet", index=False)
    results["bay_comparison"] = bay_comp

    logger.info("Computing taxa co-occurrence...")
    cooc = compute_taxa_cooccurrence()
    cooc.to_parquet(config.ANALYSIS_DIR / "taxa_cooccurrence.parquet")
    results["cooccurrence"] = cooc

    logger.info("Building analysis documents...")
    analysis_docs = build_analysis_documents(trends, correlations, diversity, bay_comp)
    doc_path = config.ANALYSIS_DIR / "analysis_documents.jsonl"
    with open(doc_path, "w", encoding="utf-8") as f:
        for d in analysis_docs:
            f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
    results["documents"] = analysis_docs
    write_artifact_manifest(config.ANALYSIS_DIR, {"taxa_env_correlations.parquet":
        ("taxa_env_correlation", correlations.attrs.get("operation", {}))})

    logger.info("Pre-analysis complete: %d outputs", len(results))
    return results
