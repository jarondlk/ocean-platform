"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, ChevronDown, ChevronRight, Database, FileText, Folder, Layers3, Search, X } from "lucide-react";
import type { CatalogueFilters, CatalogueListing, CatalogueNode, EvidenceScope } from "./catalogue-contract";
import { createCatalogueClient, defaultCatalogueScope, type CatalogueClient, type CatalogueDetails, type CatalogueSnapshotPage, type ScientificResponse } from "./catalogue-service";
import { catalogueLocationUrl, parseCatalogueLocation, updateCatalogueLocation, type CatalogueLocation, type CatalogueSelectionEvent, type DatasetSection } from "./catalogue-browser-state";
import { ScientificContextLabels } from "./shell-panels";
import type { Locale } from "./model";
import "./catalogue-browser.css";

const roots = ["data", "analyses", "statistics", "metadata", "relationships"] as const;
const rootLabels = { data: ["Data", "データ"], analyses: ["Analyses", "解析"], statistics: ["Statistics", "統計"], metadata: ["Metadata", "メタデータ"], relationships: ["Relationships", "関連性"] };
const sections = ["overview", "tables", "coverage", "methods", "provenance", "related"] as const;
const sectionLabels = { overview: ["Overview", "概要"], tables: ["Tables", "テーブル"], coverage: ["Coverage", "カバレッジ"], methods: ["Methods", "手法"], provenance: ["Provenance", "来歴"], related: ["Related", "関連"] };
const families = ["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"] as const;
const familyLabels = ["CTD", "Metagenome", "SST", "eDNA"];
const say = (locale: Locale, en: string, ja: string) => locale === "en" ? en : ja;
const localized = (labels: readonly string[], locale: Locale) => labels[locale === "en" ? 0 : 1];
const emptyFilters = (): CatalogueFilters => ({ roots: [], source_families: [], kinds: [], authorities: [], search: null });
const isDirectory = (node: CatalogueNode) => node.kind === "root" || node.kind === "directory";
type Load<T> = { key: string; status: "loading" } | { key: string; status: "ready"; data: T } | { key: string; status: "error"; error: unknown };
type Selection = CatalogueSelectionEvent;

/** An explicit selection is a notification; this component never attaches or pins. */
export type CatalogueBrowserProps = {
  locale: Locale;
  accessKey: string;
  client?: CatalogueClient;
  scope?: EvidenceScope;
  pinnedSnapshotId?: string;
  onSelect?: (selection: Selection) => void;
  onAccessLost?: () => void;
};

function useLoad<T>(key: string | null, run: (signal: AbortSignal) => Promise<T>): Load<T> | null {
  const latest = useRef(run); latest.current = run;
  const [state, setState] = useState<Load<T> | null>(null);
  useEffect(() => {
    if (key === null) { setState(null); return; }
    const controller = new AbortController();
    setState({ key, status: "loading" });
    const timeout = setTimeout(() => {
      controller.abort(); setState({ key, status: "error", error: { code: "request_timeout" } });
    }, 15_000);
    void latest.current(controller.signal).then((data) => {
      if (!controller.signal.aborted) setState({ key, status: "ready", data });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ key, status: "error", error });
    }).finally(() => clearTimeout(timeout));
    return () => { clearTimeout(timeout); controller.abort(); };
  }, [key]);
  return key === null ? null : state?.key === key ? state : { key, status: "loading" };
}

function errorCode(error: unknown): string {
  return error !== null && typeof error === "object" && "code" in error && typeof error.code === "string" ? error.code : "catalogue_unavailable";
}

