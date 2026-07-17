"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import { getCtdProfile, getDataCatalog, getSstData, getTaxaSample } from "@/lib/api";
import type {
  CtdProfileResponse,
  DataCatalogResponse,
  SstDailyPoint,
  SstDataResponse,
  SstPoint,
  TaxaEntry,
  TaxaSampleResponse,
} from "@/types";

type DataView = "ctd" | "taxa" | "sst";

const ctdLabels: Record<string, string> = {
  temperature: "Temperature",
  salinity: "Salinity",
  do_percent: "DO %",
  chl_a: "Chl-a",
  turbidity: "Turbidity",
  sigma_t: "Sigma-t",
  do_mg_l: "DO mg/L",
  ph: "pH",
  par: "PAR",
};

export default function DataPage() {
  const [catalog, setCatalog] = useState<DataCatalogResponse | null>(null);
  const [view, setView] = useState<DataView>("ctd");
  const [ctdSample, setCtdSample] = useState("");
  const [taxaSample, setTaxaSample] = useState("");
  const [selectedVars, setSelectedVars] = useState<string[]>([]);
  const [ctdProfile, setCtdProfile] = useState<CtdProfileResponse | null>(null);
  const [taxa, setTaxa] = useState<TaxaSampleResponse | null>(null);
  const [sst, setSst] = useState<SstDataResponse | null>(null);
  const [sstFrom, setSstFrom] = useState("");
  const [sstTo, setSstTo] = useState("");
  const [sstLimit, setSstLimit] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getDataCatalog()
      .then((payload) => {
        setCatalog(payload);
        const firstCtd = payload.ctd_samples[0] || "";
        const firstTaxa = payload.taxa_samples[0] || "";
        setCtdSample(firstCtd);
        setTaxaSample(firstTaxa);
        setSelectedVars(payload.ctd_variables.slice(0, 4));
        if (firstCtd) void loadCtd(firstCtd);
        if (firstTaxa) void loadTaxa(firstTaxa);
        void loadSst();
      })
      .catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadCtd(sampleId = ctdSample) {
    if (!sampleId) return;
    setLoading(true);
    setError("");
    try {
      const payload = await getCtdProfile(sampleId);
      setCtdProfile(payload);
      setSelectedVars((current) => {
        const valid = current.filter((name) => payload.variables.includes(name));
        return valid.length ? valid : payload.variables.slice(0, 4);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "CTD request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadTaxa(sampleId = taxaSample) {
    if (!sampleId) return;
    setLoading(true);
    setError("");
    try {
      setTaxa(await getTaxaSample(sampleId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taxa request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadSst() {
    setLoading(true);
    setError("");
    try {
      setSst(await getSstData({
        time_from: sstFrom || undefined,
        time_to: sstTo || undefined,
        limit: sstLimit,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "SST request failed");
    } finally {
      setLoading(false);
    }
  }

  function submitSst(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadSst();
  }

  const ctdTableRows = useMemo(() => {
    return (ctdProfile?.rows || []).slice(0, 120).map((row) => {
      const next: Record<string, unknown> = { depth_m: row.depth_m };
      selectedVars.forEach((variable) => {
        next[variable] = row[variable];
      });
      return next;
    });
  }, [ctdProfile, selectedVars]);

  return (
    <section>
      <header className="page-header">
        <h2>Data</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label="Data views">
        <button className={view === "ctd" ? "active" : ""} onClick={() => setView("ctd")} type="button">
          CTD Profiles
        </button>
        <button className={view === "taxa" ? "active" : ""} onClick={() => setView("taxa")} type="button">
          Taxa
        </button>
        <button className={view === "sst" ? "active" : ""} onClick={() => setView("sst")} type="button">
          SST
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {view === "ctd" ? (
        <section className="data-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="ctd-sample" title="CTD sample identifier to profile by depth.">
              <span>Sample</span>
              <select
                id="ctd-sample"
                className="field"
                value={ctdSample}
                onChange={(event) => {
                  setCtdSample(event.target.value);
                  void loadCtd(event.target.value);
                }}
              >
                {(catalog?.ctd_samples || []).map((sample) => (
                  <option key={sample} value={sample}>
                    {sample}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary-button" disabled={loading || !ctdSample} onClick={() => void loadCtd()} type="button">
              <RefreshCw size={15} aria-hidden="true" />
              Refresh
            </button>
          </div>

          <div className="summary-strip">
            <SummaryCell label="Depth points" value={formatCell(ctdProfile?.summary?.n_depth_points)} />
            <SummaryCell label="Max depth" value={formatMetric(ctdProfile?.summary?.max_depth_m, "m")} />
            <SummaryCell label="Surface T" value={formatMetric(ctdProfile?.summary?.surface_temperature, "C")} />
            <SummaryCell label="Mean salinity" value={formatMetric(ctdProfile?.summary?.mean_salinity, "PSU")} />
          </div>

          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">Depth Profiles</h3>
              <div className="variable-grid">
                {(ctdProfile?.variables || catalog?.ctd_variables || []).map((variable) => (
                  <label className="checkbox-row" key={variable} title={`Toggle ${variable} profile.`}>
                    <input
                      checked={selectedVars.includes(variable)}
                      onChange={(event) => {
                        setSelectedVars((current) =>
                          event.target.checked
                            ? [...current, variable]
                            : current.filter((name) => name !== variable),
                        );
                      }}
                      type="checkbox"
                    />
                    <span>{ctdLabels[variable] || variable}</span>
                  </label>
                ))}
              </div>
            </div>
            <DepthProfileChart rows={ctdProfile?.rows || []} variables={selectedVars} />
          </section>

          <section className="data-section">
            <h3 className="section-title">Profile Table</h3>
            <DataTable columns={["depth_m", ...selectedVars]} rows={ctdTableRows} rowKeyColumn="depth_m" />
          </section>
        </section>
      ) : null}

      {view === "taxa" ? (
        <section className="data-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="taxa-sample" title="Metagenome sample to inspect.">
              <span>Sample</span>
              <select
                id="taxa-sample"
                className="field"
                value={taxaSample}
                onChange={(event) => {
                  setTaxaSample(event.target.value);
                  void loadTaxa(event.target.value);
                }}
              >
                {(catalog?.taxa_samples || []).map((sample) => (
                  <option key={sample} value={sample}>
                    {sample}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary-button" disabled={loading || !taxaSample} onClick={() => void loadTaxa()} type="button">
              <RefreshCw size={15} aria-hidden="true" />
              Refresh
            </button>
          </div>

          <div className="summary-strip">
            <SummaryCell label="Runs" value={formatCell(taxa?.context?.n_runs)} />
            <SummaryCell label="Reads >1kb" value={formatCell(taxa?.context?.sum_reads_gt1kb)} />
            <SummaryCell label="Kraken genera" value={taxa?.kraken_top.length ?? "..."} />
            <SummaryCell label="MetaEuk genera" value={taxa?.metaeuk_top.length ?? "..."} />
          </div>

          <div className="taxa-grid">
            <BarPanel title="Kraken Top Genera" entries={taxa?.kraken_top || []} />
            <BarPanel title="MetaEuk Top Genera" entries={taxa?.metaeuk_top || []} />
            <BarPanel title="Dominant Groups" entries={taxa?.upper_groups || []} />
          </div>
        </section>
      ) : null}

      {view === "sst" ? (
        <section className="data-view">
          <form className="data-controls" onSubmit={submitSst}>
            <label className="settings-field" htmlFor="sst-from" title="Inclusive lower bound for SST timestamps.">
              <span>From</span>
              <input id="sst-from" className="field" type="date" value={sstFrom} onChange={(event) => setSstFrom(event.target.value)} />
            </label>
            <label className="settings-field" htmlFor="sst-to" title="Inclusive upper bound for SST timestamps.">
              <span>To</span>
              <input id="sst-to" className="field" type="date" value={sstTo} onChange={(event) => setSstTo(event.target.value)} />
            </label>
            <label className="settings-field" htmlFor="sst-limit" title="Maximum hourly SST observations to render.">
              <span>Limit</span>
              <select id="sst-limit" className="field" value={sstLimit} onChange={(event) => setSstLimit(Number(event.target.value))}>
                <option value={250}>250</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
                <option value={2000}>2000</option>
                <option value={5000}>5000</option>
              </select>
            </label>
            <button className="button" disabled={loading}>
              Apply
            </button>
          </form>

          <div className="summary-strip">
            <SummaryCell label="Observations" value={sst?.observations ?? "..."} />
            <SummaryCell label="Days" value={sst?.days ?? "..."} />
            <SummaryCell label="Mean SST" value={formatMetric(sst?.stats.mean_sst, "C")} />
            <SummaryCell label="Max SST" value={formatMetric(sst?.stats.max_sst, "C")} />
          </div>

          <section className="data-section">
            <h3 className="section-title">Point SST</h3>
            <SstPointChart points={sst?.points || []} />
          </section>
          <section className="data-section">
            <h3 className="section-title">Daily Regional Range</h3>
            <SstDailyChart points={sst?.daily || []} />
          </section>
        </section>
      ) : null}
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DepthProfileChart({ rows, variables }: { rows: Record<string, unknown>[]; variables: string[] }) {
  if (!rows.length || !variables.length) {
    return <p className="empty-state">No profile variables selected.</p>;
  }
  return (
    <div className="profile-grid">
      {variables.map((variable) => (
        <ProfilePanel key={variable} rows={rows} variable={variable} />
      ))}
    </div>
  );
}

function ProfilePanel({ rows, variable }: { rows: Record<string, unknown>[]; variable: string }) {
  const points = rows
    .map((row) => ({ depth: toNumber(row.depth_m), value: toNumber(row[variable]) }))
    .filter((point): point is { depth: number; value: number } => point.depth !== null && point.value !== null)
    .sort((a, b) => a.depth - b.depth);
  if (!points.length) {
    return <p className="empty-state">{variable}: no values.</p>;
  }
  const width = 260;
  const height = 280;
  const pad = { top: 18, right: 14, bottom: 34, left: 44 };
  const minDepth = Math.min(...points.map((point) => point.depth));
  const maxDepth = Math.max(...points.map((point) => point.depth));
  const minValue = Math.min(...points.map((point) => point.value));
  const maxValue = Math.max(...points.map((point) => point.value));
  const x = (value: number) => pad.left + safeRatio(value - minValue, maxValue - minValue) * (width - pad.left - pad.right);
  const y = (depth: number) => pad.top + safeRatio(depth - minDepth, maxDepth - minDepth) * (height - pad.top - pad.bottom);
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"} ${x(point.value)} ${y(point.depth)}`).join(" ");
  return (
    <svg className="profile-chart" viewBox={`0 0 ${width} ${height}`} role="img">
      <title>{`${ctdLabels[variable] || variable} by depth`}</title>
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
      <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      <path d={line} />
      {points.map((point, index) => (
        <circle key={`${point.depth}-${index}`} cx={x(point.value)} cy={y(point.depth)} r={2.4}>
          <title>{`${point.depth} m: ${formatNumber(point.value)}`}</title>
        </circle>
      ))}
      <text x={pad.left} y={13}>{ctdLabels[variable] || variable}</text>
      <text x={6} y={pad.top + 4}>{formatNumber(minDepth)}m</text>
      <text x={6} y={height - pad.bottom}>{formatNumber(maxDepth)}m</text>
      <text x={pad.left} y={height - 11}>{formatNumber(minValue)}</text>
      <text x={width - pad.right} y={height - 11} textAnchor="end">{formatNumber(maxValue)}</text>
    </svg>
  );
}

function BarPanel({ title, entries }: { title: string; entries: TaxaEntry[] }) {
  return (
    <section className="data-section">
      <h3 className="section-title">{title}</h3>
      {entries.length ? <HorizontalBars entries={entries} /> : <p className="empty-state">No taxa values for this sample.</p>}
    </section>
  );
}

function HorizontalBars({ entries }: { entries: TaxaEntry[] }) {
  const maxValue = Math.max(1, ...entries.map((entry) => entry.value));
  return (
    <div className="bar-list">
      {entries.map((entry) => (
        <div className="bar-row" key={entry.label}>
          <span title={entry.label}>{entry.label}</span>
          <div className="meter-track">
            <div style={{ width: `${(entry.value / maxValue) * 100}%` }} />
          </div>
          <strong>{formatNumber(entry.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function SstPointChart({ points }: { points: SstPoint[] }) {
  const prepared = points.map((point, index) => ({ x: Date.parse(point.time_jst), y: point.sst, label: point.time_jst, index }));
  return <LineChart points={prepared} emptyText="No SST point observations." />;
}

function SstDailyChart({ points }: { points: SstDailyPoint[] }) {
  const prepared = points
    .map((point, index) => ({
      x: Date.parse(point.date_jst),
      y: typeof point.mean_sst === "number" ? point.mean_sst : null,
      min: typeof point.min_sst === "number" ? point.min_sst : null,
      max: typeof point.max_sst === "number" ? point.max_sst : null,
      label: point.date_jst,
      index,
    }))
    .filter((point): point is { x: number; y: number; min: number | null; max: number | null; label: string; index: number } => point.y !== null);
  return <LineChart points={prepared} emptyText="No daily SST summaries." ranges />;
}

function LineChart({
  points,
  emptyText,
  ranges = false,
}: {
  points: Array<{ x: number; y: number; min?: number | null; max?: number | null; label: string; index: number }>;
  emptyText: string;
  ranges?: boolean;
}) {
  const valid = points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!valid.length) return <p className="empty-state">{emptyText}</p>;
  const width = 820;
  const height = 280;
  const pad = { top: 18, right: 18, bottom: 38, left: 58 };
  const allY = valid.flatMap((point) => [point.y, point.min, point.max].filter((value): value is number => typeof value === "number"));
  const minX = Math.min(...valid.map((point) => point.x));
  const maxX = Math.max(...valid.map((point) => point.x));
  const minYRaw = Math.min(...allY);
  const maxYRaw = Math.max(...allY);
  const yPad = maxYRaw === minYRaw ? 1 : (maxYRaw - minYRaw) * 0.08;
  const minY = minYRaw - yPad;
  const maxY = maxYRaw + yPad;
  const xScale = (value: number) => pad.left + safeRatio(value - minX, maxX - minX) * (width - pad.left - pad.right);
  const yScale = (value: number) => height - pad.bottom - safeRatio(value - minY, maxY - minY) * (height - pad.top - pad.bottom);
  const line = valid.map((point, index) => `${index === 0 ? "M" : "L"} ${xScale(point.x)} ${yScale(point.y)}`).join(" ");
  return (
    <div className="chart-wrap">
      <svg className="simple-chart" viewBox={`0 0 ${width} ${height}`} role="img">
        <title>SST time series</title>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{formatNumber(maxYRaw)}</text>
        <text x={8} y={height - pad.bottom}>{formatNumber(minYRaw)}</text>
        <text x={pad.left} y={height - 12}>{formatDate(valid[0].label)}</text>
        <text x={width - pad.right} y={height - 12} textAnchor="end">{formatDate(valid[valid.length - 1].label)}</text>
        {ranges
          ? valid.map((point) =>
              typeof point.min === "number" && typeof point.max === "number" ? (
                <line className="range-line" key={`${point.label}-range`} x1={xScale(point.x)} y1={yScale(point.min)} x2={xScale(point.x)} y2={yScale(point.max)} />
              ) : null,
            )
          : null}
        <path d={line} />
        {valid.length <= 220
          ? valid.map((point) => (
              <circle key={`${point.label}-${point.index}`} cx={xScale(point.x)} cy={yScale(point.y)} r={2.4}>
                <title>{`${point.label}: ${formatNumber(point.y)} C`}</title>
              </circle>
            ))
          : null}
      </svg>
    </div>
  );
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

function formatMetric(value: unknown, unit: string): string {
  const number = toNumber(value);
  return number === null ? "NA" : `${formatNumber(number)} ${unit}`;
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function formatDate(value: string): string {
  return value.length > 10 ? value.slice(0, 10) : value;
}
