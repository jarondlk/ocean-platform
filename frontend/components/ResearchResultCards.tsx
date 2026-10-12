"use client";

import { useState } from "react";
import { DataTable, formatCell } from "@/components/DataTable";
import type { ContextDocument } from "@/types";
import { ResearchAreaPlot, ResearchSeriesPlot } from "@/components/ResearchFrequencyPlot";

function ResultCard({ document }: {document: ContextDocument}) {
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [plotBin, setPlotBin] = useState("");
  const [taxon, setTaxon] = useState("");
  const [period, setPeriod] = useState("");
  const ja = document.display_language === "ja";
  const allRows = document.result_rows || [];
  const rows = allRows.filter(row => (!taxon || row.taxon_key === taxon) && (!period || row.period_kind === period));
  const taxa = [...new Set(allRows.map(row => row.taxon_key).filter((value): value is string => typeof value === "string"))];
  const periods = [...new Set(allRows.map(row => row.period_kind).filter((value): value is string => typeof value === "string"))];
  const bins = [...new Set(rows.map(row => row.bin).filter((value): value is string => typeof value === "string"))];
  const plotRows = bins.length ? rows.filter(row => row.bin === plotBin) : rows;
  const exportMetadata = {analysis_id: document.analysis_id, table: document.table, recipe: document.analysis_recipe, total_rows: document.total_rows, rows_truncated: document.rows_truncated, caption: document.title};
  const offset = page * 20;
  const selectResult = (id: string) => {
    const index = rows.findIndex(row => row.result_id === id);
    if (index >= 0) { setSelected(rows[index]); setPage(Math.floor(index / 20)); }
  };
  const columns = ["species", "position", "area_id", "season", "year", "month", "period", "taxon_key", "bin", "low_max", "high_min", "low_max_celsius", "high_min_celsius", "baseline_from", "baseline_to", "supported_days", "detected", "eligible", "frequency", "read_count", "all_edna_eligible", "sst_unavailable", "low_detected", "low_eligible", "high_detected", "high_eligible", "supported", "supported_strata", "representative", "low_support", "partial_period", "sampling_status", "sst_matched", "sample_time_sst_mean_celsius", "sst_celsius", "valid_days", "missing_days", "difference_percentage_points", "standardized_difference_percentage_points", "mean_absolute_change_percentage_points"].filter(key => allRows.some(row => key in row));
  const labels: Record<string,string> = ja ? {species:"学名（種）", position:"順位", area_id:"区域", period:"期間", taxon_key:"学名", detected:"検出単位数", eligible:"適格単位数（分母）", frequency:"検出頻度", sampling_status:"採水・検出状態", low_support:"少数サンプル", partial_period:"部分期間", read_count:"シーケンスリード数"} : {eligible:"Eligible units (denominator)", detected:"Detected units", frequency:"Detection frequency"};
  const status: Record<string,string> = ja ? {unsampled:"採水なし・頻度算出不可", sampled_not_detected:"記録上の非検出", sampled_negative:"記録上の非検出", sampled_detected:"検出あり", unavailable:"利用不可"} : {};
  Object.assign(labels, ja ? {supported_strata:"必要なサンプル数を満たす区域・季節群の数", difference_percentage_points:"全体の高SST−低SST差（百分率ポイント）", standardized_difference_percentage_points:"区域・季節群の差の等重み平均（百分率ポイント）"} : {supported_strata:"Supported area-season strata", difference_percentage_points:"Aggregate high − low (percentage points)", standardized_difference_percentage_points:"Mean supported-stratum difference (percentage points)"});
  return <section className="data-section" aria-label={document.title}>
    <h4>{document.title}</h4>
    <p>{document.total_rows ?? allRows.length} {ja ? "公表済み行。" : "published rows."} {["provisional_demo", "regional_frequency"].includes(document.analysis_type || "") ? (ja ? "分母は単一出現記録の代理単位であり、独立した採水サンプルとは確定していません。リード数は個体数ではありません。" : "Regional analysis. Frequency uses singleton occurrence proxies; read counts are sequencing signals, not fish abundance.") : (ja ? "分母は適格な物理サンプル数です。" : "Frequency is a proportion of eligible physical samples.")} {ja ? "和名が未検証の場合は学名のみを表示します。" : "Scientific names are retained; unverified common names are not supplied."}</p>
    <p>{ja ? "検出頻度 = 検出単位数 / 適格単位数。分母0は算出不可。記録上の非検出は生物学的な不在を意味しません。" : "Detection frequency = detected / eligible units. A zero denominator has no rate. Recorded non-detection does not establish biological absence."}</p>
    {document.table === "temperature_contrasts" ? <p>{ja ? "全体の高SST−低SST差と、必要なサンプル数を満たす区域・季節群の差の等重み平均は、符号が逆になる場合があります。代表系列は後者で選びます。群の数を確認し、一般的な水温への応答や因果関係を推定しません。" : "The aggregate high-minus-low difference and the mean supported-stratum difference can have opposite signs. The latter selects the representative series. Check the stratum count; these descriptive contrasts do not establish a general temperature response or causation."}</p> : null}
    {document.analysis_recipe ? <p>{ja ? "分類手法" : "Assignment method"}: {String(document.analysis_recipe.assignment_method || "unavailable")} · {ja ? "プロトコルID" : "Protocol ID"}: {[...new Set(allRows.map(row => row.protocol_id).filter(Boolean))].join(", ")}</p> : null}
    {document.protocol_definition ? <details><summary>{ja ? "機器・プライマー・PCR条件" : "Instrument, primer and PCR definition"}</summary><pre className="json-view">{JSON.stringify(document.protocol_definition, null, 2)}</pre></details> : null}
    {taxa.length > 1 ? <label>{ja ? "分類群" : "Taxon"}<select value={taxon} onChange={event => {setTaxon(event.target.value);setPage(0);setSelected(null);}}><option value="">{ja ? "すべて" : "All taxa"}</option>{taxa.map(key => <option key={key} value={key}>{document.plot_taxa?.find(t => t.taxon_key === key)?.species || key}</option>)}</select></label> : null}
    {periods.length > 1 ? <label>{ja ? "期間区分" : "Period"}<select value={period} onChange={event => {setPeriod(event.target.value);setPage(0);setSelected(null);}}><option value="">{ja ? "すべて" : "All periods"}</option>{periods.map(key => <option key={key} value={key}>{ja ? (({year:"年別",season:"季節別",month:"月別"} as Record<string,string>)[key] || key) : key}</option>)}</select></label> : null}
    {document.rows_truncated ? <p role="status">The chat snapshot contains the first {rows.length} rows. The complete analysis is available in Data to authorized researchers.</p> : null}
    {document.plot_areas?.length && bins.length ? <label className="control-label">Map temperature range<select className="field" value={plotBin} onChange={event => setPlotBin(event.target.value)}><option value="">Choose a published range</option>{bins.map(bin => <option key={bin} value={bin}>{bin}</option>)}</select></label> : null}
    {document.plot_areas?.length ? <ResearchAreaPlot rows={plotRows} areas={document.plot_areas} onSelect={selectResult} exportMetadata={exportMetadata} /> : null}
    {["series", "temperature_series", "follow_through"].includes(document.table || "") ? <ResearchSeriesPlot rows={rows} taxa={document.plot_taxa || []} onSelect={selectResult} exportMetadata={exportMetadata} language={ja ? "ja" : "en"} /> : null}
    <DataTable columns={columns} columnLabels={labels} rows={rows.slice(offset, offset+20)} rowKeyColumn="result_id" selectedKey={String(selected?.result_id || "")} onRowSelect={setSelected} renderCell={(value,column) => column === "taxon_key" ? document.plot_taxa?.find(taxon => taxon.taxon_key === value)?.species || formatCell(value) : column === "frequency" && typeof value === "number" ? `${(100*value).toFixed(2)}%` : value == null ? (ja ? "算出不可・利用不可" : "unavailable") : column === "sampling_status" ? status[String(value)] || formatCell(value) : formatCell(value)} />
    <div className="button-row"><button className="button secondary-button" type="button" disabled={page === 0} onClick={() => setPage(value => value-1)}>{ja ? "前へ" : "Previous"}</button><button className="button secondary-button" type="button" disabled={offset+20 >= rows.length} onClick={() => setPage(value => value+1)}>{ja ? "次へ" : "Next"}</button></div>
    {selected ? <details open><summary>{ja ? "公表済み結果の項目" : "Published result fields"}</summary><pre className="json-view">{JSON.stringify(selected, null, 2)}</pre></details> : null}
  </section>;
}

export function ResearchResultCards({ documents }: {documents: ContextDocument[]}) {
  return <>{documents.filter(document => ["detection_frequency", "provisional_demo", "regional_frequency"].includes(document.analysis_type || "") && document.result_rows?.length).map(document => <ResultCard key={document.doc_id} document={document} />)}</>;
}
