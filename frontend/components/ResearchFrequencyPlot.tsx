"use client";

import { useId, useRef } from "react";

export type ResearchArea = {area_id: string; label: string; west: number; east: number; south: number; north: number; coordinate_uncertainty_km: number};
type Row = Record<string, unknown>;
type ExportMetadata = Record<string, unknown>;

function exportFigure(svg: SVGSVGElement | null, caption: string, rows: Row[], metadata?: ExportMetadata) {
  if (!svg) return;
  const copy = svg.cloneNode(true) as SVGSVGElement;
  copy.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copy.setAttribute("width", copy.viewBox.baseVal.width.toString());
  copy.setAttribute("height", copy.viewBox.baseVal.height.toString());
  const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
  title.textContent = caption;
  const description = document.createElementNS("http://www.w3.org/2000/svg", "desc");
  description.textContent = "Published loaded rows only. Detection frequency is not abundance or occupancy. Missing values remain gaps. See embedded metadata for recipe and exact results.";
  const record = document.createElementNS("http://www.w3.org/2000/svg", "metadata");
  record.textContent = JSON.stringify({schema_version:1, ...metadata, caption, export_scope:"plotted_rows_only", plotted_row_count:rows.length, contains_complete_table:metadata?.total_rows === rows.length && metadata?.rows_truncated !== true, plotted_rows:rows, result_ids:rows.map(row => row.result_id)});
  copy.prepend(title, description, record);
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(copy)], {type:"image/svg+xml;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url; link.download = "ocean-published-research-figure.svg"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ResearchAreaPlot({ rows, areas, onSelect, exportMetadata }: {rows: Row[]; areas: ResearchArea[]; exportMetadata?: ExportMetadata; onSelect: (id: string) => void}) {
  const patternId = useId();
  const svg = useRef<SVGSVGElement>(null);
  if (!areas.length || !rows.length) return null;
  const seen = new Set<string>();
  if (rows.some(row => { const id = String(row.area_id); if (seen.has(id)) return true; seen.add(id); return false; })) return <p role="status">Choose one protocol and temperature bin to display one result per area.</p>;
  const west = Math.min(...areas.map(a => a.west)), east = Math.max(...areas.map(a => a.east));
  const south = Math.min(...areas.map(a => a.south)), north = Math.max(...areas.map(a => a.north));
  const x = (lon: number) => 60+(lon-west)/(east-west)*640, y = (lat: number) => 250-(lat-south)/(north-south)*200;
  const temperatures = rows.map(r => r.sst_celsius).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const min = Math.min(...temperatures), max = Math.max(...temperatures);
  return <figure><figcaption>Reviewed cell footprints · longitude/latitude. This map shows the loaded table page; unfilled cells may be unsampled, unsupported or not loaded.</figcaption>
    <svg ref={svg} viewBox="0 0 760 300" style={{width:"100%",height:"auto"}} role="group" aria-label="Reviewed area map">
      <defs><pattern id={patternId} patternUnits="userSpaceOnUse" width="8" height="8"><path d="M0,8 L8,0" stroke="#cbd5e1" /></pattern></defs>
      {areas.map(area => {
        const row = rows.find(r => r.area_id === area.area_id);
        const value = typeof row?.frequency === "number" ? row.frequency : typeof row?.sst_celsius === "number" ? row.sst_celsius : null;
        const opacity = value === null ? 1 : typeof row?.frequency === "number" ? .2+.8*value : .25+.75*(max === min ? .5 : (value-min)/(max-min));
        const status = row ? String(row.sampling_status || row.status || "unavailable") : "not loaded";
        const label = `${area.label}: ${status}; detected ${row?.detected ?? "unavailable"}, eligible ${row?.eligible ?? "unavailable"}, value ${value ?? "unavailable"}; coordinate uncertainty ${area.coordinate_uncertainty_km} km`;
        return <g key={area.area_id}><rect x={x(area.west)} y={y(area.north)} width={x(area.east)-x(area.west)} height={y(area.south)-y(area.north)} fill={value === null ? `url(#${patternId})` : typeof row?.frequency === "number" ? "#2563eb" : "#0f766e"} fillOpacity={opacity} stroke={row?.low_support ? "#b45309" : "#64748b"} strokeDasharray={row ? undefined : "3 3"} tabIndex={row ? 0 : undefined} role={row ? "button" : undefined} aria-label={label} onClick={() => row && onSelect(String(row.result_id))} onKeyDown={event => { if (row && ["Enter", " "].includes(event.key)) { event.preventDefault(); onSelect(String(row.result_id)); } }}><title>{label}</title></rect></g>;
      })}
      <text x="60" y="280">{west.toFixed(3)}°E</text><text x="640" y="280">{east.toFixed(3)}°E</text>
      <text x="4" y="55">{north.toFixed(3)}°N</text><text x="4" y="250">{south.toFixed(3)}°N</text>
    </svg>
    <p>Blue intensity shows detection frequency (0–1); teal shows SST (°C). Hatching has no value. Orange outlines flag low sample support. Cells represent reviewed footprints rather than exact sampling locations.</p>
    <button className="button secondary-button" type="button" onClick={() => exportFigure(svg.current, "Reviewed area footprints · loaded published rows; blue detection frequency (0–1), teal SST (°C), hatching unavailable, orange low support", rows, {...exportMetadata, reviewed_areas:areas})}>Export map SVG</button>
  </figure>;
}

