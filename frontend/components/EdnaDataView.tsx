"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { DataTable, formatCell } from "@/components/DataTable";
import {
  downloadEdnaCsv,
  getClassificationReviews,
  getEdnaAssay,
  getEdnaCatalog,
  getEdnaDetection,
  getEdnaDetections,
  getEdnaSample,
  getEdnaSamples,
  previewClassificationReview,
  type EdnaFilters,
} from "@/lib/api";
import { buildHref } from "@/lib/citation-navigation";
import {
  classificationPreviewDeltaRows,
  classificationPreviewMethodRows,
} from "@/lib/classification-preview";
import { EDNA_METHODS, ednaHref, parseEdnaState } from "@/lib/edna-navigation";
import { exclusionReasonDisplay } from "@/lib/edna-exclusions";
import type {
  EdnaAssayDetailResponse,
  EdnaCatalogResponse,
  EdnaDetectionDetailResponse,
  EdnaPageResponse,
  EdnaSampleDetailResponse,
  ClassificationReview,
  ClassificationReviewPreview,
} from "@/types";


function methodLabel(value: unknown): string {
  if (value === "qcauto_target") return "QCauto";
  if (value === "qcauto_95pct_3nn_target") return "QCauto 95%-3NN";
  return formatCell(value);
}

function compactId(value: unknown): string {
  const text = String(value || "");
  return text.length > 18 ? `${text.slice(0, 10)}…${text.slice(-6)}` : text;
}

function eligibilityRows(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const row = item as Record<string, unknown>;
    const reasons = Array.isArray(row.exclusion_reasons)
      ? row.exclusion_reasons.map(exclusionReasonDisplay).join(", ")
      : "";
    return {
      ...row,
      status: row.analysis_eligibility,
      reason: reasons || "NA",
    };
  });
}