export function CatalogueBrowser({ locale, accessKey, client: providedClient, scope: providedScope, pinnedSnapshotId, onSelect, onAccessLost }: CatalogueBrowserProps) {
  const client = useMemo(() => providedClient ?? createCatalogueClient(), [providedClient]);
  const scope = useMemo(() => providedScope ?? defaultCatalogueScope(), [providedScope]);
  const [location, setLocation] = useState<CatalogueLocation>(() => parseCatalogueLocation(""));
  const [located, setLocated] = useState(false);
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState("");
  const [treeOpen, setTreeOpen] = useState(false);
  const [inspectOpen, setInspectOpen] = useState(false);
  const [snapshotCursor, setSnapshotCursor] = useState<string | null>(null);
  const [snapshotOptions, setSnapshotOptions] = useState<CatalogueSnapshotPage["snapshots"]>([]);
  const [previousPages, setPreviousPages] = useState<(string | null)[]>([]);
  const [blocked, setBlocked] = useState<unknown | null>(null);
  const [securityEpoch, setSecurityEpoch] = useState(0);
  const epochRef = useRef(0);
  const serviceContext = useRef<{ snapshot: string; binding: string; revision: string } | null>(null);
  const discoveryContext = useRef<string | null>(null);
  const locationRef = useRef(location); locationRef.current = location;
  const treeTrigger = useRef<HTMLButtonElement>(null);
  const treeRef = useRef<HTMLElement>(null);
  const inspectorRef = useRef<HTMLElement>(null);
  const inputId = useId();
  const scopeKey = JSON.stringify(scope);
  const navigate = useCallback((patch: Partial<CatalogueLocation>, replace = false) => {
    const next = updateCatalogueLocation(locationRef.current, patch);
    locationRef.current = next;
    if (!pinnedSnapshotId) window.history[replace ? "replaceState" : "pushState"](null, "", catalogueLocationUrl(next));
    setLocation(next);
  }, [pinnedSnapshotId]);
  const invalidate = useCallback((error: unknown) => {
    ++epochRef.current; setSecurityEpoch(epochRef.current); setBlocked(error);
    serviceContext.current = null; discoveryContext.current = null;
    setSnapshotOptions([]); setSnapshotCursor(null); setTreeOpen(false); setInspectOpen(false);
    if (["authentication_required", "access_denied"].includes(errorCode(error))) onAccessLost?.();
  }, [onAccessLost]);
  const guarded = async <T,>(operation: () => Promise<T>): Promise<T> => {
    try {
      const value = await operation();
      if (securityEpoch !== epochRef.current) throw new DOMException("Stale catalogue request", "AbortError");
      return value;
    } catch (error) {
      if (securityEpoch === epochRef.current && ["authentication_required", "access_denied", "not_found", "invalid_cursor"].includes(errorCode(error))) invalidate(error);
      throw error;
    }
  };
  const acceptListing = (value: CatalogueListing): CatalogueListing => {
    if (securityEpoch !== epochRef.current) throw new DOMException("Stale catalogue request", "AbortError");
    const snapshot = JSON.stringify([accessKey, value.request.snapshot_id, scopeKey]);
    const previous = serviceContext.current;
    if (previous?.snapshot === snapshot && (previous.binding !== value.request.access_binding || previous.revision !== value.request.access_revision)) {
      const error = { code: "invalid_cursor" }; invalidate(error); throw error;
    }
    serviceContext.current = { snapshot, binding: value.request.access_binding, revision: value.request.access_revision };
    return value;
  };
  useEffect(() => {
    const restore = () => {
      try { setLocation(parseCatalogueLocation(pinnedSnapshotId ? "" : window.location.search)); }
      catch { setLocation(parseCatalogueLocation("")); setBlocked({ code: "invalid_location" }); }
      setPreviousPages([]); setTreeOpen(false);
    };
    restore(); setLocated(true);
    window.addEventListener("popstate", restore); return () => window.removeEventListener("popstate", restore);
  }, [pinnedSnapshotId]);
  useEffect(() => { setSearch(location.filters.search ?? ""); }, [location.filters.search]);
  useEffect(() => { setSnapshotOptions([]); setSnapshotCursor(null); }, [accessKey, scopeKey]);
  const discovery = useLoad(blocked ? null : JSON.stringify([accessKey, scopeKey, snapshotCursor, retry, securityEpoch]), async (signal) => {
    try {
      const value = await guarded(() => client.snapshots({ scope, limit: 100, ...(snapshotCursor ? { cursor: snapshotCursor } : {}) }, signal));
      if (discoveryContext.current && discoveryContext.current !== value.access_revision) {
        const error = { code: "invalid_cursor" }; invalidate(error); throw error;
      }
      discoveryContext.current = value.access_revision; return value;
    } catch (error) {
      if (securityEpoch === epochRef.current && !(error instanceof Error && error.name === "AbortError")) invalidate(error);
      throw error;
    }
  });
  useEffect(() => {
    if (discovery?.status !== "ready" || blocked || securityEpoch !== epochRef.current) return;
    setSnapshotOptions((current) => {
      const unique = new Map((snapshotCursor ? current : []).map((item) => [item.snapshot_id, item]));
      discovery.data.snapshots.forEach((item) => unique.set(item.snapshot_id, item)); return [...unique.values()];
    });
    if (located && !pinnedSnapshotId && location.snapshotId === null && discovery.data.latest_snapshot_id) navigate({ snapshotId: discovery.data.latest_snapshot_id }, true);
  }, [discovery, snapshotCursor, located, pinnedSnapshotId, location.snapshotId, navigate, blocked, securityEpoch]);
  const snapshotId = pinnedSnapshotId ?? location.snapshotId;
  const eligibilityVerified = discovery?.status === "ready" && !blocked;
  const base = snapshotId ? { snapshot_id: snapshotId, scope } : null;
  const contextKey = JSON.stringify([accessKey, snapshotId, scopeKey, retry, securityEpoch]);
  const observeError = useCallback((error: unknown) => {
    if (["authentication_required", "access_denied", "not_found", "invalid_cursor"].includes(errorCode(error))) invalidate(error);
  }, [invalidate]);
  const rootsLoad = useLoad(base && eligibilityVerified ? contextKey : null, async (signal) => {
    return acceptListing(await guarded(() => client.overview(base!, signal)));
  });
  const listingKey = JSON.stringify([contextKey, location.parentId, location.nodeId, location.section, location.filters, location.cursor, location.limit]);
  const listing = useLoad(base && eligibilityVerified ? listingKey : null, async (signal) => {
    return acceptListing(await guarded(async () => {
      const filters = location.filters;
      if (location.parentId === null && !filters.search && !filters.roots?.length && !filters.kinds?.length && !filters.source_families?.length && !filters.authorities?.length && location.cursor === null) return await client.overview(base!, signal);
      return await client.list({ ...base!, parent_id: location.parentId, filters, limit: location.limit, ...(location.cursor ? { cursor: location.cursor } : {}) }, signal);
    }));
  });
  const selectedId = location.nodeId ?? location.parentId;
  const detailKey = JSON.stringify([contextKey, selectedId]);
  const details = useLoad(base && selectedId && eligibilityVerified ? detailKey : null, async (signal) => {
    return await guarded(() => client.open({ ...base!, object_id: selectedId!, include_details: true }, signal));
  });
  const breadcrumbs = useLoad(base && selectedId && eligibilityVerified ? detailKey : null, async (signal) => {
    const path: CatalogueNode[] = []; let current: string | null = selectedId;
    while (current) {
      if (path.length >= 128 || path.some((item) => item.id === current)) throw new Error("Invalid catalogue ancestry");
      const identity: string = current;
      const node = await guarded(() => client.open({ ...base!, object_id: identity }, signal));
      path.unshift(node); current = node.parent_id;
    }
    return path;
  });
  const openNode = (node: CatalogueNode) => {
    setPreviousPages([]);
    if (isDirectory(node)) navigate({ parentId: node.id, nodeId: node.id, section: "overview", filters: { ...location.filters, search: null }, cursor: null });
    else { navigate({ nodeId: node.id, section: "overview" }); setInspectOpen(true); }
    setTreeOpen(false);
  };
  const resetList = () => {
    const code = errorCode(blocked);
    serviceContext.current = null; discoveryContext.current = null;
    setPreviousPages([]); setBlocked(null); setSnapshotCursor(null);
    if (["not_found", "invalid_cursor", "invalid_location"].includes(code)) navigate({ nodeId: null, parentId: null, cursor: null, section: "overview", ...(code === "not_found" && !pinnedSnapshotId ? { snapshotId: null } : {}) });
    else navigate({ cursor: null });
    setRetry((value) => value + 1);
  };
  const applyFilters = (filters: CatalogueFilters) => { setPreviousPages([]); navigate({ filters, cursor: null }); };
  const submitSearch = (event: FormEvent) => {
    event.preventDefault(); setPreviousPages([]);
    navigate({ parentId: null, nodeId: null, filters: { ...location.filters, search: search.trim() || null }, cursor: null });
  };
  const visibleRoots = rootsLoad?.status === "ready" ? rootsLoad.data.items : [];
  const selected = details?.status === "ready" ? details.data.node : null;
  const chooseSnapshot = (value: string) => {
    setPreviousPages([]); setInspectOpen(false); setSnapshotCursor(null);
    navigate({ snapshotId: value, nodeId: null, parentId: null, cursor: null, section: "overview" });
  };
  const visibleSnapshotOptions = eligibilityVerified ? snapshotOptions : [];
  const requestedOptionMissing = snapshotId && !visibleSnapshotOptions.some((item) => item.snapshot_id === snapshotId);
  const hasFilters = !!location.filters.search || [location.filters.roots, location.filters.source_families, location.filters.kinds, location.filters.authorities].some((items) => (items?.length ?? 0) > 0);
  const listData = listing?.status === "ready" ? listing.data : null;
  const closeTree = () => { setTreeOpen(false); requestAnimationFrame(() => treeTrigger.current?.focus()); };
  useEffect(() => {
    if (!inspectOpen || !selectedId || !window.matchMedia("(max-width: 760px)").matches) return;
    const frame = requestAnimationFrame(() => inspectorRef.current?.scrollIntoView({ block: "start" }));
    return () => cancelAnimationFrame(frame);
  }, [inspectOpen, selectedId]);
  useEffect(() => {
    if (!treeOpen) return;
    const previous = treeTrigger.current;
    const items = () => Array.from(treeRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), [role="treeitem"][tabindex="0"]') ?? []).filter((item) => item.tabIndex >= 0 && item.getClientRects().length > 0);
    const frame = requestAnimationFrame(() => items()[0]?.focus());
    const key = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setTreeOpen(false); }
      if (event.key === "Tab") {
        const list = items(), first = list[0], last = list.at(-1);
        if (!first) { event.preventDefault(); return; }
        if (event.shiftKey && (document.activeElement === first || !treeRef.current?.contains(document.activeElement))) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !treeRef.current?.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    };
    const narrow = window.matchMedia("(max-width: 760px)");
    const resize = () => { if (!narrow.matches) setTreeOpen(false); };
    document.addEventListener("keydown", key); narrow.addEventListener("change", resize);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("keydown", key); narrow.removeEventListener("change", resize); if (previous?.isConnected) previous.focus(); };
  }, [treeOpen]);

  return <section className="catalogue-browser" aria-label={say(locale, "Context Catalog", "コンテキストカタログ")}>
    <header className="cb-heading"><div><div className="eyebrow">OCEAN / v1</div><h1>{say(locale, "Context Catalog", "コンテキストカタログ")}</h1><p>{say(locale, "Browse data and context. Your investigation is unchanged.", "データとコンテキストを閲覧します。調査の設定は変わりません。")}</p></div>
      <div className="cb-snapshot"><label><span>{say(locale, pinnedSnapshotId ? "Investigation snapshot" : "Snapshot", pinnedSnapshotId ? "調査のスナップショット" : "スナップショット")}</span><select aria-label={say(locale, "Catalogue snapshot", "カタログのスナップショット")} value={snapshotId ?? ""} disabled={!!pinnedSnapshotId || !visibleSnapshotOptions.length} onChange={(event) => chooseSnapshot(event.target.value)}><option value="" disabled>{say(locale, "Select snapshot", "スナップショットを選択")}</option>{requestedOptionMissing && <option value={snapshotId}>{say(locale, "Requested snapshot", "指定のスナップショット")} · {snapshotId.slice(0, 12)}</option>}{visibleSnapshotOptions.map((item) => <option key={item.snapshot_id} value={item.snapshot_id}>{item.label[locale]}</option>)}</select></label>
        {discovery?.status === "ready" && discovery.data.next_cursor && <button className="text-button" onClick={() => setSnapshotCursor(discovery.data.next_cursor)}>{say(locale, "More snapshots", "ほかのスナップショット")}</button>}</div>
    </header>
    <form className="cb-search" onSubmit={submitSearch}><Search size={18} /><label className="sr-only" htmlFor={`${inputId}-search`}>{say(locale, "Search every permitted catalogue object", "アクセス可能なすべてのカタログ項目を検索")}</label><input id={`${inputId}-search`} value={search} maxLength={4000} onChange={(event) => setSearch(event.target.value)} placeholder={say(locale, "Search names, identities or paths", "名前・識別情報・パスで検索")} /><button className="button secondary" type="submit">{say(locale, "Search", "検索")}</button></form>
    <div className="cb-filters"><label>{say(locale, "Source", "ソース")}<select value={location.filters.source_families?.[0] ?? ""} onChange={(event) => applyFilters({ ...location.filters, source_families: event.target.value ? [event.target.value as typeof families[number]] : [] })}><option value="">{say(locale, "All sources", "すべてのソース")}</option>{families.map((family, index) => <option key={family} value={family}>{familyLabels[index]}</option>)}</select></label><label>{say(locale, "Kind", "種類")}<select value={location.filters.kinds?.[0] ?? ""} onChange={(event) => applyFilters({ ...location.filters, kinds: event.target.value ? [event.target.value as CatalogueNode["kind"]] : [] })}><option value="">{say(locale, "All kinds", "すべての種類")}</option>{["directory", "dataset", "table", "analysis", "workflow", "statistic", "metadata", "relationship", "reference"].map((kind) => <option key={kind} value={kind}>{kindLabel(kind, locale)}</option>)}</select></label><label>{say(locale, "Authority", "位置付け")}<select value={location.filters.authorities?.[0] ?? ""} onChange={(event) => applyFilters({ ...location.filters, authorities: event.target.value ? [event.target.value as CatalogueNode["authority"]] : [] })}><option value="">{say(locale, "All authorities", "すべての位置付け")}</option><option value="descriptive">{say(locale, "Descriptive", "記述的")}</option><option value="published">{say(locale, "Published", "公開済み")}</option><option value="experimental">{say(locale, "Experimental", "実験的")}</option></select></label>{hasFilters && <button className="text-button" onClick={() => applyFilters(emptyFilters())}><X size={14} />{say(locale, "Clear filters", "絞り込みを解除")}</button>}</div>
    {hasFilters && <div className="cb-active-filters" aria-label={say(locale, "Applied filters", "適用された絞り込み")}>{location.filters.search && <span>{say(locale, "Search", "検索")}: {location.filters.search}</span>}{(location.filters.roots ?? []).map((value) => <span key={`root:${value}`}>{say(locale, "Root", "ルート")}: {localized(rootLabels[value], locale)}</span>)}{(location.filters.source_families ?? []).map((value) => <span key={`source:${value}`}>{say(locale, "Source", "ソース")}: {familyLabels[families.indexOf(value)]}</span>)}{(location.filters.kinds ?? []).map((value) => <span key={`kind:${value}`}>{say(locale, "Kind", "種類")}: {kindLabel(value, locale)}</span>)}{(location.filters.authorities ?? []).map((value) => <span key={`authority:${value}`}>{say(locale, "Authority", "位置付け")}: {value}</span>)}</div>}
    <label className="cb-page-size">{say(locale, "Objects per page", "1ページの項目数")}<select aria-label={say(locale, "Objects per page", "1ページの項目数")} value={location.limit} onChange={(event) => { setPreviousPages([]); navigate({ limit: Number(event.target.value), cursor: null }); }}>{![25, 100, 500].includes(location.limit) && <option value={location.limit}>{location.limit}</option>}{[25, 100, 500].map((limit) => <option key={limit} value={limit}>{limit}</option>)}</select></label>
    {blocked ? <ErrorPanel error={blocked} locale={locale} retry={resetList} /> : discovery?.status === "error" && <ErrorPanel error={discovery.error} locale={locale} retry={() => setRetry((value) => value + 1)} />}
    {blocked ? null : !eligibilityVerified ? <Loading locale={locale} /> : !snapshotId ? discovery?.status === "ready" && !discovery.data.total ? <Notice title={say(locale, "No eligible snapshots", "利用可能なスナップショットがありません")} locale={locale}>{say(locale, "No catalogue snapshot is available to your current account.", "現在のアカウントで利用できるカタログのスナップショットはありません。")}</Notice> : null : <>
      <div className="cb-mobile-controls"><button ref={treeTrigger} className="button secondary" aria-expanded={treeOpen} aria-controls={`${inputId}-tree`} onClick={() => setTreeOpen(true)}><Folder size={16} />{say(locale, "Directories", "ディレクトリ")}</button>{selectedId && <button className="button secondary" aria-expanded={inspectOpen} onClick={() => setInspectOpen((value) => !value)}><FileText size={16} />{say(locale, "Inspector", "インスペクター")}</button>}</div>
      <div className="cb-layout">
        {treeOpen && <button className="cb-tree-scrim" aria-label={say(locale, "Close directories", "ディレクトリを閉じる")} onClick={closeTree} />}
        <aside ref={treeRef} id={`${inputId}-tree`} className={`cb-tree ${treeOpen ? "is-open" : ""}`} role={treeOpen ? "dialog" : undefined} aria-modal={treeOpen ? true : undefined} aria-label={say(locale, "Catalogue directories", "カタログのディレクトリ")}><div className="cb-pane-heading"><h2>{say(locale, "Directories", "ディレクトリ")}</h2><button className="icon-button cb-mobile-close" onClick={closeTree} aria-label={say(locale, "Close directories", "ディレクトリを閉じる")}><X size={16} /></button></div><button className="cb-overview-link" onClick={() => { setPreviousPages([]); navigate({ parentId: null, nodeId: null, cursor: null, filters: emptyFilters() }); setTreeOpen(false); }}><Layers3 size={15} />{say(locale, "Catalogue overview", "カタログの概要")}</button>
          {rootsLoad?.status === "loading" ? <Loading locale={locale} /> : rootsLoad?.status === "error" ? <ErrorPanel error={rootsLoad.error} locale={locale} retry={resetList} /> : <DirectoryTree key={contextKey} nodes={visibleRoots} client={client} base={base!} locale={locale} current={location.parentId} onOpen={openNode} onError={observeError} onPage={acceptListing} />}
        </aside>
        <div className="cb-list-pane" inert={treeOpen}>
          <nav className="cb-breadcrumbs" aria-label={say(locale, "Catalogue path", "カタログのパス")}><button onClick={() => navigate({ parentId: null, nodeId: null, cursor: null, filters: emptyFilters() })}>{say(locale, "Overview", "概要")}</button>{breadcrumbs?.status === "ready" && breadcrumbs.data.map((node) => <span key={node.id}><ChevronRight size={12} /><button onClick={() => openNode(node)} aria-current={node.id === selectedId ? "page" : undefined}>{node.title[locale]}</button></span>)}</nav>
          <div className="cb-list-heading"><h2>{location.filters.search ? say(locale, "Search results", "検索結果") : location.parentId ? breadcrumbs?.status === "ready" ? breadcrumbs.data.find((node) => node.id === location.parentId)?.title[locale] ?? say(locale, "Contents", "内容") : say(locale, "Contents", "内容") : say(locale, "Catalogue overview", "カタログの概要")}</h2>{listData && <span>{listData.total.value ?? say(locale, "Unknown", "不明")} {say(locale, "matching objects", "一致する項目")}</span>}</div>
          {listing?.status === "loading" ? <Loading locale={locale} /> : listing?.status === "error" ? <ErrorPanel error={listing.error} locale={locale} retry={resetList} /> : listData && <>
            {listData.availability.status !== "available" ? <Notice title={listData.availability.status === "unknown" ? say(locale, "Catalogue availability unknown", "カタログの利用状況は不明です") : say(locale, "Catalogue unavailable", "カタログを利用できません")} locale={locale}>{listData.availability.reason}</Notice> : !listData.items.length ? <Notice title={say(locale, hasFilters ? "No matching objects" : "No child objects", hasFilters ? "一致する項目がありません" : "子項目がありません")} locale={locale}>{say(locale, hasFilters ? "Change or clear the filters to search again." : "The current permitted view contains no objects here.", hasFilters ? "絞り込みを変更または解除して再検索してください。" : "現在アクセス可能なビューには、この場所の項目はありません。")}</Notice> : <ul className="cb-object-list">{listData.items.map((node) => <li key={node.id}><button onClick={() => openNode(node)} aria-pressed={location.nodeId === node.id}><span className="cb-node-icon">{isDirectory(node) ? <Folder size={20} /> : node.kind === "dataset" ? <Database size={20} /> : <FileText size={20} />}</span><span className="cb-node-label"><strong>{node.title[locale]}</strong><span>{kindLabel(node.kind, locale)}{node.source_family ? ` · ${familyLabels[families.indexOf(node.source_family)]}` : ""}</span><code>{node.id}</code></span><ChevronRight size={16} /></button></li>)}</ul>}
            <div className="cb-completeness"><span>{listData.returned_count} {say(locale, "shown", "表示")} / {listData.total.value ?? say(locale, "total unknown", "総数不明")}</span><span>{say(locale, "Source completeness", "ソースの完全性")}: {listData.source_completeness} · {say(locale, "Query", "クエリ")}: {listData.query_completion}</span></div>
            <details className="cb-applied-context"><summary>{say(locale, "Applied scope and completeness", "適用された対象範囲と完全性")}</summary><ScientificContextLabels locale={locale} context={{ snapshotId: listData.request.snapshot_id, scope: listData.request.scope, availability: listData.availability, sourceCompleteness: listData.source_completeness, queryCompletion: listData.query_completion }} /></details>
            <div className="cb-pagination"><button className="button secondary" disabled={location.cursor === null} onClick={() => { setPreviousPages([]); navigate({ cursor: null }); }}><ArrowLeft size={14} />{say(locale, "First page", "最初のページ")}</button><button className="button secondary" disabled={!previousPages.length} onClick={() => { const history = [...previousPages]; const cursor = history.pop() ?? null; setPreviousPages(history); navigate({ cursor }); }}>{say(locale, "Previous", "前へ")}</button><button className="button secondary" disabled={!listData.next_cursor} onClick={() => { setPreviousPages((current) => [...current, location.cursor]); navigate({ cursor: listData.next_cursor }); }}>{say(locale, "Next page", "次のページ")}<ArrowRight size={14} /></button></div>
          </>}
        </div>
        <aside ref={inspectorRef} className={`cb-inspector ${inspectOpen ? "is-open" : ""}`} inert={treeOpen} aria-label={say(locale, "Object inspector", "項目のインスペクター")}><div className="cb-pane-heading"><h2>{say(locale, "Inspector", "インスペクター")}</h2><button className="icon-button cb-mobile-close" onClick={() => setInspectOpen(false)} aria-label={say(locale, "Close inspector", "インスペクターを閉じる")}><X size={16} /></button></div>
          {!selectedId ? <Notice title={say(locale, "Select an object", "項目を選択してください")} locale={locale}>{say(locale, "Inspect its source, scope and qualifications here.", "ソース・対象範囲・条件をここで確認できます。")}</Notice> : details?.status === "loading" ? <Loading locale={locale} /> : details?.status === "error" ? <ErrorPanel error={details.error} locale={locale} retry={resetList} /> : details?.status === "ready" && <ObjectInspector key={detailKey} value={details.data} client={client} base={base!} locale={locale} section={location.section} allowRetainedAnalysisScope={!providedScope && !pinnedSnapshotId} onSection={(section) => navigate({ section })} onBrowse={() => { setPreviousPages([]); navigate({ parentId: details.data.node.id, nodeId: details.data.node.id, cursor: null, filters: emptyFilters(), section: "overview" }); setInspectOpen(false); }} onOpenId={(nodeId) => { navigate({ nodeId, section: "overview" }); setInspectOpen(true); }} onSelect={onSelect} onError={observeError} />}
        </aside>
      </div>
    </>}
  </section>;
}

