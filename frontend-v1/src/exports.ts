import type { Investigation, Locale, Receipt, Table } from "./model.ts";
import { escapeCsvCell } from "../../frontend/lib/csv.ts";

export function safeCell(value: unknown): string {
  return escapeCsvCell(value, true);
}
export function tableCsv(table: Table, locale: Locale): string {
  return "\ufeff" + [table.columns.map((column) => safeCell(`${column.title[locale]}${column.unit ? ` (${column.unit})` : ""}`)).join(","), ...table.rows.map((row) => table.columns.map((column) => safeCell(row[column.key])).join(","))].join("\r\n");
}
export type TableExportSource = { snapshotId: string; recordId: string; authority?: "descriptive" | "published" | "experimental" };
export function exportTable(table: Table, source?: TableExportSource): Table {
  const metadata = [{ key: "_preview", title: { en: "Preview", ja: "プレビュー" } }, ...(source ? [{ key: "_snapshot", title: { en: "Snapshot", ja: "スナップショット" } }, { key: "_record", title: { en: "Record", ja: "記録" } }] : [])];
  if (source?.authority) metadata.push({ key: "_authority", title: { en: "Authority", ja: "権威区分" } });
  return { ...table, columns: [...metadata, ...table.columns], rows: table.rows.map((row) => ({ ...row, _preview: "P00 synthetic sample", ...(source ? { _snapshot: source.snapshotId, _record: source.recordId, ...(source.authority ? { _authority: source.authority } : {}) } : {}) })) };
}
export function investigationExport(investigation: Investigation) {
  return { format: "ocean-p00-preview-1", label: "Synthetic local preview; not scientific publication", investigation: structuredClone(investigation) };
}
export function receiptExport(receipt: Receipt) {
  return { format: "ocean-p00-evidence-1", label: "Synthetic evidence receipt", receipt: structuredClone(receipt) };
}
export function investigationMarkdown(investigation: Investigation, locale: Locale): string {
  const lines = [`# ${investigation.title}`, "", "P00 synthetic local preview — not scientific publication.", "", `Snapshot: ${investigation.snapshotId}`, `Context revision: ${investigation.context.revision}`, ""];
  for (const chat of investigation.conversations) { lines.push(`## ${chat.title[locale]}`, ""); for (const message of chat.messages) { lines.push(`### ${message.role === "user" ? "You" : "OCEAN · sample answer"}`, "", message.body[locale], ""); if (message.answer) lines.push(`Evidence: ${message.answer.receipt.id} · ${message.answer.receipt.snapshotId}`, message.answer.receipt.limitation[locale], ""); } }
  return lines.join("\n");
}
export function plotSvg(series: { label: string; value: number }[]): string {
  const points = series.map((point, index) => `${40 + index * 30},${180 - (point.value - 5) * 7}`).join(" ");
  const grid = [10, 15, 20, 25].map((value) => `<line x1="40" x2="370" y1="${180 - (value - 5) * 7}" y2="${180 - (value - 5) * 7}" stroke="#dfebf1"/><text x="15" y="${184 - (value - 5) * 7}" font-size="10">${value}</text>`).join("");
  const months = [[0, "Jan"], [3, "Apr"], [6, "Jul"], [9, "Oct"], [11, "Dec"]].map(([index, label]) => `<text x="${40 + Number(index) * 30}" y="198" font-size="10" text-anchor="middle">${label}</text>`).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 430 245" font-family="Arial" fill="#193448"><rect width="430" height="245" fill="white"/><title>P00 sample regional SST · synthetic descriptive result</title><text x="30" y="25" font-size="13">Sample regional SST · °C</text>${grid}<polyline points="${points}" fill="none" stroke="#247fae" stroke-width="3"/>${months}<text x="30" y="226" font-size="10" fill="#5b7180">Synthetic preview. Regional data does not establish site temperature.</text></svg>`;
}
export function downloadBlob(content: string | Blob, filename: string, mime = "application/json") {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename.replace(/[^a-zA-Z0-9_.-]/g, "_"); anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const downloadJson = (value: unknown, filename: string) => downloadBlob(JSON.stringify(value, null, 2), filename, "application/json");
