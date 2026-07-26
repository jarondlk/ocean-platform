#!/usr/bin/env python3
"""
Ablation study runner — 7-variant evaluation benchmark.

Orchestrates the complete evaluation of the provenance-aware RAG system
across 7 system configurations that vary source coverage (0–3),
pre-analysis injection, and reliability injection.

Usage:
    # Full ablation (7 variants × 15 questions)
    python scripts/run_ablation.py

    # With 3 repetitions for statistical testing
    python scripts/run_ablation.py --repeats 3

    # Quick mode (subset of questions)
    python scripts/run_ablation.py --quick

    # With LLM-as-judge scoring
    python scripts/run_ablation.py --judge

    # Custom model
    python scripts/run_ablation.py --model qwen2.5:7b-instruct --tag small

    # Analyze existing results only
    python scripts/run_ablation.py --analyze-only --results-dir data/evaluation/ablation_XXX/
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from evaluation.benchmark import (
    BENCHMARK_QUESTIONS,
    SYSTEM_VARIANTS,
    SystemVariant,
    run_single_ablation,
)
from evaluation.quality_metrics import score_single_response
from evaluation.reference_answers import get_reference
from evaluation.statistical_analysis import (
    pairwise_to_dataframe,
    run_full_statistical_analysis,
)

logger = logging.getLogger(__name__)

# Default LLM configuration
DEFAULT_MODEL = "qwen2.5:14b-instruct"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_TOP_K = 8
DEFAULT_TEMPERATURE = 0.0
DEFAULT_NUM_CTX = 8192


# ─────────────────────────────────────────────
# Preflight checks
# ─────────────────────────────────────────────
def preflight_check(ollama_url: str, model: str) -> bool:
    """Verify that Ollama and the required model are available."""
    import requests

    print("🔍 Preflight checks...")

    # Check Ollama
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        print(f"  ✅ Ollama reachable ({len(models)} models available)")
    except Exception as e:
        print(f"  ❌ Ollama not reachable at {ollama_url}: {e}")
        return False

    # Check model
    if model in models or any(model in m for m in models):
        print(f"  ✅ Model '{model}' available")
    else:
        print(f"  ⚠️  Model '{model}' not found (available: {', '.join(models[:5])})")
        print("      Will attempt to use anyway (Ollama may pull automatically)")

    # Check retrieval data
    jsonl = config.SERVING_DIR / "retrieval_documents.jsonl"
    if jsonl.exists():
        n_docs = sum(1 for line in open(jsonl) if line.strip())
        print(f"  ✅ Retrieval documents: {n_docs}")
    else:
        print(f"  ⚠️  No retrieval documents at {jsonl}")

    # Check analysis data
    analysis_jsonl = config.ANALYSIS_DIR / "analysis_documents.jsonl"
    if analysis_jsonl.exists():
        print("  ✅ Analysis documents available")
    else:
        print("  ⚠️  No analysis documents")

    # Check reliability data
    rel_jsonl = config.RELIABILITY_DIR / "reliability_documents.jsonl"
    if rel_jsonl.exists():
        print("  ✅ Reliability documents available")
    else:
        print("  ⚠️  No reliability documents")

    print()
    return True


# ─────────────────────────────────────────────
# Single repetition
# ─────────────────────────────────────────────
def run_single_repetition(
    questions,
    variants: list[SystemVariant],
    *,
    model: str,
    ollama_url: str,
    top_k: int,
    temperature: float,
    num_ctx: int,
    rep_id: int = 1,
) -> pd.DataFrame:
    """Run one full repetition of the ablation benchmark."""
    total = len(questions) * len(variants)
    results = []
    errors = 0

    print(f"\n{'='*60}")
    print(f"  Repetition {rep_id}: {len(questions)} questions × {len(variants)} variants = {total} evaluations")
    print(f"{'='*60}")

    for i, q in enumerate(questions):
        for j, v in enumerate(variants):
            idx = i * len(variants) + j + 1
            print(f"  [{idx:3d}/{total}] {q.id:20s} | {v.name:28s} | ", end="", flush=True)

            t0 = time.time()
            result = run_single_ablation(
                q, v,
                model=model,
                ollama_url=ollama_url,
                top_k=top_k,
                temperature=temperature,
                num_ctx=num_ctx,
            )
            elapsed = time.time() - t0

            if result.error:
                print(f"ERROR ({elapsed:.1f}s): {result.error[:60]}")
                errors += 1
            else:
                print(
                    f"OK ({elapsed:.1f}s) "
                    f"prec={result.retrieval_precision:.2f} "
                    f"cov={result.source_coverage:.2f} "
                    f"cit={result.citation_count} "
                    f"acc={result.citation_accuracy:.2f}"
                )

            results.append(asdict(result))

    df = pd.DataFrame(results)
    print(f"\n  Repetition {rep_id} complete: {total - errors}/{total} successful, {errors} errors")
    return df


# ─────────────────────────────────────────────
# Quality scoring
# ─────────────────────────────────────────────
def compute_quality_scores(
    results_df: pd.DataFrame,
    *,
    ollama_url: str,
    run_judge: bool = False,
    judge_model: str = DEFAULT_MODEL,
) -> pd.DataFrame:
    """Compute quality metrics for all results."""
    print("\n📊 Computing answer quality metrics...")

    quality_rows = []
    total = len(results_df)

    for idx, (_, row) in enumerate(results_df.iterrows()):
        qid = row["question_id"]
        ref = get_reference(qid)

        if ref is None:
            # No reference for this question
            quality_rows.append({
                "question_id": qid,
                "mode": row["mode"],
                "rouge_l": 0.0,
                "semantic_similarity": 0.0,
                "faithfulness": 0.0,
                "answer_completeness": 0.0,
                "judge_correctness": 0,
                "judge_completeness": 0,
                "judge_citation_quality": 0,
                "judge_coherence": 0,
                "judge_mean": 0.0,
            })
            continue

        response = row.get("response", "")
        if not response or pd.isna(response):
            quality_rows.append({
                "question_id": qid,
                "mode": row["mode"],
                "rouge_l": 0.0,
                "semantic_similarity": 0.0,
                "faithfulness": 0.0,
                "answer_completeness": 0.0,
                "judge_correctness": 0,
                "judge_completeness": 0,
                "judge_citation_quality": 0,
                "judge_coherence": 0,
                "judge_mean": 0.0,
            })
            continue

        print(f"  [{idx+1}/{total}] {qid} / {row['mode']}", end="", flush=True)

        # Build context docs from the response metadata
        context_docs = []
        cited_ids = str(row.get("cited_ids", "")).split(",")
        for cid in cited_ids:
            if cid.strip():
                context_docs.append({"doc_id": cid.strip(), "text": ""})

        scores = score_single_response(
            question_id=qid,
            variant_name=row["mode"],
            question_text=row.get("question", ""),
            response=response,
            context_docs=context_docs,
            reference_text=ref.reference_text,
            key_facts=ref.key_facts,
            ollama_url=ollama_url,
            run_judge=run_judge,
            judge_model=judge_model,
        )

        quality_rows.append({
            "question_id": qid,
            "mode": row["mode"],
            "rouge_l": scores.rouge_l,
            "semantic_similarity": scores.semantic_similarity,
            "faithfulness": scores.faithfulness,
            "answer_completeness": scores.answer_completeness,
            "judge_correctness": scores.judge_correctness,
            "judge_completeness": scores.judge_completeness,
            "judge_citation_quality": scores.judge_citation_quality,
            "judge_coherence": scores.judge_coherence,
            "judge_mean": scores.judge_mean,
        })

        print(
            f" | ROUGE={scores.rouge_l:.3f} "
            f"faith={scores.faithfulness:.3f} "
            f"comp={scores.answer_completeness:.3f}"
        )

    quality_df = pd.DataFrame(quality_rows)

    # Merge quality metrics into results
    merged = results_df.merge(
        quality_df,
        on=["question_id", "mode"],
        how="left",
    )
    print(f"  ✅ Quality metrics computed for {len(quality_rows)} evaluations")
    return merged


# ─────────────────────────────────────────────
# Analysis & reporting
# ─────────────────────────────────────────────
def run_analysis(
    all_results: pd.DataFrame,
    output_dir: Path,
    *,
    run_meta: dict,
) -> None:
    """Run statistical analysis and generate reports."""
    from evaluation.report import generate_report
    from evaluation.visualization import generate_all_figures

    analysis_dir = output_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    # 1. Summary statistics
    print("\n📈 Computing summary statistics...")
    metric_cols = [
        c for c in all_results.columns
        if c in [
            "retrieval_precision", "source_coverage",
            "citation_count", "citation_accuracy",
            "context_utilization", "latency_seconds",
            "rouge_l", "semantic_similarity",
            "faithfulness", "answer_completeness", "judge_mean",
        ]
    ]

    summary = all_results.groupby("mode")[metric_cols].agg(["mean", "std"]).round(4)
    summary.to_csv(analysis_dir / "ablation_summary.csv")
    print("  ✅ Ablation summary saved")

    # Category breakdown
    cat_summary = all_results.groupby(["mode", "category"])[metric_cols].mean().round(4)
    cat_summary.to_csv(analysis_dir / "category_breakdown.csv")
    print("  ✅ Category breakdown saved")

    # 2. Statistical tests
    print("\n🔬 Running statistical significance tests...")
    stat_report = run_full_statistical_analysis(all_results, metrics=metric_cols)

    # Save Friedman results
    friedman_rows = [
        {
            "metric": fr.metric,
            "statistic": fr.statistic,
            "p_value": fr.p_value,
            "significant": fr.significant,
            "n_variants": fr.n_variants,
            "n_questions": fr.n_questions,
        }
        for fr in stat_report.friedman_tests
    ]
    pd.DataFrame(friedman_rows).to_csv(analysis_dir / "friedman_tests.csv", index=False)

    # Save pairwise results
    pairwise_df = pairwise_to_dataframe(stat_report.pairwise_tests)
    pairwise_df.to_csv(analysis_dir / "pairwise_significance.csv", index=False)

    # Save significance matrices
    for metric, matrix in stat_report.significance_matrix.items():
        matrix.to_csv(analysis_dir / f"sig_matrix_{metric}.csv")

    # Save summary as JSON
    with open(analysis_dir / "statistical_tests.json", "w") as f:
        json.dump(stat_report.summary, f, indent=2, default=str)

    n_sig = sum(1 for pr in stat_report.pairwise_tests if pr.significant)
    print(f"  ✅ Friedman tests: {len(stat_report.friedman_tests)} metrics")
    print(f"  ✅ Pairwise tests: {len(stat_report.pairwise_tests)} pairs ({n_sig} significant)")

    # 3. Generate figures
    print("\n🎨 Generating publication-quality figures...")
    try:
        generated = generate_all_figures(
            all_results,
            output_dir,
            significance_matrices=stat_report.significance_matrix,
            metrics=[m for m in metric_cols if m != "citation_count"],
        )
        print(f"  ✅ Generated {len(generated)} figures")
    except Exception as e:
        print(f"  ⚠️  Figure generation failed: {e}")

    # 4. Generate markdown report
    print("\n📝 Generating ablation report...")
    report = _generate_ablation_report(all_results, stat_report, run_meta)
    report_path = output_dir / "ablation_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  ✅ Report saved: {report_path}")

    # Also generate standard report
    try:
        std_report = generate_report(all_results, run_meta)
        (output_dir / "standard_report.md").write_text(std_report, encoding="utf-8")
        print("  ✅ Standard report saved")
    except Exception as e:
        print(f"  ⚠️  Standard report failed: {e}")


def _generate_ablation_report(
    results_df: pd.DataFrame,
    stat_report,
    run_meta: dict,
) -> str:
    """Generate comprehensive ablation study markdown report."""
    lines = [
        "# Ablation Study Report",
        "",
        f"**Generated**: {datetime.now().isoformat()}",
        f"**Model**: {run_meta.get('model', 'unknown')}",
        f"**Questions**: {run_meta.get('n_questions', '?')}",
        f"**Variants**: {run_meta.get('n_variants', '?')}",
        f"**Total evaluations**: {run_meta.get('n_evaluations', '?')}",
    ]

    if run_meta.get("tag"):
        lines.append(f"**Tag**: {run_meta['tag']}")
    if run_meta.get("duration_seconds"):
        lines.append(f"**Duration**: {run_meta['duration_seconds']:.1f}s")

    n_errors = run_meta.get("n_errors", 0)
    if n_errors > 0:
        lines.append(f"\n> [!WARNING]\n> {n_errors} evaluations encountered errors.")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Ablation table
    lines.append("## System Variant Performance")
    lines.append("")

    metric_cols = [
        c for c in [
            "retrieval_precision", "source_coverage",
            "citation_count", "citation_accuracy",
            "context_utilization", "latency_seconds",
            "rouge_l", "semantic_similarity",
            "faithfulness", "answer_completeness", "judge_mean",
        ]
        if c in results_df.columns
    ]

    summary = results_df.groupby("mode")[metric_cols].mean().round(4)

    # Table header
    header_labels = {
        "retrieval_precision": "Ret. Prec.",
        "source_coverage": "Src. Cov.",
        "citation_count": "Cit. Count",
        "citation_accuracy": "Cit. Acc.",
        "context_utilization": "Ctx. Util.",
        "latency_seconds": "Latency (s)",
        "rouge_l": "ROUGE-L",
        "semantic_similarity": "Sem. Sim.",
        "faithfulness": "Faith.",
        "answer_completeness": "Compl.",
        "judge_mean": "Judge",
    }

    cols = [header_labels.get(c, c) for c in metric_cols]
    lines.append("| Variant | " + " | ".join(cols) + " |")
    lines.append("| --- | " + " | ".join(["---:"] * len(cols)) + " |")

    variant_order = [
        "LLM-only", "Single-source RAG", "Two-source RAG",
        "Multi-source RAG", "Multi-source + Analysis",
        "Multi-source + Reliability", "Full framework",
    ]

    for v in variant_order:
        if v in summary.index:
            vals = [f"{summary.loc[v, c]:.4f}" if "latency" not in c else f"{summary.loc[v, c]:.2f}"
                    for c in metric_cols]
            lines.append(f"| {v} | " + " | ".join(vals) + " |")

    lines.append("")

    # Key deltas
    lines.append("## Key Comparisons (Δ)")
    lines.append("")

    comparisons = [
        ("LLM-only", "Multi-source RAG", "Effect of retrieval"),
        ("Multi-source RAG", "Full framework", "Effect of analysis + reliability"),
        ("Multi-source RAG", "Multi-source + Analysis", "Effect of pre-analysis only"),
        ("Multi-source RAG", "Multi-source + Reliability", "Effect of reliability only"),
        ("LLM-only", "Full framework", "Full system vs baseline"),
    ]

    for va, vb, desc in comparisons:
        if va in summary.index and vb in summary.index:
            lines.append(f"### {desc}: {va} → {vb}")
            lines.append("")
            key_metrics = ["retrieval_precision", "citation_accuracy", "context_utilization"]
            key_metrics = [m for m in key_metrics if m in metric_cols]
            if "rouge_l" in metric_cols:
                key_metrics.append("rouge_l")
            if "faithfulness" in metric_cols:
                key_metrics.append("faithfulness")

            for m in key_metrics:
                delta = summary.loc[vb, m] - summary.loc[va, m]
                sign = "+" if delta >= 0 else ""
                lines.append(f"- **{header_labels.get(m, m)}**: {summary.loc[va, m]:.4f} → {summary.loc[vb, m]:.4f} ({sign}{delta:.4f})")
            lines.append("")

    # Statistical significance
    lines.append("## Statistical Significance")
    lines.append("")

    if stat_report.friedman_tests:
        lines.append("### Friedman Omnibus Tests")
        lines.append("")
        lines.append("| Metric | χ² | p-value | Significant |")
        lines.append("| --- | ---: | ---: | :---: |")
        for fr in stat_report.friedman_tests:
            sig = "✅" if fr.significant else "—"
            lines.append(f"| {header_labels.get(fr.metric, fr.metric)} | {fr.statistic:.4f} | {fr.p_value:.6f} | {sig} |")
        lines.append("")

    # Significant pairwise comparisons
    sig_pairs = [pr for pr in stat_report.pairwise_tests if pr.significant]
    if sig_pairs:
        lines.append("### Significant Pairwise Comparisons (Wilcoxon + Holm-Bonferroni)")
        lines.append("")
        lines.append("| Metric | Variant A | Variant B | p-value | Cliff's δ | Effect |")
        lines.append("| --- | --- | --- | ---: | ---: | --- |")
        for pr in sig_pairs:
            lines.append(
                f"| {header_labels.get(pr.metric, pr.metric)} "
                f"| {pr.variant_a} | {pr.variant_b} "
                f"| {pr.p_value:.6f} | {pr.effect_size:.4f} | {pr.effect_category} |"
            )
        lines.append("")

    # Category breakdown
    lines.append("## Performance by Question Category")
    lines.append("")

    categories = sorted(results_df["category"].unique())
    for cat in categories:
        cat_df = results_df[results_df["category"] == cat]
        cat_summary = cat_df.groupby("mode")[metric_cols].mean().round(4)

        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Variant | " + " | ".join(cols[:6]) + " |")
        lines.append("| --- | " + " | ".join(["---:"] * min(6, len(cols))) + " |")

        for v in variant_order:
            if v in cat_summary.index:
                vals = [f"{cat_summary.loc[v, c]:.4f}" for c in metric_cols[:6]]
                lines.append(f"| {v} | " + " | ".join(vals) + " |")
        lines.append("")

    # Error log
    error_df = results_df[results_df["error"].notna() & (results_df["error"] != "")]
    if not error_df.empty:
        lines.append("## Errors")
        lines.append("")
        for _, row in error_df.iterrows():
            lines.append(f"- **{row['question_id']}** / {row['mode']}: {row['error']}")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Run the 7-variant ablation study benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama API URL")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="Retrieval top-K")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="LLM temperature")
    parser.add_argument("--num-ctx", type=int, default=DEFAULT_NUM_CTX, help="Context window")
    parser.add_argument("--repeats", type=int, default=1, help="Number of repetitions (for statistical power)")
    parser.add_argument("--tag", type=str, default=None, help="Run tag for identification")
    parser.add_argument("--quick", action="store_true", help="Quick mode: 1 question per category (5 total)")
    parser.add_argument("--judge", action="store_true", help="Run LLM-as-judge scoring")
    parser.add_argument("--judge-model", default=None, help="Model for LLM judge (default: same as --model)")
    parser.add_argument("--analyze-only", action="store_true", help="Only run analysis on existing results")
    parser.add_argument("--results-dir", type=str, default=None, help="Path to existing results directory")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip preflight checks")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M")
    run_id = f"ablation_{timestamp}_{args.model.replace(':', '_').replace('/', '_')}"
    if args.tag:
        run_id += f"_{args.tag}"

    # Determine output directory
    if args.results_dir:
        output_dir = Path(args.results_dir)
    else:
        output_dir = Path("data/evaluation") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    print(f"🧪 Ablation Study: {run_id}")
    print(f"📁 Output: {output_dir}")

    # Analyze-only mode
    if args.analyze_only:
        print("\n📊 Analyze-only mode — loading existing results...")
        csvs = sorted(raw_dir.glob("rep_*_results.csv"))
        if not csvs:
            csvs = sorted(output_dir.glob("*.csv"))
        if not csvs:
            print("❌ No CSV results found in", raw_dir)
            sys.exit(1)

        all_dfs = [pd.read_csv(c) for c in csvs]
        all_results = pd.concat(all_dfs, ignore_index=True)
        # Average across repetitions
        group_cols = ["question_id", "category", "question", "mode"]
        numeric_cols = all_results.select_dtypes(include=[np.number]).columns
        avg_results = all_results.groupby(group_cols, as_index=False)[numeric_cols].mean()

        meta_path = output_dir / "ablation_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                run_meta = json.load(f)
        else:
            run_meta = {"model": "unknown", "n_questions": len(avg_results["question_id"].unique()),
                        "n_variants": len(avg_results["mode"].unique()),
                        "n_evaluations": len(avg_results)}

        run_analysis(avg_results, output_dir, run_meta=run_meta)
        print("\n✅ Analysis complete!")
        return

    # Preflight
    if not args.skip_preflight:
        if not preflight_check(args.ollama_url, args.model):
            print("❌ Preflight failed. Use --skip-preflight to override.")
            sys.exit(1)

    # Select questions
    if args.quick:
        # Pick 1 question per category
        seen_cats = set()
        questions = []
        for q in BENCHMARK_QUESTIONS:
            if q.category not in seen_cats:
                questions.append(q)
                seen_cats.add(q.category)
        print(f"⚡ Quick mode: {len(questions)} questions (1 per category)")
    else:
        questions = BENCHMARK_QUESTIONS

    variants = SYSTEM_VARIANTS

    # Run repetitions
    all_rep_dfs = []
    total_start = time.time()

    for rep in range(1, args.repeats + 1):
        rep_df = run_single_repetition(
            questions, variants,
            model=args.model,
            ollama_url=args.ollama_url,
            top_k=args.top_k,
            temperature=args.temperature,
            num_ctx=args.num_ctx,
            rep_id=rep,
        )

        # Save raw results
        rep_path = raw_dir / f"rep_{rep}_results.csv"
        rep_df.to_csv(rep_path, index=False)
        print(f"  💾 Saved: {rep_path}")

        all_rep_dfs.append(rep_df)

    total_duration = time.time() - total_start

    # Combine repetitions
    all_results = pd.concat(all_rep_dfs, ignore_index=True)

    # Average across repetitions
    group_cols = ["question_id", "category", "question", "mode"]
    existing_group = [c for c in group_cols if c in all_results.columns]
    numeric_cols = all_results.select_dtypes(include=[np.number]).columns.tolist()
    avg_results = all_results.groupby(existing_group, as_index=False)[numeric_cols].mean()

    # Compute quality scores
    avg_results = compute_quality_scores(
        avg_results,
        ollama_url=args.ollama_url,
        run_judge=args.judge,
        judge_model=args.judge_model or args.model,
    )

    # Save combined results
    avg_results.to_csv(output_dir / "ablation_results.csv", index=False)

    # Build run metadata
    n_errors = int(all_results["error"].notna().sum() if "error" in all_results.columns else 0)
    n_errors = max(0, n_errors - int((all_results["error"] == "").sum() if "error" in all_results.columns else 0))

    run_meta = {
        "run_id": run_id,
        "model": args.model,
        "tag": args.tag,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_questions": len(questions),
        "n_variants": len(variants),
        "n_evaluations": len(avg_results),
        "n_repetitions": args.repeats,
        "top_k": args.top_k,
        "temperature": args.temperature,
        "num_ctx": args.num_ctx,
        "duration_seconds": round(total_duration, 1),
        "n_errors": n_errors,
        "judge_enabled": args.judge,
        "quick_mode": args.quick,
        "variants": [v.name for v in variants],
    }

    with open(output_dir / "ablation_meta.json", "w") as f:
        json.dump(run_meta, f, indent=2)

    # Run analysis
    run_analysis(avg_results, output_dir, run_meta=run_meta)

    # Final summary
    print(f"\n{'='*60}")
    print("  ✅ ABLATION STUDY COMPLETE")
    print(f"{'='*60}")
    print(f"  Run ID:      {run_id}")
    print(f"  Variants:    {len(variants)}")
    print(f"  Questions:   {len(questions)}")
    print(f"  Repetitions: {args.repeats}")
    print(f"  Evaluations: {len(avg_results)}")
    print(f"  Errors:      {n_errors}")
    print(f"  Duration:    {total_duration:.1f}s ({total_duration/60:.1f}min)")
    print(f"  Output:      {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