function DirectoryTree({ nodes, client, base, locale, current, onOpen, onError, onPage }: { nodes: CatalogueNode[]; client: CatalogueClient; base: { snapshot_id: string; scope: EvidenceScope }; locale: Locale; current: string | null; onOpen: (node: CatalogueNode) => void; onError: (error: unknown) => void; onPage: (page: CatalogueListing) => CatalogueListing }) {
  const ref = useRef<HTMLUListElement>(null);
  const [focused, setFocused] = useState(nodes[0]?.id ?? "");
  const keydown = (event: KeyboardEvent<HTMLElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const visible = Array.from(ref.current?.querySelectorAll<HTMLElement>('[role="treeitem"]') ?? []).filter((item) => item.getClientRects().length > 0);
    const position = visible.indexOf(event.currentTarget);
    const next = event.key === "Home" ? 0 : event.key === "End" ? visible.length - 1 : event.key === "ArrowDown" ? Math.min(position + 1, visible.length - 1) : Math.max(position - 1, 0);
    event.preventDefault(); visible[next]?.focus(); setFocused(visible[next]?.dataset.nodeId ?? "");
  };
  return <ul ref={ref} role="tree" aria-label={say(locale, "Catalogue directory tree", "カタログのディレクトリツリー")}>{roots.flatMap((root) => nodes.filter((node) => node.root === root)).map((node) => <TreeBranch key={node.id} node={node} level={1} client={client} base={base} locale={locale} current={current} onOpen={onOpen} onError={onError} onPage={onPage} focused={focused} focus={setFocused} keydown={keydown} />)}</ul>;
}

