"use client";

import { useEffect, useId, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import type { Availability, CatalogueListing, CatalogueNode, EvidenceScope } from "./catalogue-contract";
import type { Locale } from "./model";

export function PanelSeparator({ value, onChange, label, minimum = 320, maximum = 620 }: {
  value: number; onChange: (value: number) => void; label: string; minimum?: number; maximum?: number;
}) {
  const cleanup = useRef<() => void>(() => undefined);
  useEffect(() => () => cleanup.current(), []);
  const clamp = (next: number) => Math.max(minimum, Math.min(maximum, next));
  return <div className="pane-divider shell-separator" role="separator" aria-orientation="vertical" aria-label={label} aria-valuemin={minimum} aria-valuemax={maximum} aria-valuenow={value} tabIndex={0}
    onKeyDown={(event) => {
      const next = event.key === "ArrowLeft" ? value + 20 : event.key === "ArrowRight" ? value - 20 : event.key === "Home" ? minimum : event.key === "End" ? maximum : undefined;
      if (next !== undefined) { event.preventDefault(); onChange(clamp(next)); }
    }} onPointerDown={(event) => {
      event.preventDefault(); cleanup.current();
      const move = (pointer: PointerEvent) => onChange(clamp(window.innerWidth - pointer.clientX));
      const end = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", end); window.removeEventListener("pointercancel", end); cleanup.current = () => undefined; };
      cleanup.current = end; window.addEventListener("pointermove", move); window.addEventListener("pointerup", end); window.addEventListener("pointercancel", end);
    }} />;
}

export type ShellPanelTab = { id: string; label: string; content: ReactNode };

export function ShellTabs({ tabs, active, onChange, label }: { tabs: readonly ShellPanelTab[]; active: string; onChange: (id: string) => void; label: string }) {
  const prefix = useId(); const current = tabs.some((tab) => tab.id === active) ? active : tabs[0]?.id;
  return <><div className="shell-tabs" role="tablist" aria-label={label}>{tabs.map((tab, index) => <button key={tab.id} type="button" id={`${prefix}-tab-${tab.id}`} role="tab" aria-controls={`${prefix}-panel-${tab.id}`} aria-selected={current === tab.id} tabIndex={current === tab.id ? 0 : -1} onClick={() => onChange(tab.id)} onKeyDown={(event) => {
    const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index - 1 + tabs.length) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
    if (next < 0) return; event.preventDefault(); onChange(tabs[next].id); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }}>{tab.label}</button>)}</div>{tabs.map((tab) => <div key={tab.id} id={`${prefix}-panel-${tab.id}`} role="tabpanel" aria-labelledby={`${prefix}-tab-${tab.id}`} hidden={current !== tab.id} tabIndex={0}>{tab.content}</div>)}</>;
}

