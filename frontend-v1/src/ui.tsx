"use client";
import { useEffect, useId, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { AlertCircle, ArrowRight, Database, FileSearch, LockKeyhole, Search, X } from "lucide-react";
import { translate } from "./i18n";
import type { Locale, Scenario, Table } from "./model";
import { downloadBlob, exportTable, tableCsv, type TableExportSource } from "./exports";

export function tabKey<T extends string>(event: ReactKeyboardEvent<HTMLButtonElement>, index: number, tabs: T[], activate: (tab: T) => void) {
  const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
  if (next < 0) return;
  event.preventDefault(); activate(tabs[next]); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button[role="tab"]')[next]?.focus();
}
export function Modal({ title, children, onClose, locale, restoreFocusTo }: { restoreFocusTo?: HTMLElement | null; title: string; children: ReactNode; onClose: () => void; locale: Locale }) {
  const id = useId(); const ref = useRef<HTMLDivElement>(null); const t = translate(locale);
  useEffect(() => {
    const previous = restoreFocusTo ?? document.activeElement as HTMLElement | null;
    const panel = ref.current;
    const focusables = () => Array.from(panel?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, textarea, a[href], [tabindex="0"]') ?? []);
    (panel?.querySelector<HTMLElement>("[data-autofocus]") ?? focusables()[0])?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const items = focusables(); const first = items[0]; const last = items.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); if (previous?.isConnected) previous.focus(); };
  }, [onClose, title, restoreFocusTo]);
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="modal" ref={ref} role="dialog" aria-modal="true" aria-labelledby={id}><header><h2 id={id}>{title}</h2><button className="icon-button" onClick={onClose} aria-label={t("close")}><X size={18} /></button></header>{children}</div></div>;
}
export function StatePanel({ scenario, locale, onRecover }: { scenario: Scenario | "missing"; locale: Locale; onRecover?: () => void }) {
  const t = translate(locale);
  const key = scenario === "zero" ? "zero" : scenario === "empty" ? "empty" : scenario === "loading" ? "loading" : scenario === "revoked" ? "revoked" : scenario === "error" ? "error" : "unavailable";
  const Icon = scenario === "revoked" ? LockKeyhole : scenario === "zero" ? Search : scenario === "error" ? AlertCircle : Database;
  return <div className="state-panel" role={scenario === "error" ? "alert" : "status"}><Icon size={28} strokeWidth={1.5} className={scenario === "loading" ? "pulse" : ""} /><h3>{t(key)}</h3>{scenario !== "loading" && <p>{t(scenario === "zero" ? "noMatchesHelp" : scenario === "revoked" ? "revokedHelp" : "unavailableHelp")}</p>}{onRecover && <button className="button secondary" onClick={onRecover}>{t(scenario === "error" ? "retry" : "recover")}<ArrowRight size={15} /></button>}</div>;
}
export function DataTable({ table, locale, limit }: { table: Table; locale: Locale; limit?: number }) {
  const t = translate(locale);
  return <div className="table-scroll" tabIndex={0} aria-label={table.entity[locale]}><table><caption className="sr-only">{t("sample")} · {table.entity[locale]}</caption><thead><tr>{table.columns.map((column) => <th key={column.key} scope="col">{column.title[locale]}{column.unit && <span className="unit"> {column.unit}</span>}</th>)}</tr></thead><tbody>{table.rows.slice(0, limit ?? table.rows.length).map((row, i) => <tr key={i}>{table.columns.map((column) => { const value = row[column.key]; const display = typeof value === "string" && value.includes(" / ") ? value.split(" / ")[locale === "en" ? 0 : 1] : value; return <td key={column.key} className={typeof value === "number" ? "numeric" : undefined}>{display}</td>; })}</tr>)}</tbody></table></div>;
}
export function TemperaturePlot({ series, locale }: { series: { label: string; value: number }[]; locale: Locale }) {
  const id = useId(); const t = translate(locale); const x = (index: number) => 30 + index * 27; const y = (value: number) => 140 - (value - 5) * 5;
  const points = series.map((point, i) => `${x(i)},${y(point.value)}`).join(" ");
  return <figure className="temperature-plot"><figcaption><span>{locale === "en" ? "Regional SST" : "地域の海面水温"} <span className="unit">°C</span></span><span className="small-badge">{t("sample")}</span></figcaption><svg viewBox="0 0 350 175" role="img" aria-label={locale === "en" ? "Sample monthly temperature, February 8.4°C to August 22.6°C" : "サンプル月別水温。2月8.4°C、8月22.6°C"}><defs><linearGradient id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity=".22" /><stop offset="100%" stopColor="var(--accent)" stopOpacity=".01" /></linearGradient></defs>{[10, 15, 20, 25].map((value) => <g key={value}><line x1="30" x2="327" y1={y(value)} y2={y(value)} stroke="var(--line)" /><text x="3" y={y(value) + 4}>{value}</text></g>)}<polygon points={`30,146 ${points} 327,146`} fill={`url(#${id})`} /><polyline points={points} fill="none" stroke="var(--blue-ink)" strokeWidth="2.5" strokeLinejoin="round" />{series.map((point, i) => <circle key={point.label} cx={x(i)} cy={y(point.value)} r="3" fill="var(--surface)" stroke="var(--blue-ink)" strokeWidth="1.8"><title>{point.label}: {point.value}°C</title></circle>)}{[0, 3, 6, 9, 11].map((i) => <text key={i} x={x(i)} y="167" textAnchor="middle">{locale === "en" ? ["Jan", "Apr", "Jul", "Oct", "Dec"][[0, 3, 6, 9, 11].indexOf(i)] : `${i + 1}月`}</text>)}</svg></figure>;
}
export function EmptyWorkspace({ title, action }: { title: string; action?: ReactNode }) { return <div className="empty-workspace"><FileSearch size={28} strokeWidth={1.3} /><p>{title}</p>{action}</div>; }
export function downloadTable(table: Table, filename: string, locale: Locale, source?: TableExportSource) {
  downloadBlob(tableCsv(exportTable(table, source), locale), filename, "text/csv;charset=utf-8");
}
