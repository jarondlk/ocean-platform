"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { AnalysisWorkbench } from "@/components/AnalysisWorkbench";
import { DataTable, formatCell } from "@/components/DataTable";
import { EdnaDataView } from "@/components/EdnaDataView";
import { EdnaAnalysisView } from "@/components/EdnaAnalysisView";
import { getCtdProfile, getDataCatalog, getSstData, getTaxaSample } from "@/lib/api";
import {
  buildHref,
  resolveContextWorkspace,
  safeEvidenceIdentifier,
  safeIsoDate,
} from "@/lib/citation-navigation";
import { useAppPreferences } from "@/lib/preferences";
import type {
  CtdProfileResponse,
  DataCatalogResponse,
  SstDailyPoint,
  SstDataResponse,
  SstPoint,
  TaxaEntry,
  TaxaSampleResponse,
} from "@/types";

type DataView = "observations" | "ctd" | "taxa" | "edna" | "edna_analysis" | "sst" | "analysis" | "reliability";

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
  return (
    <Suspense fallback={<DataPageFallback />}>
      <DataPageContent />
    </Suspense>
  );
}

function DataPageContent() {
  const { ui } = useAppPreferences();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedView = searchParams.get("view");
  const requestedSampleRaw = searchParams.get("sample_id");
  const requestedSample = safeEvidenceIdentifier(requestedSampleRaw);
  const requestedFromRaw = searchParams.get("time_from");
  const requestedToRaw = searchParams.get("time_to");
  const requestedFrom = safeIsoDate(requestedFromRaw);
  const requestedTo = safeIsoDate(requestedToRaw);
  const requestedContextRaw = searchParams.get("context_id");
  const requestedContext = safeEvidenceIdentifier(requestedContextRaw);
  const contextTarget = resolveContextWorkspace(requestedContext);
  const urlView: DataView = isDataView(requestedView)
    ? requestedView
    : contextTarget?.scope || "observations";
  const [catalog, setCatalog] = useState<DataCatalogResponse | null>(null);
  const [view, setView] = useState<DataView>(urlView);
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
    setView(urlView);
  }, [urlView]);

  useEffect(() => {
    setError("");
    if (urlView === "edna" || urlView === "edna_analysis") return;
    let active = true;
    getDataCatalog()
      .then((payload) => {
        if (!active) return;
        setCatalog(payload);
        setSelectedVars(payload.ctd_variables.slice(0, 4));
      })
      .catch((err: Error) => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [urlView]);

  useEffect(() => {
    if (!catalog) return;
    setError("");

    if (urlView === "ctd") {
      if (requestedSampleRaw && !requestedSample) {
        setCtdSample("");
        setCtdProfile(null);
        setError("The requested CTD sample identifier is invalid.");
        return;
      }
      const sampleId = requestedSample || catalog.ctd_samples[0] || "";
      if (requestedSample && !catalog.ctd_samples.includes(requestedSample)) {
        setCtdSample("");
        setCtdProfile(null);
        setError(`CTD sample ${requestedSample} is not available.`);
        return;
      }
      setCtdSample(sampleId);
      if (sampleId) void loadCtd(sampleId);
      return;
    }

    if (urlView === "taxa") {
      if (requestedSampleRaw && !requestedSample) {
        setTaxaSample("");
        setTaxa(null);
        setError("The requested taxa sample identifier is invalid.");
        return;
      }
      const sampleId = requestedSample || catalog.taxa_samples[0] || "";
      if (requestedSample && !catalog.taxa_samples.includes(requestedSample)) {
        setTaxaSample("");
        setTaxa(null);
        setError(`Taxa sample ${requestedSample} is not available.`);
        return;
      }
      setTaxaSample(sampleId);
      if (sampleId) void loadTaxa(sampleId);
      return;
    }

    if (urlView === "sst") {
      if ((requestedFromRaw && !requestedFrom) || (requestedToRaw && !requestedTo)) {
        setSst(null);
        setError("The requested SST date range is invalid.");
        return;
      }
      const nextFrom = requestedFrom || "";
      const nextTo = requestedTo || "";
      setSstFrom(nextFrom);
      setSstTo(nextTo);
      void loadSst({ nextFrom, nextTo });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalog, requestedFrom, requestedFromRaw, requestedSample, requestedSampleRaw, requestedTo, requestedToRaw, urlView]);

  async function loadCtd(sampleId = ctdSample) {
    if (!sampleId) return;
    setLoading(true);
    setError("");
    setCtdProfile(null);
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
    setTaxa(null);
    try {
      setTaxa(await getTaxaSample(sampleId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Taxa request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadSst({
    nextFrom = sstFrom,
    nextTo = sstTo,
    nextLimit = sstLimit,
  }: {
    nextFrom?: string;
    nextTo?: string;
    nextLimit?: number;
  } = {}) {
    setLoading(true);
    setError("");
    setSst(null);
    try {
      setSst(await getSstData({
        time_from: nextFrom || undefined,
        time_to: nextTo || undefined,
        limit: nextLimit,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "SST request failed");
    } finally {
      setLoading(false);
    }
  }

  function submitSst(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextFrom = safeIsoDate(sstFrom);
    const nextTo = safeIsoDate(sstTo);
    if ((sstFrom && !nextFrom) || (sstTo && !nextTo)) {
      setSst(null);
      setError("The requested SST date range is invalid.");
      return;
    }
    router.replace(buildHref("/data", {
      view: "sst",
      time_from: nextFrom,
      time_to: nextTo,
    }), { scroll: false });
    if ((requestedFrom || "") === (nextFrom || "") && (requestedTo || "") === (nextTo || "")) {
      void loadSst({ nextFrom: nextFrom || "", nextTo: nextTo || "" });
    }
  }

  function changeView(nextView: DataView) {
    router.push(buildHref("/data", {
      view: nextView === "observations" ? undefined : nextView,
    }), { scroll: false });
  }

  function changeSample(nextView: "ctd" | "taxa", sampleId: string) {
    router.push(buildHref("/data", { view: nextView, sample_id: sampleId }), { scroll: false });
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
        <h2>{ui("Data")}</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label={ui("Data views")}>
        <button className={view === "observations" ? "active" : ""} onClick={() => changeView("observations")} type="button">
          {ui("Observations")}
        </button>
        <button className={view === "ctd" ? "active" : ""} onClick={() => changeView("ctd")} type="button">
          CTD
        </button>
        <button className={view === "taxa" ? "active" : ""} onClick={() => changeView("taxa")} type="button">
          {ui("Taxa")}
        </button>
        <button className={view === "edna" ? "active" : ""} onClick={() => changeView("edna")} type="button">
          eDNA
        </button>
        <button className={view === "sst" ? "active" : ""} onClick={() => changeView("sst")} type="button">
          SST
        </button>
        <button className={view === "edna_analysis" ? "active" : ""} onClick={() => changeView("edna_analysis")} type="button">eDNA analysis</button>
        <button className={view === "analysis" ? "active" : ""} onClick={() => changeView("analysis")} type="button">
          {ui("Derived Analysis")}
        </button>
        <button className={view === "reliability" ? "active" : ""} onClick={() => changeView("reliability")} type="button">
          {ui("Reliability")}
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {view === "observations" ? (
        <section className="data-view">
          <div className="summary-strip">
            <SummaryCell label={ui("CTD samples")} value={catalog?.ctd_samples.length ?? "..."} />
            <SummaryCell label={ui("Taxa samples")} value={catalog?.taxa_samples.length ?? "..."} />
            <SummaryCell label={ui("SST observations")} value={formatCell(catalog?.sst_observations)} />
            <SummaryCell label={ui("SST days")} value={formatCell(catalog?.sst_days)} />
          </div>

          <section className="dashboard-grid">
            <article className="data-section">
              <h3 className="section-title">{ui("Observation Classes")}</h3>
              <ObservationBars
                rows={[
                  { label: "CTD", value: catalog?.ctd_samples.length || 0 },
                  { label: "Taxa", value: catalog?.taxa_samples.length || 0 },
                  { label: "SST days", value: catalog?.sst_days || 0 },
                ]}
              />
            </article>
            <article className="data-section">
              <h3 className="section-title">{ui("Catalog")}</h3>
              <table className="debug-table">
                <tbody>
                  <CatalogRow label={ui("CTD variables")} value={catalog?.ctd_variables.length} />
                  <CatalogRow label={ui("Context rows")} value={catalog?.context_rows} />
                  <CatalogRow label={ui("Default CTD sample")} value={ctdSample || "NA"} />
                  <CatalogRow label={ui("Default taxa sample")} value={taxaSample || "NA"} />
                </tbody>
              </table>
            </article>
          </section>
        </section>
      ) : null}

      {view === "ctd" ? (
        <section className="data-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="ctd-sample" title="CTD sample identifier to profile by depth.">
              <span>{ui("Sample")}</span>
              <select
                id="ctd-sample"
                className="field"
                value={ctdSample}
                onChange={(event) => {
                  changeSample("ctd", event.target.value);
                }}
              >
                <option disabled value="">{ui("Select a sample")}</option>
                {(catalog?.ctd_samples || []).map((sample) => (
                  <option key={sample} value={sample}>
                    {sample}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary-button" disabled={loading || !ctdSample} onClick={() => void loadCtd()} type="button">
              <RefreshCw size={15} aria-hidden="true" />
              {ui("Refresh")}
            </button>
          </div>

          <div className="summary-strip">
            <SummaryCell label={ui("Depth points")} value={formatCell(ctdProfile?.summary?.n_depth_points)} />
            <SummaryCell label={ui("Max depth")} value={formatMetric(ctdProfile?.summary?.max_depth_m, "m")} />
            <SummaryCell label={ui("Surface T")} value={formatMetric(ctdProfile?.summary?.surface_temperature, "C")} />
            <SummaryCell label={ui("Mean salinity")} value={formatMetric(ctdProfile?.summary?.mean_salinity, "PSU")} />
          </div>

          <section className="data-section">
            <div className="section-toolbar">
              <h3 className="section-title">{ui("Depth Profiles")}</h3>
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
            <h3 className="section-title">{ui("Profile Table")}</h3>
            <DataTable columns={["depth_m", ...selectedVars]} rows={ctdTableRows} rowKeyColumn="depth_m" />
          </section>
        </section>
      ) : null}

      {view === "taxa" ? (
        <section className="data-view">
          <div className="data-controls">
            <label className="settings-field" htmlFor="taxa-sample" title="Metagenome sample to inspect.">
              <span>{ui("Sample")}</span>
              <select
                id="taxa-sample"
                className="field"
                value={taxaSample}
                onChange={(event) => {
                  changeSample("taxa", event.target.value);
                }}
              >
                <option disabled value="">{ui("Select a sample")}</option>
                {(catalog?.taxa_samples || []).map((sample) => (
                  <option key={sample} value={sample}>
                    {sample}
                  </option>
                ))}
              </select>
            </label>
            <button className="button secondary-button" disabled={loading || !taxaSample} onClick={() => void loadTaxa()} type="button">
              <RefreshCw size={15} aria-hidden="true" />
              {ui("Refresh")}
            </button>
          </div>

          <div className="summary-strip">
            <SummaryCell label={ui("Runs")} value={formatCell(taxa?.context?.n_runs)} />
            <SummaryCell label={ui("Reads >1kb")} value={formatCell(taxa?.context?.sum_reads_gt1kb)} />
            <SummaryCell label={ui("Kraken genera")} value={taxa?.kraken_top.length ?? "..."} />
            <SummaryCell label={ui("MetaEuk genera")} value={taxa?.metaeuk_top.length ?? "..."} />
          </div>

          <div className="taxa-grid">
            <BarPanel title={ui("Kraken Top Genera")} entries={taxa?.kraken_top || []} />
            <BarPanel title={ui("MetaEuk Top Genera")} entries={taxa?.metaeuk_top || []} />
            <BarPanel title={ui("Dominant Groups")} entries={taxa?.upper_groups || []} />
          </div>
        </section>
      ) : null}

      {view === "sst" ? (
        <section className="data-view">
          <form className="data-controls" onSubmit={submitSst}>
            <label className="settings-field" htmlFor="sst-from" title="Inclusive lower bound for SST timestamps.">
              <span>{ui("From")}</span>
              <input id="sst-from" className="field" type="date" value={sstFrom} onChange={(event) => setSstFrom(event.target.value)} />
            </label>
            <label className="settings-field" htmlFor="sst-to" title="Inclusive upper bound for SST timestamps.">
              <span>{ui("To")}</span>
              <input id="sst-to" className="field" type="date" value={sstTo} onChange={(event) => setSstTo(event.target.value)} />
            </label>
            <label className="settings-field" htmlFor="sst-limit" title="Maximum hourly SST observations to render.">
              <span>{ui("Limit")}</span>
              <select id="sst-limit" className="field" value={sstLimit} onChange={(event) => setSstLimit(Number(event.target.value))}>
                <option value={250}>250</option>
                <option value={500}>500</option>
                <option value={1000}>1000</option>
                <option value={2000}>2000</option>
                <option value={5000}>5000</option>
              </select>
            </label>
            <button className="button" disabled={loading}>
              {ui("Apply")}
            </button>
          </form>

          <div className="summary-strip">
            <SummaryCell label={ui("Observations")} value={sst?.observations ?? "..."} />
            <SummaryCell label={ui("Days")} value={sst?.days ?? "..."} />
            <SummaryCell label={ui("Mean SST")} value={formatMetric(sst?.stats.mean_sst, "C")} />
            <SummaryCell label={ui("Max SST")} value={formatMetric(sst?.stats.max_sst, "C")} />
          </div>

          <section className="data-section">
            <h3 className="section-title">{ui("Point SST")}</h3>
            <SstPointChart points={sst?.points || []} />
          </section>
          <section className="data-section">
            <h3 className="section-title">{ui("Daily Regional Range")}</h3>
            <SstDailyChart points={sst?.daily || []} />
          </section>
        </section>
      ) : null}

      {view === "edna" ? <EdnaDataView /> : null}
      {view === "edna_analysis" ? <EdnaAnalysisView /> : null}

      {view === "analysis" ? (
        requestedContextRaw && (!requestedContext || !contextTarget || contextTarget.scope !== "analysis") ? (
          <UnsupportedContext contextId={requestedContextRaw} />
        ) : (
          <AnalysisWorkbench contextId={requestedContext} key={`analysis-${requestedContext || "default"}`} scope="analysis" />
        )
      ) : null}

      {view === "reliability" ? (
        requestedContextRaw && (!requestedContext || !contextTarget || contextTarget.scope !== "reliability") ? (
          <UnsupportedContext contextId={requestedContextRaw} />
        ) : (
          <AnalysisWorkbench contextId={requestedContext} key={`reliability-${requestedContext || "default"}`} scope="reliability" />
        )
      ) : null}
    </section>
  );
}

function UnsupportedContext({ contextId }: { contextId: string }) {
  return (
    <section className="data-section navigator-warning" role="alert">
      <h3 className="section-title">Unsupported evidence context</h3>
      <p>The context identifier <strong>{contextId}</strong> does not map to a published analysis or reliability artifact.</p>
    </section>
  );
}

function DataPageFallback() {
  const { ui } = useAppPreferences();
  return (
    <section>
      <header className="page-header">
        <h2>{ui("Data")}</h2>
      </header>
      <p className="empty-state">{ui("Loading data workspace.")}</p>
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

function CatalogRow({ label, value }: { label: string; value: unknown }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td>{formatCell(value)}</td>
    </tr>
  );
}

function ObservationBars({ rows }: { rows: { label: string; value: number }[] }) {
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  return (
    <div className="visual-bars">
      {rows.map((row) => {
        const pct = total ? Math.round((row.value / total) * 100) : 0;
        return (
          <div className="visual-bar-row" key={row.label}>
            <span>{row.label}</span>
            <div className="visual-track" aria-label={`${row.label}: ${pct}%`}>
              <div style={{ width: `${pct}%` }} />
            </div>
            <strong>{row.value.toLocaleString()}</strong>
            <em>{pct}%</em>
          </div>
        );
      })}
    </div>
  );
}

function DepthProfileChart({ rows, variables }: { rows: Record<string, unknown>[]; variables: string[] }) {
  const { ui } = useAppPreferences();
  if (!rows.length || !variables.length) {
    return <p className="empty-state">{ui("No profile variables selected.")}</p>;
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
  const { ui } = useAppPreferences();
  return (
    <section className="data-section">
      <h3 className="section-title">{title}</h3>
      {entries.length ? <HorizontalBars entries={entries} /> : <p className="empty-state">{ui("No taxa values for this sample.")}</p>}
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
  const { ui } = useAppPreferences();
  const valid = points.filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!valid.length) return <p className="empty-state">{ui(emptyText)}</p>;
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

function isDataView(value: string | null): value is DataView {
  if (value === "edna_analysis") return true;
  return value === "observations" || value === "ctd" || value === "taxa" || value === "edna" || value === "sst" || value === "analysis" || value === "reliability";
}