function Series({ rows, field, label, onSelect, exportMetadata }: {rows: Row[]; field: string; label: string; exportMetadata?: ExportMetadata; onSelect: (id: string) => void}) {
  const svg = useRef<SVGSVGElement>(null);
  const values = rows.map(r => r[field]).filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!values.length) return <p>{label}: no observed values in this page.</p>;
  const min = field === "frequency" ? 0 : Math.min(...values)-1, max = field === "frequency" ? 1 : Math.max(...values)+1;
  const x = (index: number) => 50+index/Math.max(1,rows.length-1)*640, y = (value: number) => 175-(value-min)/(max-min)*140;
  const segments: string[][] = [[]];
  rows.forEach((row,index) => { const value = row[field]; if (typeof value !== "number" || !Number.isFinite(value)) { segments.push([]); } else { segments[segments.length-1].push(`${x(index)},${y(value)}`); } });
  return <div><svg ref={svg} viewBox="0 0 750 220" style={{width:"100%",height:"auto"}} role="group" aria-label={label}>
    <path d="M50,30 V175 H690" fill="none" stroke="#94a3b8" />
    <text x="3" y="38">{max.toFixed(1)}</text><text x="3" y="175">{min.toFixed(1)}</text>
    {segments.map((points,index) => points.length > 1 ? <polyline key={index} points={points.join(" ")} fill="none" stroke={field === "frequency" ? "#2563eb" : "#0f766e"} strokeWidth="2" /> : null)}
    {rows.map((row,index) => typeof row[field] === "number" && Number.isFinite(row[field]) ? <circle key={String(row.result_id)} cx={x(index)} cy={y(row[field] as number)} r="4" fill={field === "frequency" ? "#2563eb" : "#0f766e"} stroke={row.low_support ? "#b45309" : undefined} strokeWidth={row.low_support ? 2 : undefined} tabIndex={0} role="button" aria-label={`${row.period || row.year}: ${label} ${row[field]}; detected ${row.detected}, eligible ${row.eligible}, SST matched ${row.sst_matched ?? "unavailable"}; low support ${row.low_support ?? "unavailable"}; partial period ${row.partial_period ?? "unavailable"}`} onClick={() => onSelect(String(row.result_id))} onKeyDown={event => { if (["Enter"," "].includes(event.key)) { event.preventDefault(); onSelect(String(row.result_id)); } }}><title>{String(row.period || row.year)} · {label} {String(row[field])} · {String(row.detected)}/{String(row.eligible)} · SST matched {String(row.sst_matched ?? "unavailable")} · low support {String(row.low_support ?? "unavailable")} · partial period {String(row.partial_period ?? "unavailable")}</title></circle> : null)}
    <text x="50" y="205">{String(rows[0].period || rows[0].year)}</text><text x="610" y="205">{String(rows[rows.length-1].period || rows[rows.length-1].year)}</text>
  </svg><button className="button secondary-button" type="button" onClick={() => exportFigure(svg.current, `${label} · loaded published rows; gaps unavailable, orange low support`, rows, exportMetadata)}>Export {label} SVG</button></div>;
}

export function periodOrder(row: Row): string {
  const value = String(row.period || row.year);
  return value.replace(/-(DJF|MAM|JJA|SON)$/, (_, season: string) => ({DJF: "-01", MAM: "-03", JJA: "-06", SON: "-09"}[season] || ""));
}

export function ResearchSeriesPlot({ rows, taxa, onSelect, exportMetadata }: {rows: Row[]; exportMetadata?: ExportMetadata; taxa: {taxon_key: string; species: string}[]; onSelect: (id: string) => void}) {
  const groups = new Map<string,Row[]>();
  rows.forEach(row => { const key = [row.protocol_id,row.taxon_key,row.area_id,row.season,row.period_kind].join("/"); groups.set(key,[...(groups.get(key)||[]),row]); });
  return <section aria-label="Published frequency and SST series"><p>Charts show the loaded page, with separate protocol, species, area and period groups. Missing values break lines; orange outlines flag low sample support; point details include partial-period flags. Temperatures have a separate axis and matched denominator.</p>
    {groups.size > 6 ? <p role="status">Showing the first six series groups. Select a species, protocol or area to inspect another group.</p> : null}
    {[...groups.entries()].slice(0,6).map(([key,group]) => { const ordered = [...group].sort((a,b) => periodOrder(a).localeCompare(periodOrder(b))); const first = ordered[0]; return <figure key={key}><figcaption>{taxa.find(t => t.taxon_key === first.taxon_key)?.species || String(first.taxon_key)} · {String(first.area_id || "Regional")} · {String(first.season || first.period_kind)}</figcaption><Series rows={ordered} field="frequency" label="Detection frequency (0–1)" onSelect={onSelect} exportMetadata={exportMetadata} />{ordered.some(r => "sample_time_sst_mean_celsius" in r) ? <Series rows={ordered} field="sample_time_sst_mean_celsius" label="Sample-time SST context (°C)" onSelect={onSelect} exportMetadata={exportMetadata} /> : null}</figure>; })}
  </section>;
}