/** Reusable conversation/list + Workspace/inspector slots; presentation only. */
export function ShellSplitPanels({ primary, secondary, primaryLabel, secondaryLabel, locale, width, open, active, onWidth, onOpen, onActive }: {
  primary: ReactNode; secondary: ReactNode; primaryLabel: string; secondaryLabel: string; locale: Locale;
  width: number; open: boolean; active: "primary" | "secondary"; onWidth: (width: number) => void; onOpen: (open: boolean) => void; onActive: (active: "primary" | "secondary") => void;
}) {
  const trigger = useRef<HTMLButtonElement>(null); const id = useId();
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 950px)");
    const update = () => setNarrow(media.matches); update();
    media.addEventListener("change", update); return () => media.removeEventListener("change", update);
  }, []);
  const selected = open ? active : "primary";
  const close = () => { onOpen(false); onActive("primary"); requestAnimationFrame(() => trigger.current?.focus()); };
  return <section className={`shell-split ${open ? "secondary-open" : ""}`} data-pane={selected} style={{ "--workspace-width": `${width}px` } as CSSProperties}>
    <div className="shell-panel-toolbar"><span>{primaryLabel}</span><button ref={trigger} className="icon-button" aria-controls={`${id}-secondary`} aria-expanded={open} aria-label={`${open ? locale === "en" ? "Close" : "閉じる" : locale === "en" ? "Open" : "開く"} ${secondaryLabel}`} onClick={() => { onOpen(!open); onActive(open ? "primary" : "secondary"); }}>{open ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}</button></div>
    <div className="shell-mobile-tabs" role="tablist" aria-label={locale === "en" ? `${primaryLabel} panels` : `${primaryLabel}パネル`}>{(["primary", "secondary"] as const).map((pane, index) => <button key={pane} role="tab" id={`${id}-${pane}-tab`} aria-controls={`${id}-${pane}`} aria-selected={selected === pane} tabIndex={selected === pane ? 0 : -1} onClick={() => { onActive(pane); if (pane === "secondary") onOpen(true); }} onKeyDown={(event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault(); const next = event.key === "Home" ? "primary" : event.key === "End" ? "secondary" : pane === "primary" ? "secondary" : "primary";
      onActive(next); if (next === "secondary") onOpen(true); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('button')[next === "primary" ? 0 : 1]?.focus();
    }}>{index === 0 ? primaryLabel : secondaryLabel}</button>)}</div>
    <div className="shell-split-body"><div id={`${id}-primary`} className="shell-primary" role={narrow ? "tabpanel" : "region"} tabIndex={narrow ? 0 : undefined} aria-labelledby={narrow ? `${id}-primary-tab` : undefined} aria-label={narrow ? undefined : primaryLabel} hidden={narrow && selected !== "primary"}>{primary}</div>
      {open && <PanelSeparator value={width} onChange={onWidth} label={locale === "en" ? `Resize ${secondaryLabel}` : `${secondaryLabel}の幅を変更`} />}
      <aside id={`${id}-secondary`} className="shell-secondary" role={narrow ? "tabpanel" : "region"} tabIndex={narrow ? 0 : undefined} aria-labelledby={narrow ? `${id}-secondary-tab` : undefined} aria-label={narrow ? undefined : secondaryLabel} hidden={!open || narrow && selected !== "secondary"}><header><h2>{secondaryLabel}</h2><button className="icon-button" aria-label={locale === "en" ? `Close ${secondaryLabel}` : `${secondaryLabel}を閉じる`} onClick={close}><PanelRightClose size={17} /></button></header>{secondary}</aside>
    </div>
  </section>;
}

export type ShellScientificContext = {
  snapshotId: CatalogueNode["snapshot_id"]; scope: EvidenceScope; availability: Availability;
  sourceCompleteness: CatalogueListing["source_completeness"]; queryCompletion: CatalogueListing["query_completion"];
};

/** Labels reflect supplied C08 values; no shell action can change their scope. */
export function ScientificContextLabels({ context, locale }: { context: ShellScientificContext; locale: Locale }) {
  const labels = locale === "en" ? { snapshot: "Snapshot", scope: "Scope", source: "Source completeness", query: "Query completion", availability: "Availability" } : { snapshot: "スナップショット", scope: "対象範囲", source: "ソースの完全性", query: "クエリの完了状態", availability: "利用状況" };
  const filtered = Object.values(context.scope.sources).some((source) => Object.values(source.filters).some((value) => value != null) || ("analysis_id" in source && source.analysis_id != null));
  return <div><dl className="shell-context-labels"><div><dt>{labels.snapshot}</dt><dd><code>{context.snapshotId}</code></dd></div><div><dt>{labels.scope}</dt><dd>{Object.entries(context.scope.sources).filter(([, source]) => source.enabled).map(([family]) => family).join(" · ") || (locale === "en" ? "No enabled sources" : "有効なソースなし")}{filtered && <span> · {locale === "en" ? "Filters applied" : "絞り込みあり"}</span>}</dd></div><div><dt>{labels.source}</dt><dd>{context.sourceCompleteness}</dd></div><div><dt>{labels.query}</dt><dd>{context.queryCompletion}</dd></div><div><dt>{labels.availability}</dt><dd>{context.availability.status}{context.availability.reason ? ` · ${context.availability.reason}` : ""}</dd></div></dl><details className="shell-scope-details"><summary>{locale === "en" ? "Exact scope" : "正確な対象範囲"}</summary><pre>{JSON.stringify(context.scope, null, 2)}</pre></details></div>;
}
