"use client";

import { useState } from "react";

type Row = Record<string, unknown>;
const groupKey = (row: Row) => JSON.stringify([row.partition_id, row.variable, row.evidence_type]);

/** Only a single protocol/method/variable partition is plotted at a time. */
export function EdnaEnvironmentPlot({ rows, onSelect }: { rows: Row[]; onSelect: (id: string) => void }) {
  const groups = [...new Set(rows.map(groupKey))];
  const [group, setGroup] = useState(groups[0] || "");
  const selected = rows.filter(row => groupKey(row) === group);
  const points = selected.filter(row => typeof row.value === "number" && Number.isFinite(row.value) && typeof row.shannon === "number" && Number.isFinite(row.shannon));
  const first = selected[0];
  if (!first) return null;
  const xs = points.map(row => Number(row.value)), ys = points.map(row => Number(row.shannon));
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const x = (n: number) => 64 + (xmax === xmin ? 0.5 : (n - xmin) / (xmax - xmin)) * 480;
  const y = (n: number) => 260 - (ymax === ymin ? 0.5 : (n - ymin) / (ymax - ymin)) * 220;
  const number = (n: number) => Number(n.toPrecision(4)).toString();
  return <section aria-label="Environmental association plot">
    <label className="control-label">Plot partition<select className="field" value={group} onChange={event => setGroup(event.target.value)}>{groups.map(key => {
      const row = rows.find(item => groupKey(item) === key)!;
      return <option key={key} value={key}>{String(row.assignment_method)} · {String(row.variable)} · {String(row.evidence_type)} · {String(row.partition_id).slice(0, 8)}</option>;
    })}</select></label>
    <p>{points.length} plotted pairs · displayed rows only · descriptive</p>
    {points.length ? <svg className="simple-chart" style={{ maxWidth: 640, display: "block" }} viewBox="0 0 600 320" role="group" aria-label={`Shannon index by ${String(first.variable)} (${String(first.unit)})`}>
      <title>Shannon index by {String(first.variable)} ({String(first.unit)})</title>
      <line x1={64} y1={40} x2={64} y2={260} stroke="currentColor" />
      <line x1={64} y1={260} x2={544} y2={260} stroke="currentColor" />
      {[...new Set([xmin, xmax])].map(value => <text key={value} x={x(value)} y={282} textAnchor="middle" fontSize={12}>{number(value)}</text>)}
      {[...new Set([ymin, ymax])].map(value => <text key={value} x={56} y={y(value) + 4} textAnchor="end" fontSize={12}>{number(value)}</text>)}
      <text x={64} y={22} fontSize={13}>Shannon (ln)</text>
      <text x={300} y={310} textAnchor="middle" fontSize={13}>{String(first.variable)} ({String(first.unit)})</text>
      {points.map(row => <circle key={String(row.result_id)} cx={x(Number(row.value))} cy={y(Number(row.shannon))} r={5} fill="currentColor" tabIndex={0} role="button" aria-label={`Open result for ${row.sample_id}`} onClick={() => onSelect(String(row.result_id))} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(String(row.result_id)); } }}><title>{String(row.sample_id)}: {number(Number(row.value))}, {number(Number(row.shannon))}</title></circle>)}
    </svg> : <p>No eligible pairs.</p>}
  </section>;
}
