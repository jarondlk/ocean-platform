"use client";

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import { getAnalysis } from "@/lib/api";
import { useAppPreferences } from "@/lib/preferences";
import type { AnalysisResponse } from "@/types";

type AnalysisView = "trends" | "correlations" | "diversity" | "cooccurrence" | "reliability";
type ReliabilityView = "sst_ctd" | "gap" | "diversity_prediction" | "corroboration";
type AnalysisScope = "all" | "analysis" | "reliability";

const trendLabels: Record<string, string> = {
  mean_temperature: "Mean temperature",
  mean_salinity: "Mean salinity",
  mean_do_percent: "Mean DO %",
  mean_chl_a: "Mean chl-a",
  mean_turbidity: "Mean turbidity",
  surface_temperature: "Surface temperature",
  bottom_temperature: "Bottom temperature",
  strat_index: "Stratification index",
};

export function AnalysisWorkbench({ scope = "all" }: { scope?: AnalysisScope }) {
  const { ui } = useAppPreferences();
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [view, setView] = useState<AnalysisView>(scope === "reliability" ? "reliability" : "trends");
  const [trendVariable, setTrendVariable] = useState("mean_temperature");
  const [significantOnly, setSignificantOnly] = useState(true);
  const [diversitySource, setDiversitySource] = useState("");
  const [pairLimit, setPairLimit] = useState(30);
  const [reliabilityView, setReliabilityView] = useState<ReliabilityView>("sst_ctd");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function load(nextPairLimit = pairLimit) {
    setLoading(true);
    setError("");
    try {
      const payload = await getAnalysis({ cooccurrence_pairs: nextPairLimit, table_limit: 700 });
      setAnalysis(payload);
      const variables = getStringArray(payload.catalog.trend_variables);
      if (variables.length && !variables.includes(trendVariable)) {
        setTrendVariable(variables[0]);
      }
      const sources = getStringArray(payload.catalog.diversity_sources);
      if (sources.length && !diversitySource) {
        setDiversitySource(sources[0]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (scope === "reliability" && view !== "reliability") {
      setView("reliability");
    }
    if (scope === "analysis" && view === "reliability") {
      setView("trends");
    }
  }, [scope, view]);

  const trendRows = getRows(analysis?.ctd_trends, "rows");
  const trendVariables = getStringArray(analysis?.catalog.trend_variables);
  const correlationRows = significantOnly
    ? getRows(analysis?.correlations, "significant")
    : getRows(analysis?.correlations, "rows");
  const diversityRows = getRows(analysis?.diversity, "rows").filter((row) => !diversitySource || row.source === diversitySource);
  const diversitySources = getStringArray(analysis?.catalog.diversity_sources);
  const cooccurrence = asRecord(analysis?.cooccurrence);
  const reliability = asRecord(analysis?.reliability);
  const selectedReliability = asRecord(reliability[reliabilityView]);
  const reliabilityRows = getRows(selectedReliability, "rows");

  const correlationSummary = asRecord(analysis?.correlations.summary);
  const reliabilitySummary = asRecord(selectedReliability.summary);
  const tabItems: { view: AnalysisView; label: string; scope: Exclude<AnalysisScope, "all"> }[] = [
    { view: "trends", label: "CTD Trends", scope: "analysis" },
    { view: "correlations", label: "Correlations", scope: "analysis" },
    { view: "diversity", label: "Diversity", scope: "analysis" },
    { view: "cooccurrence", label: "Co-occurrence", scope: "analysis" },
    { view: "reliability", label: "Reliability", scope: "reliability" },
  ];
  const visibleTabs = tabItems.filter((item) => scope === "all" || item.scope === scope);

  return (
    <section className="analysis-workbench">
      {visibleTabs.length > 1 ? (
        <div className="data-tabs" role="tablist" aria-label={ui("Analysis views")}>
          {visibleTabs.map((item) => (
            <TabButton
              active={view === item.view}
              key={item.view}
              label={item.label}
              onClick={() => setView(item.view)}
            />
          ))}
        </div>
      ) : null}

      <div className="section-toolbar">
        <span className="empty-state">{loading ? ui("Loading artifacts.") : ui("Artifacts loaded.")}</span>
        <button className="button secondary-button" onClick={() => void load()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          {ui("Refresh")}
        </button>
      </div>
      {error ? <p className="error-text">{error}</p> : null}

      {view === "trends" ? (
        <section className="analysis-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="trend-variable" title="Monthly trend variable to plot by bay.">
              <span>{ui("Variable")}</span>
              <select id="trend-variable" className="field" value={trendVariable} onChange={(event) => setTrendVariable(event.target.value)}>
                {trendVariables.map((variable) => (
                  <option key={variable} value={variable}>{trendLabels[variable] || variable}</option>
                ))}
              </select>
            </label>
          </div>
          <TrendChart rows={trendRows} variable={trendVariable} />
          <DataTable columns={["bay", "year_month", `${trendVariable}_mean`, `${trendVariable}_std`, `${trendVariable}_count`].filter((column) => trendRows.some((row) => column in row))} rows={trendRows} />
        </section>
      ) : null}

      {view === "correlations" ? (
        <section className="analysis-view">
          <div className="summary-strip">
            <SummaryCell label={ui("Pairs")} value={formatCell(correlationSummary.total)} />
            <SummaryCell label={ui("Significant")} value={formatCell(correlationSummary.significant)} />
            <SummaryCell label={ui("Genera")} value={formatCell(correlationSummary.genera)} />
            <SummaryCell label={ui("Variables")} value={formatCell(correlationSummary.env_variables)} />
          </div>
          <label className="checkbox-row" title="Restrict table and heatmap to p<0.05 rows.">
            <input checked={significantOnly} onChange={(event) => setSignificantOnly(event.target.checked)} type="checkbox" />
            <span>{ui("Significant only")}</span>
          </label>
          <CorrelationHeatmap rows={correlationRows} />
          <DataTable columns={["genus", "env_variable", "spearman_rho", "p_value", "n_samples", "significant"]} rows={correlationRows} />
        </section>
      ) : null}

      {view === "diversity" ? (
        <section className="analysis-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="diversity-source" title="Taxonomic source used for diversity metrics.">
              <span>{ui("Source")}</span>
              <select id="diversity-source" className="field" value={diversitySource} onChange={(event) => setDiversitySource(event.target.value)}>
                {diversitySources.map((source) => <option key={source} value={source}>{source}</option>)}
              </select>
            </label>
          </div>
          <DiversityChart rows={diversityRows} />
          <DataTable columns={["sample_id", "source", "bay", "year_month", "shannon_h", "simpson_1d", "richness", "evenness"]} rows={diversityRows} />
        </section>
      ) : null}

      {view === "cooccurrence" ? (
        <section className="analysis-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="pair-limit" title="Number of strongest co-occurring genus pairs to fetch.">
              <span>{ui("Top pairs")}</span>
              <select
                id="pair-limit"
                className="field"
                value={pairLimit}
                onChange={(event) => {
                  const next = Number(event.target.value);
                  setPairLimit(next);
                  void load(next);
                }}
              >
                <option value={20}>20</option>
                <option value={30}>30</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          </div>
          <CooccurrenceHeatmap payload={cooccurrence} />
          <DataTable columns={["genus_a", "genus_b", "jaccard"]} rows={getRows(cooccurrence, "top_pairs")} />
        </section>
      ) : null}

      {view === "reliability" ? (
        <section className="analysis-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="reliability-view" title="Cross-source reliability artifact to inspect.">
              <span>{ui("Check")}</span>
              <select id="reliability-view" className="field" value={reliabilityView} onChange={(event) => setReliabilityView(event.target.value as ReliabilityView)}>
                <option value="sst_ctd">SST / CTD validation</option>
                <option value="gap">Gap interpolation</option>
                <option value="diversity_prediction">Diversity prediction</option>
                <option value="corroboration">Corroboration tiers</option>
              </select>
            </label>
          </div>
          <ReliabilitySummary view={reliabilityView} summary={reliabilitySummary} payload={selectedReliability} />
          <ReliabilityChart view={reliabilityView} rows={reliabilityRows} payload={selectedReliability} />
          <DataTable columns={Object.keys(reliabilityRows[0] || {}).slice(0, 10)} rows={reliabilityRows} />
        </section>
      ) : null}
    </section>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  const { ui } = useAppPreferences();
  return <button className={active ? "active" : ""} onClick={onClick} type="button">{ui(label)}</button>;
}

function SummaryCell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TrendChart({ rows, variable }: { rows: Record<string, unknown>[]; variable: string }) {
  const meanColumn = `${variable}_mean`;
  const points = rows
    .map((row, index) => ({ x: String(row.year_month || index), y: toNumber(row[meanColumn]), bay: String(row.bay || "NA"), index }))
    .filter((point): point is { x: string; y: number; bay: string; index: number } => point.y !== null);
  return <MultiLineChart points={points} yLabel={trendLabels[variable] || variable} />;
}

function MultiLineChart({ points, yLabel }: { points: Array<{ x: string; y: number; bay: string; index: number }>; yLabel: string }) {
  if (!points.length) return <p className="empty-state">No trend points.</p>;
  const labels = Array.from(new Set(points.map((point) => point.x)));
  const bays = Array.from(new Set(points.map((point) => point.bay)));
  const width = 820;
  const height = 280;
  const pad = { top: 18, right: 18, bottom: 38, left: 58 };
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const xScale = (label: string) => pad.left + safeRatio(labels.indexOf(label), Math.max(1, labels.length - 1)) * (width - pad.left - pad.right);
  const yScale = (value: number) => height - pad.bottom - safeRatio(value - minY, maxY - minY) * (height - pad.top - pad.bottom);
  return (
    <div className="chart-wrap">
      <svg className="simple-chart analysis-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>{yLabel}</title>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{formatNumber(maxY)}</text>
        <text x={8} y={height - pad.bottom}>{formatNumber(minY)}</text>
        <text x={pad.left} y={height - 12}>{labels[0]}</text>
        <text x={width - pad.right} y={height - 12} textAnchor="end">{labels[labels.length - 1]}</text>
        {bays.map((bay, bayIndex) => {
          const series = points.filter((point) => point.bay === bay);
          const d = series.map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.x)} ${yScale(point.y)}`).join(" ");
          return <path className={`series-${bayIndex % 4}`} d={d} key={bay} />;
        })}
        {bays.map((bay, index) => <text key={bay} x={pad.left + index * 80} y={14}>{bay}</text>)}
      </svg>
    </div>
  );
}

function CorrelationHeatmap({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="empty-state">No correlation rows.</p>;
  const genera = Array.from(new Set(rows.map((row) => String(row.genus))));
  const variables = Array.from(new Set(rows.map((row) => String(row.env_variable))));
  const cell = 24;
  const left = 120;
  const top = 30;
  const width = left + variables.length * cell + 10;
  const height = top + genera.length * cell + 10;
  return (
    <div className="heatmap-wrap">
      <svg className="matrix-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>Taxa environment correlations</title>
        {variables.map((variable, index) => <text key={variable} x={left + index * cell + cell / 2} y={20} textAnchor="middle">{variable.replace("mean_", "")}</text>)}
        {genera.map((genus, rowIndex) => <text key={genus} x={left - 8} y={top + rowIndex * cell + 16} textAnchor="end">{genus}</text>)}
        {rows.map((row) => {
          const x = variables.indexOf(String(row.env_variable));
          const y = genera.indexOf(String(row.genus));
          const value = toNumber(row.spearman_rho) || 0;
          return (
            <rect key={`${row.genus}-${row.env_variable}`} x={left + x * cell} y={top + y * cell} width={cell - 1} height={cell - 1} fill={correlationColor(value)}>
              <title>{`${row.genus} / ${row.env_variable}: ${formatNumber(value)}`}</title>
            </rect>
          );
        })}
      </svg>
    </div>
  );
}

function DiversityChart({ rows }: { rows: Record<string, unknown>[] }) {
  const points = rows
    .map((row, index) => ({ x: String(row.year_month || index), y: toNumber(row.shannon_h), bay: String(row.bay || "NA"), index }))
    .filter((point): point is { x: string; y: number; bay: string; index: number } => point.y !== null);
  return <MultiLineChart points={points} yLabel="Shannon H" />;
}

function CooccurrenceHeatmap({ payload }: { payload: Record<string, unknown> }) {
  const labels = getStringArray(payload.labels).slice(0, 30);
  const matrix = Array.isArray(payload.matrix) ? payload.matrix as unknown[][] : [];
  if (!labels.length || !matrix.length) return <p className="empty-state">No co-occurrence matrix.</p>;
  const cell = 16;
  const left = 120;
  const top = 34;
  const width = left + labels.length * cell + 10;
  const height = top + labels.length * cell + 10;
  return (
    <div className="heatmap-wrap">
      <svg className="matrix-chart cooccurrence-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>Genus co-occurrence matrix</title>
        {labels.map((label, rowIndex) => <text key={label} x={left - 8} y={top + rowIndex * cell + 12} textAnchor="end">{label}</text>)}
        {labels.map((_, rowIndex) =>
          labels.map((label, colIndex) => {
            const value = toNumber(matrix[rowIndex]?.[colIndex]) || 0;
            return (
              <rect key={`${rowIndex}-${label}`} x={left + colIndex * cell} y={top + rowIndex * cell} width={cell - 1} height={cell - 1} fill={cooccurrenceColor(value)}>
                <title>{`${labels[rowIndex]} / ${label}: ${formatNumber(value)}`}</title>
              </rect>
            );
          }),
        )}
      </svg>
    </div>
  );
}

function ReliabilitySummary({ summary, payload, view }: { summary: Record<string, unknown>; payload: Record<string, unknown>; view: ReliabilityView }) {
  if (view === "corroboration") {
    const tiers = asRecord(payload.tier_counts);
    return (
      <div className="summary-strip">
        <SummaryCell label="Verified" value={formatCell(tiers.verified)} />
        <SummaryCell label="Supported" value={formatCell(tiers.supported)} />
        <SummaryCell label="Standalone" value={formatCell(tiers.standalone)} />
        <SummaryCell label="Mean score" value={formatCell(payload.mean_score)} />
      </div>
    );
  }
  const entries = Object.entries(summary).slice(0, 4);
  return (
    <div className="summary-strip">
      {entries.map(([key, value]) => <SummaryCell key={key} label={key} value={formatCell(value)} />)}
    </div>
  );
}

function ReliabilityChart({ rows, view, payload }: { rows: Record<string, unknown>[]; view: ReliabilityView; payload: Record<string, unknown> }) {
  if (view === "sst_ctd") {
    return <ScatterChart rows={rows} xKey="sst_daily_mean" yKey="ctd_surface_t" />;
  }
  if (view === "gap") {
    const points = rows
      .map((row, index) => ({ x: String(row.date || index), y: toNumber(row.interpolated_surface_t), bay: "gap", index }))
      .filter((point): point is { x: string; y: number; bay: string; index: number } => point.y !== null);
    return <MultiLineChart points={points} yLabel="Interpolated surface T" />;
  }
  if (view === "diversity_prediction") {
    return <ScatterChart rows={rows} xKey="predicted_shannon" yKey="actual_shannon" />;
  }
  return <TierBars tiers={asRecord(payload.tier_counts)} />;
}

function ScatterChart({ rows, xKey, yKey }: { rows: Record<string, unknown>[]; xKey: string; yKey: string }) {
  const points = rows
    .map((row) => ({ x: toNumber(row[xKey]), y: toNumber(row[yKey]), label: String(row.sample_id || "") }))
    .filter((point): point is { x: number; y: number; label: string } => point.x !== null && point.y !== null);
  if (!points.length) return <p className="empty-state">No scatter points.</p>;
  const width = 620;
  const height = 320;
  const pad = { top: 20, right: 20, bottom: 42, left: 58 };
  const minX = Math.min(...points.map((point) => point.x));
  const maxX = Math.max(...points.map((point) => point.x));
  const minY = Math.min(...points.map((point) => point.y));
  const maxY = Math.max(...points.map((point) => point.y));
  const x = (value: number) => pad.left + safeRatio(value - minX, maxX - minX) * (width - pad.left - pad.right);
  const y = (value: number) => height - pad.bottom - safeRatio(value - minY, maxY - minY) * (height - pad.top - pad.bottom);
  return (
    <div className="chart-wrap">
      <svg className="simple-chart scatter-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>{`${yKey} by ${xKey}`}</title>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={pad.left} y={height - 12}>{xKey}</text>
        <text x={8} y={pad.top + 4}>{yKey}</text>
        {points.map((point) => <circle key={`${point.label}-${point.x}-${point.y}`} cx={x(point.x)} cy={y(point.y)} r={3}><title>{`${point.label}: ${formatNumber(point.x)}, ${formatNumber(point.y)}`}</title></circle>)}
      </svg>
    </div>
  );
}

function TierBars({ tiers }: { tiers: Record<string, unknown> }) {
  const rows = Object.entries(tiers).map(([label, value]) => ({ label, value: toNumber(value) || 0 }));
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="bar-list">
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <span>{row.label}</span>
          <div className="meter-track"><div style={{ width: `${(row.value / max) * 100}%` }} /></div>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function getRows(value: unknown, key: string): Record<string, unknown>[] {
  const rows = asRecord(value)[key];
  return Array.isArray(rows) ? rows.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row)) : [];
}

function getStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function safeRatio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0.5 : numerator / denominator;
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function correlationColor(value: number): string {
  const strength = Math.min(1, Math.abs(value));
  const alpha = 0.18 + strength * 0.72;
  return value >= 0 ? `rgba(36, 127, 174, ${alpha})` : `rgba(159, 29, 32, ${alpha})`;
}

function cooccurrenceColor(value: number): string {
  const alpha = 0.12 + Math.min(1, value) * 0.78;
  return `rgba(86, 180, 233, ${alpha})`;
}