function TreeBranch({ node, level, client, base, locale, current, onOpen, onError, onPage, focused, focus, keydown }: { node: CatalogueNode; level: number; client: CatalogueClient; base: { snapshot_id: string; scope: EvidenceScope }; locale: Locale; current: string | null; onOpen: (node: CatalogueNode) => void; onError: (error: unknown) => void; onPage: (page: CatalogueListing) => CatalogueListing; focused: string; focus: (id: string) => void; keydown: (event: KeyboardEvent<HTMLElement>) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<CatalogueNode[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);
  const [retry, setRetry] = useState(0);
  const button = useRef<HTMLDivElement>(null);
  const page = useLoad(expanded ? JSON.stringify([base.snapshot_id, node.id, cursor, retry]) : null, async (signal) => {
    try { return onPage(await client.list({ ...base, parent_id: node.id, filters: { ...emptyFilters(), kinds: ["directory"] }, limit: 100, ...(cursor ? { cursor } : {}) }, signal)); }
    catch (error) { onError(error); throw error; }
  });
  useEffect(() => {
    if (page?.status !== "ready") return;
    setRequested(true); setItems((old) => {
      const map = new Map((cursor ? old : []).map((item) => [item.id, item]));
      page.data.items.forEach((item) => map.set(item.id, item)); return [...map.values()];
    });
  }, [page, cursor]);
  return <li role="none"><div ref={button} role="treeitem" data-node-id={node.id} aria-level={level} aria-expanded={expanded} aria-selected={current === node.id} tabIndex={focused === node.id ? 0 : -1} className={`cb-tree-item ${current === node.id ? "selected" : ""}`} onFocus={() => focus(node.id)} onClick={() => { setExpanded(true); onOpen(node); }} onKeyDown={(event) => {
    keydown(event);
    if (event.key === "ArrowRight") { event.preventDefault(); if (!expanded) setExpanded(true); else (event.currentTarget.nextElementSibling?.querySelector('[role="treeitem"]') as HTMLElement | null)?.focus(); }
    if (event.key === "ArrowLeft") { event.preventDefault(); if (expanded) setExpanded(false); else (event.currentTarget.closest('ul[role="group"]')?.previousElementSibling as HTMLElement | null)?.focus(); }
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setExpanded(true); onOpen(node); }
  }}><button className="cb-tree-toggle" tabIndex={-1} aria-label={say(locale, expanded ? "Collapse directory" : "Expand directory", expanded ? "ディレクトリを閉じる" : "ディレクトリを開く")} onClick={(event) => { event.stopPropagation(); setExpanded((value) => !value); }}>{expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button><Folder size={15} /><span>{node.kind === "root" ? localized(rootLabels[node.root], locale) : node.title[locale]}</span></div>
    {expanded && <ul role="group">{items.map((item) => <TreeBranch key={item.id} node={item} level={level + 1} client={client} base={base} locale={locale} current={current} onOpen={onOpen} onError={onError} onPage={onPage} focused={focused} focus={focus} keydown={keydown} />)}{page?.status === "loading" && <li role="none"><Loading locale={locale} /></li>}{page?.status === "error" && <li role="none"><ErrorPanel error={page.error} locale={locale} retry={() => { setCursor(null); setItems([]); setRetry((value) => value + 1); }} /></li>}{page?.status === "ready" && page.data.next_cursor && <li role="none"><button className="text-button cb-tree-more" onClick={() => setCursor(page.data.next_cursor ?? null)}>{say(locale, "More directories", "ほかのディレクトリ")} · {items.length}/{page.data.total.value ?? "?"}</button></li>}{requested && page?.status === "ready" && !items.length && <li role="none" className="cb-tree-empty">{say(locale, "No subdirectories", "サブディレクトリはありません")}</li>}</ul>}
  </li>;
}

function ObjectInspector({ value, client, base, locale, section, allowRetainedAnalysisScope, onSection, onBrowse, onOpenId, onSelect, onError }: { value: CatalogueDetails; client: CatalogueClient; base: { snapshot_id: string; scope: EvidenceScope }; locale: Locale; section: DatasetSection; allowRetainedAnalysisScope: boolean; onSection: (section: DatasetSection) => void; onBrowse: () => void; onOpenId: (id: string) => void; onSelect?: (selection: Selection) => void; onError: (error: unknown) => void }) {
  const node = value.node;
  const parent = useLoad(node.kind === "table" && node.parent_id ? node.parent_id : null, async (signal) => {
    try { return await client.open({ ...base, object_id: node.parent_id!, include_details: true }, signal); }
    catch (error) { onError(error); throw error; }
  });
  const operationTarget = parent?.status === "ready" ? parent.data : value;
  const metadata = object(operationTarget.details);
  const record = object(metadata.record);
  const sourceMetadata = object(metadata.metadata);
  const tables = array(metadata.tables ?? record.tables ?? sourceMetadata.tables ?? (sourceMetadata.table ? [sourceMetadata.table] : [])).map(object);
  const [table, setTable] = useState(() => tables.find((item) => item.object_id === node.id)?.name as string ?? "");
  const chosenTable = tables.find((item) => item.name === table) ?? tables.find((item) => item.object_id === node.id) ?? tables[0];
  const [offset, setOffset] = useState(0);
  const [retry, setRetry] = useState(0);
  const prefix = useId();
  const sourceTableOperation = array(metadata.source_operations).map(object).find((item) => typeof item.id === "string" && item.id.endsWith(".table") && object(item.availability).status === "available");
  const tableSupported = typeof chosenTable?.name === "string" && (operationTarget.node.kind === "analysis" || !!sourceTableOperation);
  const rawEdna = operationTarget.node.source_family === "edna_metabarcoding" || sourceMetadata.family === "edna_metabarcoding" || sourceTableOperation?.id === "c12.table";
  const targetReady = node.kind !== "table" || parent?.status === "ready";
  const query = useLoad(targetReady && (section === "coverage" || section === "tables" && tableSupported) ? JSON.stringify([base.snapshot_id, node.id, section, chosenTable?.name, offset, retry]) : null, async (signal) => {
    try {
      if (section === "coverage") return await client.coverage({ ...base, object_id: operationTarget.node.id, parameters: rawEdna ? { population: "raw" } : {}, limit: 100, offset }, signal);
      if (operationTarget.node.kind === "analysis") return await client.query({ ...base, ...(allowRetainedAnalysisScope && record.scope ? { scope: record.scope as EvidenceScope } : {}), operation_id: "c13.table", operation_version: "c13-v1", input_ids: [operationTarget.node.id], parameters: { table: chosenTable!.name, limit: 100, offset } }, signal);
      return await client.query({ ...base, operation_id: "c13.operation", operation_version: "c13-v1", input_ids: [operationTarget.node.id], parameters: { operation_id: sourceTableOperation!.id, operation_version: sourceTableOperation!.version, parameters: sourceTableOperation!.id === "c11.table" ? {} : { table: chosenTable!.name, ...(sourceTableOperation!.id === "c12.table" ? { population: "raw" } : {}) }, limit: 100, offset } }, signal);
    } catch (error) { onError(error); throw error; }
  });
  const changeSection = (next: DatasetSection) => { setOffset(0); onSection(next); };
  const references = [...new Set(node.related_ids)];
  return <article className="cb-object-inspector"><header><span className="small-badge">{kindLabel(node.kind, locale)}</span><h2>{node.title[locale]}</h2><code>{node.id}</code><button className="text-button" onClick={onBrowse}><Folder size={14} />{say(locale, "Browse contents", "内容を閲覧")}</button></header>
    <div className="cb-inspector-tabs" role="tablist" aria-label={say(locale, "Inspection sections", "確認するセクション")}>{sections.map((item, index) => <button key={item} id={`${prefix}-${item}-tab`} role="tab" aria-selected={section === item} aria-controls={`${prefix}-content`} tabIndex={section === item ? 0 : -1} onClick={() => changeSection(item)} onKeyDown={(event) => {
      const next = event.key === "ArrowRight" ? (index + 1) % sections.length : event.key === "ArrowLeft" ? (index - 1 + sections.length) % sections.length : event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1 : -1;
      if (next < 0) return; event.preventDefault(); changeSection(sections[next]); event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
    }}>{localized(sectionLabels[item], locale)}</button>)}</div>
    <div id={`${prefix}-content`} role="tabpanel" aria-labelledby={`${prefix}-${section}-tab`} tabIndex={0} className="cb-inspector-content">
      {section === "overview" && <><p>{node.purpose[locale]}</p><dl className="cb-facts"><div><dt>{say(locale, "Authority", "位置付け")}</dt><dd>{node.authority}</dd></div><div><dt>{say(locale, "Publication", "公開状態")}</dt><dd>{node.lifecycle.publication}</dd></div><div><dt>{say(locale, "Scientific approval", "科学的な承認")}</dt><dd>{node.lifecycle.scientific_approval}</dd></div><div><dt>{say(locale, "Availability", "利用状況")}</dt><dd>{node.availability.status}{node.availability.reason && ` · ${node.availability.reason}`}</dd></div></dl><p className="cb-qualification">{say(locale, "Published, descriptive and experimental results have different authority. Publication does not establish independent approval.", "公開済み・記述的・実験的な結果は異なる位置付けです。公開されていることは独立した承認を意味しません。")}</p><JsonDetails value={metadata.overview ?? record} title={say(locale, "Retained overview", "保持された概要")} /></>}
      {section === "tables" && <>{allowRetainedAnalysisScope && operationTarget.node.kind === "analysis" && record.scope != null && <p className="cb-qualification">{say(locale, "This table uses the publication’s retained scope. Browsing and investigation settings are unchanged.", "このテーブルでは公開結果に保持された対象範囲を使用します。閲覧条件や調査の設定は変更しません。")}</p>}{rawEdna && <p className="cb-qualification">{say(locale, "Raw retained rows include controls and unknown records; they are not an eligible scientific cohort.", "保持された生の行には対照・不明なレコードを含みます。科学的に適格なコホートを意味しません。")}</p>}{tables.length > 0 && <label className="cb-table-select">{say(locale, "Table", "テーブル")}<select value={typeof chosenTable?.name === "string" ? chosenTable.name : ""} onChange={(event) => { setTable(event.target.value); setOffset(0); }}>{tables.map((item, index) => <option key={String(item.object_id ?? index)} value={String(item.name)}>{String(item.name)} · {item.row_count == null ? say(locale, "count unknown", "行数不明") : `${String(item.row_count)} ${say(locale, "retained rows", "保持された行")}`}</option>)}</select></label>}{!tableSupported ? <Notice title={say(locale, "Table operation unavailable", "テーブルの操作を利用できません")} locale={locale}>{say(locale, "No available table operation is registered for this object.", "この項目には利用可能なテーブル操作が登録されていません。")}</Notice> : <QueryView state={query} locale={locale} offset={offset} setOffset={setOffset} retry={() => setRetry((value) => value + 1)} />}</>}
      {section === "coverage" && <>{rawEdna && <p className="cb-qualification">{say(locale, "Coverage describes the raw retained population, including controls and unknown records.", "カバレッジは対照・不明なレコードを含む、保持された生の母集団を示します。")}</p>}<QueryView state={query} locale={locale} offset={offset} setOffset={setOffset} retry={() => setRetry((value) => value + 1)} /></>}
      {section === "methods" && <><JsonDetails value={metadata.methods ?? record.method_id ?? node.descriptor} title={say(locale, "Retained methods and source semantics", "保持された手法とソースの意味")} open /><JsonDetails value={record.limitations ?? record.approval_basis} title={say(locale, "Qualifications", "条件")} /><p className="muted small">{say(locale, "Workflow descriptions do not execute an experiment.", "ワークフローの説明によって実験は実行されません。")}</p></>}
      {section === "provenance" && <><dl className="cb-facts"><div><dt>{say(locale, "Snapshot", "スナップショット")}</dt><dd><code>{base.snapshot_id}</code></dd></div></dl><JsonDetails value={base.scope} title={say(locale, "Catalogue browsing scope", "カタログ閲覧の対象範囲")} /><JsonDetails value={metadata.snapshot_binding ?? metadata.provenance ?? node.provenance} title={say(locale, "Retained provenance references", "保持された来歴の参照")} open /><p className="muted small">{say(locale, "This inspection does not infer source coverage from a preview.", "この確認ではプレビューからソースの完全性を推測しません。")}</p></>}
      {section === "related" && <><p className="cb-qualification">{say(locale, "A catalogue link alone does not verify physical identity or authorize a comparison.", "カタログのリンクだけでは、物理的な同一性や比較の許可を確認できません。")}</p>{!references.length ? <p>{say(locale, "No permitted links are retained for this object.", "この項目に保持されたアクセス可能なリンクはありません。")}</p> : <ul className="cb-related">{references.map((id) => <li key={id}><button onClick={() => onOpenId(id)}><FileText size={14} /><code>{id}</code><ChevronRight size={14} /></button></li>)}</ul>}<JsonDetails value={metadata.relationship ?? metadata.qualification} title={say(locale, "Relationship qualification", "関連性の条件")} /></>}
    </div>
    {onSelect && <footer className="cb-select-footer"><button className="button primary" onClick={() => onSelect({ type: "catalogue.selection", object_id: node.id, snapshot_id: base.snapshot_id, scope: base.scope })}>{say(locale, "Select this object", "この項目を選択")}</button><p>{say(locale, "Selection is passed to the host. It does not attach data or pin a scope.", "選択はホストに通知されます。データの追加や対象範囲の固定は行いません。")}</p></footer>}
  </article>;
}

function QueryView({ state, locale, offset, setOffset, retry }: { state: Load<ScientificResponse> | null; locale: Locale; offset: number; setOffset: (value: number) => void; retry: () => void }) {
  if (!state || state.status === "loading") return <Loading locale={locale} />;
  if (state.status === "error") return <ErrorPanel error={state.error} locale={locale} retry={retry} />;
  const value = state.data, receipt = value.receipt;
  const context = <ScientificContextLabels locale={locale} context={{ snapshotId: receipt.snapshot_id, scope: receipt.scope, availability: receipt.availability, sourceCompleteness: receipt.source_completeness, queryCompletion: receipt.query_completion }} />;
  if (receipt.availability.status !== "available") return <>{context}<Notice title={receipt.availability.status === "unknown" ? say(locale, "Availability or coverage unknown", "利用状況またはカバレッジは不明です") : say(locale, "Operation unavailable", "操作を利用できません")} locale={locale}>{receipt.availability.reason}</Notice>{value.qualifications.map((item, index) => <p key={index} className="cb-qualification">{item}</p>)}<JsonDetails value={receipt} title={say(locale, "Operation receipt", "操作の記録")} /></>;
  return <>{context}<div className="cb-query-summary"><strong>{receipt.total_rows.value ?? say(locale, "Unknown total", "総数不明")}</strong><span>{receipt.total_rows.entity} · {receipt.total_rows.denominator}</span><span>{receipt.returned_count} {say(locale, "shown", "表示")} · {receipt.source_completeness} · {receipt.query_completion}</span></div>{!value.rows.length ? <Notice title={say(locale, receipt.total_rows.value === 0 ? "No matching records" : "No preview rows available", receipt.total_rows.value === 0 ? "一致するレコードがありません" : "表示できるプレビュー行がありません")} locale={locale}>{say(locale, "Zero, missing and unknown retain their source meanings.", "ゼロ・欠損・不明はソースが定める意味を保持します。")}</Notice> : <div className="cb-table-scroll" tabIndex={0} aria-label={say(locale, "Result table", "結果テーブル")}><table><thead><tr>{value.columns.map((column) => <th key={column.key} scope="col">{column.title[locale]}{column.unit && <small>{column.unit}</small>}</th>)}</tr></thead><tbody>{value.rows.map((row, index) => <tr key={index}>{value.columns.map((column) => <td key={column.key}>{row[column.key] === null ? <span className="muted">{say(locale, "Missing", "欠損")}</span> : display(row[column.key])}</td>)}</tr>)}</tbody></table></div>}<div className="cb-pagination"><button className="button secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 100))}>{say(locale, "Previous rows", "前の行")}</button><button className="button secondary" disabled={value.next_offset === null} onClick={() => value.next_offset !== null && setOffset(value.next_offset)}>{say(locale, "Next rows", "次の行")}</button></div>{value.qualifications.map((item, index) => <p key={index} className="cb-qualification">{item}</p>)}<JsonDetails value={receipt} title={say(locale, "Operation receipt", "操作の記録")} /></>;
}

function kindLabel(kind: string, locale: Locale): string {
  const values: Record<string, readonly string[]> = { root: ["Collection", "コレクション"], directory: ["Directory", "ディレクトリ"], dataset: ["Dataset", "データセット"], table: ["Table", "テーブル"], analysis: ["Analysis", "解析"], workflow: ["Workflow", "ワークフロー"], statistic: ["Statistic", "統計"], metadata: ["Metadata", "メタデータ"], relationship: ["Relationship", "関連性"], reference: ["Reference", "参照"] };
  return values[kind] ? localized(values[kind], locale) : kind;
}
function object(value: unknown): Record<string, unknown> { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function array(value: unknown): unknown[] { return Array.isArray(value) ? value : []; }
function display(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value) ?? ""; }
function JsonDetails({ value, title, open = false }: { value: unknown; title: string; open?: boolean }) {
  if (value == null || typeof value === "object" && !Object.keys(value).length) return <p className="muted small">{title}: —</p>;
  return <details className="cb-json" open={open}><summary>{title}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
function Loading({ locale }: { locale: Locale }) { return <div className="cb-loading" role="status" aria-live="polite">{say(locale, "Checking the permitted catalogue…", "アクセス可能なカタログを確認中…")}</div>; }
function Notice({ title, children, locale }: { title: string; children?: ReactNode; locale: Locale }) { return <div className="cb-notice" role="status" lang={locale}><h3>{title}</h3><p>{children}</p></div>; }
function ErrorPanel({ error, locale, retry }: { error: unknown; locale: Locale; retry: () => void }) {
  const code = errorCode(error);
  const title = ["authentication_required", "access_denied", "not_found"].includes(code) ? say(locale, "Object or access unavailable", "項目またはアクセス権を利用できません") : code === "invalid_cursor" ? say(locale, "The catalogue view changed", "カタログのビューが変更されました") : code === "invalid_location" ? say(locale, "Catalogue link is invalid", "カタログのリンクが無効です") : say(locale, "Could not load this catalogue view", "カタログのビューを読み込めませんでした");
  const action = code === "invalid_cursor" ? say(locale, "Restart list", "一覧を最初から表示") : code === "invalid_location" ? say(locale, "Reset catalogue link", "カタログのリンクをリセット") : code === "not_found" ? say(locale, "Choose an available catalogue", "利用可能なカタログを選択") : say(locale, "Try again", "再試行");
  return <div className="cb-notice cb-error" role="alert"><h3>{title}</h3><p>{say(locale, "Check your current access or restart this view.", "現在のアクセス権を確認するか、このビューを再読み込みしてください。")}</p><button className="button secondary" onClick={retry}>{action}</button></div>;
}