export function EdnaDataView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryState = searchParams.toString();
  const [catalog, setCatalog] = useState<EdnaCatalogResponse | null>(null);
  const [samples, setSamples] = useState<EdnaPageResponse | null>(null);
  const [detections, setDetections] = useState<EdnaPageResponse | null>(null);
  const [sample, setSample] = useState<EdnaSampleDetailResponse | null>(null);
  const [assay, setAssay] = useState<EdnaAssayDetailResponse | null>(null);
  const [detection, setDetection] = useState<EdnaDetectionDetailResponse | null>(null);
  const [filters, setFilters] = useState<EdnaFilters>({});
  const [appliedFilters, setAppliedFilters] = useState<EdnaFilters>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [exportNote, setExportNote] = useState("");
  const [classificationReviews, setClassificationReviews] = useState<ClassificationReview[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState("");
  const [classificationPreview, setClassificationPreview] = useState<ClassificationReviewPreview | null>(null);
  const [classificationError, setClassificationError] = useState("");
  const [classificationLoading, setClassificationLoading] = useState(false);
  const [previewMethod, setPreviewMethod] = useState("");
  const [previewRank, setPreviewRank] = useState<"genus" | "species">("genus");
  const [previewMinReads, setPreviewMinReads] = useState(1);
  const [previewTopTaxa, setPreviewTopTaxa] = useState(10);

  useEffect(() => {
    getEdnaCatalog().then(setCatalog).catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    let active = true;
    const sampleId = typeof sample?.sample.sample_id === "string" ? sample.sample.sample_id : "";
    setClassificationReviews([]);
    setSelectedReviewId("");
    setClassificationPreview(null);
    setClassificationError("");
    if (!sampleId) return () => { active = false; };
    getClassificationReviews(sampleId)
      .then((payload) => {
        if (!active) return;
        setClassificationReviews(payload.items);
        const previewable = payload.items.find((item) => ["draft", "approved", "failed"].includes(item.state));
        setSelectedReviewId((previewable || payload.items[0])?.id || "");
      })
      .catch((err: Error) => { if (active) setClassificationError(err.message); });
    return () => { active = false; };
  }, [sample]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setSamples(null);
    setDetections(null);
    setSample(null);
    setAssay(null);
    setDetection(null);
    setExportNote("");
    async function load() {
      const state = parseEdnaState(queryState);
      const next = { ...state.filters };
      const detectionDetail = state.detectionId ? await getEdnaDetection(state.detectionId) : null;
      if (detectionDetail) {
        const target = {
          sample_id: String(detectionDetail.sample.sample_id),
          assay_id: String(detectionDetail.assay.assay_id),
          assignment_method: String(detectionDetail.detection.assignment_method),
        };
        for (const key of ["sample_id", "assay_id", "assignment_method"] as const) {
          if (next[key] && next[key] !== target[key]) throw new Error("Detection does not match the selected evidence.");
          next[key] = target[key];
        }
      }
      const assayDetail = next.assay_id ? await getEdnaAssay(next.assay_id) : null;
      if (assayDetail) {
        const sampleId = String(assayDetail.sample.sample_id);
        if (next.sample_id && next.sample_id !== sampleId) throw new Error("Assay does not match the selected sample.");
        next.sample_id = sampleId;
      }
      const sampleDetail = next.sample_id ? await getEdnaSample(next.sample_id) : null;
      const summaries = assayDetail?.method_summaries || sampleDetail?.method_summaries;
      if (next.assignment_method && summaries && !summaries.some((row) => row.assignment_method === next.assignment_method)) {
        throw new Error("No active records for the selected assignment method.");
      }
      const [sampleRows, detectionRows] = await Promise.all([
        getEdnaSamples({ ...next, limit: 100, offset: state.sampleOffset }),
        getEdnaDetections({ ...next, limit: 100, offset: state.detectionOffset }),
      ]);
      if (!cancelled) {
        setFilters(next);
        setAppliedFilters(next);
        setSamples(sampleRows);
        setDetections(detectionRows);
        setSample(sampleDetail);
        setAssay(assayDetail);
        setDetection(detectionDetail);
      }
    }
    void load()
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [queryState]);

  function setFilter(name: keyof EdnaFilters, value: string) {
    setFilters((current) => ({ ...current, [name]: value || undefined }));
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    router.push(ednaHref(filters), { scroll: false });
  }

  function selectSample(sampleId: string) {
    router.push(ednaHref({ ...appliedFilters, sample_id: sampleId || undefined, assay_id: undefined }), { scroll: false });
  }

  async function exportCsv() {
    try {
      const result = await downloadEdnaCsv(appliedFilters);
      const href = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(href);
      setExportNote(result.truncated ? "Export limited to 25,000 rows. Narrow the filters for a complete export." : "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "eDNA export failed");
    }
  }

  const selectedReview = useMemo(
    () => classificationReviews.find((item) => item.id === selectedReviewId),
    [classificationReviews, selectedReviewId],
  );

  async function runClassificationPreview() {
    if (!selectedReview) return;
    setClassificationLoading(true);
    setClassificationError("");
    setClassificationPreview(null);
    try {
      setClassificationPreview(await previewClassificationReview(selectedReview.id, {
        expected_version: selectedReview.version,
        assignment_methods: previewMethod
          ? [previewMethod]
          : ["qcauto_target", "qcauto_95pct_3nn_target"],
        rank: previewRank,
        min_read_count: previewMinReads,
        top_taxa_limit: previewTopTaxa,
      }));
    } catch (err) {
      setClassificationError(err instanceof Error ? err.message : "Classification preview failed");
    } finally {
      setClassificationLoading(false);
    }
  }

  const sampleRows = (samples?.rows || []).map((row) => {
    const exclusionReasons = Array.isArray(row.exclusion_reasons)
      ? row.exclusion_reasons
      : [];
    return {
      ...row,
      sample: compactId(row.sample_id),
      provider_sample_id: row.provider_sample_id,
      project: row.provider_project_id,
      run: row.provider_run_id,
      sample_kind: row.sample_kind,
      control_status: row.is_control === null ? "Unknown" : row.is_control ? "Control" : "Non-control",
      analysis_eligibility: row.analysis_eligibility,
      exclusion_reason: exclusionReasons.map(exclusionReasonDisplay).join(", ") || "NA",
      collection_date_utc: row.collection_date_utc,
      detection_count: row.detection_count,
      "QCauto records": row.qcauto_detection_count,
      "QCauto 95%-3NN records": row.three_nn_detection_count,
    };
  });
  const detectionRows = (detections?.rows || []).map((row) => ({
    ...row,
    detection: compactId(row.detection_id),
    method: methodLabel(row.assignment_method),
    assigned_taxon_name: row.assigned_taxon_name,
    assigned_taxon_rank: row.assigned_taxon_rank,
    read_count: row.read_count,
    "Source-supplied copies/mL": row.copies_per_ml,
    eligibility: row.analysis_eligibility,
    exclusion_reason: Array.isArray(row.exclusion_reasons)
      ? row.exclusion_reasons.map(exclusionReasonDisplay).join(", ") || "NA"
      : "NA",
    source_row_number: row.source_row_number,
  }));

  function page(kind: "sample" | "detection", offset: number) {
    router.push(ednaHref(appliedFilters, {
      sampleOffset: kind === "sample" ? offset : samples?.offset,
      detectionOffset: kind === "detection" ? offset : detections?.offset,
      detectionId: searchParams.get("detection_id") || undefined,
    }), { scroll: false });
  }

  return (
    <section className="data-view">
      <form className="data-controls" onSubmit={apply}>
        <label className="settings-field" htmlFor="edna-provider">
          <span>Provider</span>
          <select id="edna-provider" className="field" value={filters.provider || ""} onChange={(event) => setFilter("provider", event.target.value)}>
            <option value="">All</option>
            {(catalog?.providers || []).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-project">
          <span>Project</span>
          <select id="edna-project" className="field" value={filters.provider_project_id || ""} onChange={(event) => setFilter("provider_project_id", event.target.value)}>
            <option value="">All</option>
            {(catalog?.projects || []).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-run">
          <span>Run</span>
          <select id="edna-run" className="field" value={filters.provider_run_id || ""} onChange={(event) => setFilter("provider_run_id", event.target.value)}>
            <option value="">All</option>
            {(catalog?.runs || []).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-method">
          <span>Assignment</span>
          <select id="edna-method" className="field" value={filters.assignment_method || ""} onChange={(event) => setFilter("assignment_method", event.target.value)}>
            <option value="">Both methods</option>
            {EDNA_METHODS.map((value) => <option key={value} value={value}>{methodLabel(value)}</option>)}
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-control">
          <span>Control status</span>
          <select id="edna-control" className="field" value={filters.is_control === undefined ? "" : String(filters.is_control)} onChange={(event) => setFilters((current) => ({ ...current, is_control: event.target.value === "" ? undefined : event.target.value === "true" }))}>
            <option value="">All (including unknown)</option>
            <option value="true">Control</option>
            <option value="false">Non-control</option>
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-kind">
          <span>Sample kind</span>
          <select id="edna-kind" className="field" value={filters.sample_kind || ""} onChange={(event) => setFilter("sample_kind", event.target.value)}>
            <option value="">All</option>
            {(catalog?.sample_kinds || []).map((value) => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className="settings-field" htmlFor="edna-taxon">
          <span>Taxon</span>
          <input id="edna-taxon" className="field" maxLength={200} value={filters.taxon || ""} onChange={(event) => setFilter("taxon", event.target.value)} />
        </label>
        <label className="settings-field" htmlFor="edna-from">
          <span>From</span>
          <input id="edna-from" className="field" type="date" value={filters.time_from || ""} onChange={(event) => setFilter("time_from", event.target.value)} />
        </label>
        <label className="settings-field" htmlFor="edna-to">
          <span>To</span>
          <input id="edna-to" className="field" type="date" value={filters.time_to || ""} onChange={(event) => setFilter("time_to", event.target.value)} />
        </label>
        {(["lat_min", "lat_max", "lon_min", "lon_max"] as const).map((key) => (
          <label key={key} className="settings-field" htmlFor={`edna-${key}`}>
            <span>{{ lat_min: "Latitude min", lat_max: "Latitude max", lon_min: "Longitude min", lon_max: "Longitude max" }[key]}</span>
            <input id={`edna-${key}`} className="field" type="number" step="any" min={key.startsWith("lat") ? -90 : -180} max={key.startsWith("lat") ? 90 : 180} value={filters[key] ?? ""} onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value === "" ? undefined : Number(event.target.value) }))} />
          </label>
        ))}
        <button className="button" disabled={loading}>Apply</button>
        <button className="button secondary-button" onClick={() => router.push("/data?view=edna", { scroll: false })} type="button">Clear</button>
        <button className="button secondary-button" disabled={loading || Boolean(error) || !detections} onClick={() => void exportCsv()} type="button">
          <Download size={15} aria-hidden="true" /> Export CSV
        </button>
      </form>

      {error ? <p className="error-text">{error}</p> : null}
      {exportNote ? <p role="status">{exportNote}</p> : null}

      <div className="summary-strip">
        <Metric label="Samples" value={catalog?.samples} />
        <Metric label="Assays" value={catalog?.assays} />
        <Metric label="Detections" value={catalog?.detections} />
        <Metric label="Controls" value={catalog?.controls} />
      </div>

      <section className="data-section">
        <div className="section-toolbar">
          <h3 className="section-title">Samples ({formatCell(samples?.total)})</h3>
          <select aria-label="Selected eDNA sample" className="field" value={filters.sample_id || ""} onChange={(event) => selectSample(event.target.value)}>
            <option value="">Select sample</option>
            {(samples?.rows || []).map((row) => (
              <option key={String(row.sample_id)} value={String(row.sample_id)}>{String(row.provider_sample_id || row.sample_id)}</option>
            ))}
          </select>
        </div>
        <DataTable columns={["sample", "provider_sample_id", "project", "run", "sample_kind", "control_status", "analysis_eligibility", "exclusion_reason", "collection_date_utc", "QCauto records", "QCauto 95%-3NN records"]} rows={sampleRows} rowKeyColumn="sample_id" selectedKey={appliedFilters.sample_id} onRowSelect={(row) => selectSample(String(row.sample_id))} />
        <Pagination page={samples} loading={loading} onPage={(offset) => page("sample", offset)} />
      </section>

      {sample ? (
        <section className="data-section">
          <h3 className="section-title">Sample</h3>
          <DataTable columns={["provider_sample_id", "provider_project_id", "provider_run_id", "sample_kind", "is_control", "collection_date_utc", "lat", "lon"]} rows={[sample.sample]} />
          <h3 className="section-title">Environmental analysis eligibility</h3>
          <DataTable
            columns={["status", "reason", "sample_kind", "is_control", "active_assays"]}
            rows={[{
              status: sample.sample.analysis_eligibility,
              reason: Array.isArray(sample.sample.exclusion_reasons)
                ? sample.sample.exclusion_reasons.map(exclusionReasonDisplay).join(", ") || "NA"
                : "NA",
              sample_kind: sample.sample.sample_kind,
              is_control: sample.sample.is_control,
              active_assays: sample.assays.length,
            }]}
          />
          <h3 className="section-title">Methods</h3>
          <DataTable columns={["assignment_method", "detection_count", "read_count_sum", "copies_per_ml_record_count"]} rows={sample.method_summaries} />
          <h3 className="section-title">Eligibility by assay and method</h3>
          <DataTable
            columns={["assay_id", "assignment_method", "status", "reason"]}
            rows={eligibilityRows(sample.sample.method_eligibility)}
          />
          <h3 className="section-title">Assays</h3>
          <DataTable columns={["assay_id", "target_gene", "primer_set", "sequencing_method"]} rows={sample.assays} rowKeyColumn="assay_id" selectedKey={appliedFilters.assay_id} onRowSelect={(row) => router.push(ednaHref({ ...appliedFilters, assay_id: String(row.assay_id) }), { scroll: false })} />
        </section>
      ) : null}

      {sample ? (
        <section className="data-section">
          <h3 className="section-title">Classification review</h3>
          {classificationError ? <p className="error-text" role="alert">{classificationError}</p> : null}
          {!classificationReviews.length && !classificationError ? <p>No reviews.</p> : null}
          {classificationReviews.length ? <>
            <div className="filter-grid">
              <label className="control-label">Review
                <select className="field" value={selectedReviewId} onChange={(event) => { setSelectedReviewId(event.target.value); setClassificationPreview(null); }}>
                  {classificationReviews.map((item) => <option key={item.id} value={item.id}>{item.state} · {item.sample_kind} · v{item.version}</option>)}
                </select>
              </label>
              <label className="control-label">Assignment method
                <select className="field" value={previewMethod} onChange={(event) => { setPreviewMethod(event.target.value); setClassificationPreview(null); }}>
                  <option value="">Both</option>
                  <option value="qcauto_target">QCauto</option>
                  <option value="qcauto_95pct_3nn_target">QCauto 95%-3NN</option>
                </select>
              </label>
              <label className="control-label">Rank
                <select className="field" value={previewRank} onChange={(event) => { setPreviewRank(event.target.value as "genus" | "species"); setClassificationPreview(null); }}>
                  <option value="genus">Genus</option>
                  <option value="species">Species</option>
                </select>
              </label>
              <label className="control-label">Minimum reads
                <input className="field" type="number" min="1" max="1000000000" value={previewMinReads} onChange={(event) => { setPreviewMinReads(Math.min(1000000000, Math.max(1, Number(event.target.value) || 1))); setClassificationPreview(null); }} />
              </label>
              <label className="control-label">Top taxa
                <input className="field" type="number" min="1" max="25" value={previewTopTaxa} onChange={(event) => { setPreviewTopTaxa(Math.min(25, Math.max(1, Number(event.target.value) || 1))); setClassificationPreview(null); }} />
              </label>
            </div>
            <button
              className="button secondary-button"
              type="button"
              disabled={classificationLoading || !selectedReview || !["draft", "approved", "failed"].includes(selectedReview.state)}
              onClick={() => void runClassificationPreview()}
            >
              {classificationLoading ? "Calculating…" : "Preview effect"}
            </button>
            <DataTable
              columns={["state", "sample_kind", "version", "rationale", "scientific_decided_at"]}
              rows={selectedReview ? [selectedReview] : []}
            />
          </> : null}
          {classificationPreview ? <>
            <div className="summary-strip">
              <Metric label="Current" value={classificationPreview.baseline.eligibility} />
              <Metric label="Proposed" value={classificationPreview.proposed.eligibility} />
              <Metric label="Current kind" value={classificationPreview.baseline.sample_kind} />
              <Metric label="Proposed kind" value={classificationPreview.proposed.sample_kind} />
            </div>
            <DataTable
              columns={["scenario", "status", "reason"]}
              rows={[
                {
                  scenario: "Current",
                  status: classificationPreview.baseline.eligibility,
                  reason: classificationPreview.baseline.exclusion_reasons.map(exclusionReasonDisplay).join(", ") || "NA",
                },
                {
                  scenario: "Proposed",
                  status: classificationPreview.proposed.eligibility,
                  reason: classificationPreview.proposed.exclusion_reasons.map(exclusionReasonDisplay).join(", ") || "NA",
                },
              ]}
            />
            <h3 className="section-title">Method results</h3>
            <DataTable
              columns={["scenario", "assay_id", "assignment_method", "status", "reason", "source_detection_count", "retained_detection_count", "excluded_detection_count", "source_reads", "retained_reads", "excluded_reads", "richness", "shannon", "simpson_1d", "evenness", "metric_status", "top_taxa"]}
              rows={classificationPreviewMethodRows(classificationPreview)}
            />
            <h3 className="section-title">Changed table counts</h3>
            <DataTable
              columns={["table", "current", "proposed", "delta"]}
              rows={classificationPreviewDeltaRows(classificationPreview)}
            />
            <details>
              <summary>Preview record</summary>
              <DataTable columns={["preview_sha256", "canonical_input_sha256", "algorithm_version"]} rows={[classificationPreview]} />
              <ul>{classificationPreview.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>
          </> : null}
        </section>
      ) : null}

      {assay ? (
        <section className="data-section">
          <h3 className="section-title">Assay</h3>
          <DataTable columns={["assay_id", "target_gene", "primer_set", "sequencing_method", "library_layout", "instrument_model"]} rows={[assay.assay]} />
          <h3 className="section-title">Eligibility by method</h3>
          <DataTable
            columns={["assignment_method", "status", "reason"]}
            rows={eligibilityRows(assay.assay.method_eligibility)}
          />
          <h3 className="section-title">Internal standards</h3>
          <DataTable columns={["standard_name", "sequence_sha256", "read_count", "source_row_number"]} rows={assay.internal_standards} />
          <div className="section-toolbar">
            {assay.method_summaries.map((row) => (
              <a key={String(row.assignment_method)} className="button secondary-button" href={buildHref("/provenance", { view: "trace", doc_id: `edna_${assay.assay.assay_id}_${row.assignment_method}` })}>
                Provenance · {methodLabel(row.assignment_method)}
              </a>
            ))}
          </div>
        </section>
      ) : null}

      {detection ? (
        <section className="data-section">
          <h3 className="section-title">Detection</h3>
          <DataTable columns={["detection_id", "assignment_method", "analysis_eligibility", "exclusion_reasons", "assigned_taxon_name", "assigned_taxon_rank", "read_count", "copies_per_ml", "sequence_sha256", "source_row_number"]} rows={[detection.detection]} />
        </section>
      ) : null}

      <section className="data-section">
        <h3 className="section-title">Detections ({formatCell(detections?.total)})</h3>
        <DataTable columns={["detection", "method", "eligibility", "exclusion_reason", "assigned_taxon_name", "assigned_taxon_rank", "read_count", "Source-supplied copies/mL", "source_row_number"]} rows={detectionRows} rowKeyColumn="detection_id" selectedKey={searchParams.get("detection_id") || undefined} onRowSelect={(row) => router.push(ednaHref({ ...appliedFilters, sample_id: String(row.sample_id), assay_id: String(row.assay_id), assignment_method: String(row.assignment_method) }, { detectionId: String(row.detection_id) }), { scroll: false })} />
        <Pagination page={detections} loading={loading} onPage={(offset) => page("detection", offset)} />
      </section>
      <SourceRecords provenance={detection?.provenance || assay?.provenance || sample?.provenance} />
    </section>
  );
}

function Metric({ label, value }: { label: string; value?: number | string }) {
  return <div><span>{label}</span><strong>{value === undefined ? "…" : typeof value === "number" ? value.toLocaleString() : value}</strong></div>;
}

function Pagination({ page, loading, onPage }: { page: EdnaPageResponse | null; loading: boolean; onPage: (offset: number) => void }) {
  if (!page || page.total <= page.limit) return null;
  return <div className="section-toolbar">
    <button className="button secondary-button" disabled={loading || page.offset === 0} onClick={() => onPage(Math.max(0, page.offset - page.limit))}>Previous</button>
    <span>{page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} / {page.total}</span>
    <button className="button secondary-button" disabled={loading || page.offset + page.limit >= page.total} onClick={() => onPage(page.offset + page.limit)}>Next</button>
  </div>;
}

function SourceRecords({ provenance }: { provenance?: Record<string, unknown> }) {
  const rows = Array.isArray(provenance?.records) ? provenance.records as Record<string, unknown>[] : [];
  if (!rows.length) return null;
  const urls = Array.from(new Set(rows.map((row) => String(row.source_url || "")))).filter((value) => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" && url.hostname === "db.anemone.bio" && !url.username && !url.password;
    } catch { return false; }
  });
  return <section className="data-section">
    <h3 className="section-title">Source records</h3>
    <DataTable columns={["entity_type", "entity_id", "snapshot_id", "source_file_id", "sha256", "source_row_locator"]} rows={rows} rowKeyColumn="entity_id" />
    <div className="section-toolbar">{urls.map((url, index) => <a key={url} className="button secondary-button" href={url} target="_blank" rel="noreferrer">Source {index + 1}</a>)}</div>
  </section>;
}
