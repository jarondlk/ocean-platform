"use client";

import { useState } from "react";
import { DataTable, formatCell } from "@/components/DataTable";
import type { ContextDocument } from "@/types";
import { ResearchAreaPlot, ResearchSeriesPlot } from "@/components/ResearchFrequencyPlot";

function ResultCard({ document }: {document: ContextDocument}) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [plotBin, setPlotBin] = useState("");
  const rows = document.result_rows || [];
  const bins = [...new Set(rows.map(row => row.bin).filter((value): value is string => typeof value === "string"))];
  const plotRows = bins.length ? rows.filter(row => row.bin === plotBin) : rows;
  const exportMetadata = {analysis_id: document.analysis_id, table: document.table, recipe: document.analysis_recipe, total_rows: document.total_rows, rows_truncated: document.rows_truncated, caption: document.title};
  const offset = page * 20;
  const selectResult = (id: string) => {
    const index = rows.findIndex(row => row.result_id === id);
    if (index >= 0) { setSelected(rows[index]); setPage(Math.floor(index / 20)); }
  };
  const columns = ["species", "position", "area_id", "season", "year", "month", "period", "taxon_key", "bin", "low_max", "high_min", "low_max_celsius", "high_min_celsius", "baseline_from", "baseline_to", "supported_days", "detected", "eligible", "frequency", "read_count", "all_edna_eligible", "sst_unavailable", "low_detected", "low_eligible", "high_detected", "high_eligible", "supported", "representative", "low_support", "partial_period", "sampling_status", "sst_matched", "sample_time_sst_mean_celsius", "sst_celsius", "valid_days", "missing_days", "difference_percentage_points", "standardized_difference_percentage_points", "mean_absolute_change_percentage_points"].filter(key => rows.some(row => key in row));
  return <section className="data-section" aria-label={document.title}>
    <h4>{document.title}</h4>
    <p>{document.total_rows ?? rows.length} published rows. {["provisional_demo", "regional_frequency"].includes(document.analysis_type || "") ? "Regional analysis. Frequency uses singleton occurrence proxies; read counts are sequencing signals, not fish abundance." : "Frequency is a proportion of eligible physical samples."} Select a row to inspect its published fields and result ID.</p>
    {document.rows_truncated ? <p role="status">The chat snapshot contains the first {rows.length} rows. The complete analysis is available in Data to authorized researchers.</p> : null}
    {document.plot_areas?.length && bins.length ? <label className="control-label">Map temperature range<select className="field" value={plotBin} onChange={event => setPlotBin(event.target.value)}><option value="">Choose a published range</option>{bins.map(bin => <option key={bin} value={bin}>{bin}</option>)}</select></label> : null}
    {document.plot_areas?.length ? <ResearchAreaPlot rows={plotRows} areas={document.plot_areas} onSelect={selectResult} exportMetadata={exportMetadata} /> : null}
    {["series", "temperature_series", "follow_through"].includes(document.table || "") ? <ResearchSeriesPlot rows={rows} taxa={document.plot_taxa || []} onSelect={selectResult} exportMetadata={exportMetadata} /> : null}
    <DataTable columns={columns} rows={rows.slice(offset, offset+20)} rowKeyColumn="result_id" selectedKey={String(selected?.result_id || "")} onRowSelect={setSelected} renderCell={(value,column) => column === "taxon_key" ? document.plot_taxa?.find(taxon => taxon.taxon_key === value)?.species || formatCell(value) : formatCell(value)} />
    <div className="button-row"><button className="button secondary-button" type="button" disabled={page === 0} onClick={() => setPage(value => value-1)}>Previous</button><button className="button secondary-button" type="button" disabled={offset+20 >= rows.length} onClick={() => setPage(value => value+1)}>Next</button></div>
    {selected ? <details open><summary>Published result fields</summary><pre className="json-view">{JSON.stringify(selected, null, 2)}</pre></details> : null}
  </section>;
}

export function ResearchResultCards({ documents }: {documents: ContextDocument[]}) {
  return <>{documents.filter(document => ["detection_frequency", "provisional_demo", "regional_frequency"].includes(document.analysis_type || "") && document.result_rows?.length).map(document => <ResultCard key={document.doc_id} document={document} />)}</>;
}
