"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronDown, Database, Globe2, Info, Layers3, LockKeyhole, MessageSquare, Moon, RefreshCw, Settings2, ShieldCheck, Sun, UserRound, Wrench } from "lucide-react";
import { ApplicationShell, ShellDialog, type ShellLink } from "./application-shell";
import { ShellSplitPanels } from "./shell-panels";
import { CatalogueBrowser } from "./catalogue-browser";
import { ResearchWorkspace, createResearchSession } from "./research-workspace";
import type { ResearchRunTransport } from "./research-run-contract";
import { createExperimentClient } from "./experiment-service";
import { createExperimentExecutionClient } from "./experiment-execution-service";
import { createResearchRunTransport } from "./research-run-service";
import { createAnswerClient, createEvidenceClient } from "./research-evidence-service";
import { createCatalogueClient } from "./catalogue-service";
import { createInvestigationClient } from "./investigation-service";
import {
  capabilityReady, capabilityVisible, createRuntimeTransport, destinationFromLocation,
  destinationPath, getCapability, parseRuntimeBootstrap, routeAccessible,
  type Fetcher, type RuntimeDestination, type RuntimeState, type RuntimeTransport, type ShellDestination,
} from "./runtime";
import { defaultPresentation, PRESENTATION_STORAGE_KEY, restorePresentation, serializePresentation } from "./presentation";
import type { Locale } from "./model";

export type { ShellDestination } from "./runtime";

const labels: Record<RuntimeDestination, readonly [string, string]> = {
  research: ["Research", "リサーチ"], catalogue: ["Context Catalog", "コンテキストカタログ"], tools: ["Tools", "ツール"],
  settings: ["Settings", "設定"], administration: ["Administration", "管理"], feedback: ["Feedback", "フィードバック"], about: ["About", "概要"],
};
const primary: RuntimeDestination[] = ["research", "catalogue", "tools"];
const support: RuntimeDestination[] = ["settings", "administration", "about", "feedback"];
const icons = { research: MessageSquare, catalogue: Layers3, tools: Wrench, settings: Settings2, administration: ShieldCheck, about: Info, feedback: MessageSquare };
const canonical = (destination: ShellDestination): RuntimeDestination => destination === "admin" ? "administration" : destination;
const label = (destination: RuntimeDestination, locale: Locale) => labels[destination][locale === "en" ? 0 : 1];
const language = (locale: Locale, english: string, japanese: string) => locale === "en" ? english : japanese;

export function RuntimeApp({ initialDestination = "research", transport, researchRunTransport, fetcher }: { initialDestination?: ShellDestination; transport?: RuntimeTransport; researchRunTransport?: ResearchRunTransport; fetcher?: Fetcher }) {
  const dependency = useMemo(() => transport ?? createRuntimeTransport({ fetcher }), [transport, fetcher]);
  const serviceExperiments = useMemo(() => createExperimentClient({ fetcher }), [fetcher]);
  const serviceExecutions = useMemo(() => createExperimentExecutionClient({ fetcher }), [fetcher]);
  const serviceRuns = useMemo(() => createResearchRunTransport({ fetcher }), [fetcher]);
  const serviceAnswers = useMemo(() => createAnswerClient({ fetcher }), [fetcher]);
  const serviceEvidence = useMemo(() => createEvidenceClient({ fetcher }), [fetcher]);
  // The authenticated host explicitly supplies a same-origin session transport.
  // Preview and other callers retain the original credential-free defaults.
  const hostCatalogue = useMemo(() => fetcher ? createCatalogueClient({ fetcher }) : undefined, [fetcher]);
  const hostInvestigations = useMemo(() => fetcher ? createInvestigationClient({ fetcher }) : undefined, [fetcher]);
  const [runtime, setRuntime] = useState<RuntimeState>({ status: "loading" });
  const [destination, setDestination] = useState<RuntimeDestination>(() => canonical(initialDestination));
  const [preferences, setPreferences] = useState(defaultPresentation);
  const [presentationReady, setPresentationReady] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [accountOpen, setAccountOpen] = useState(false);
  const generation = useRef(0); const controller = useRef<AbortController | null>(null);
  const deadline = useRef<ReturnType<typeof setTimeout> | null>(null);
  const locale = preferences.locale;
  const researchSession = useRef(createResearchSession());
  const researchIdentity = useRef<string | null>(null);
  const clearResearch = () => { researchSession.current.drafts.bind(null); researchSession.current.runs.clear(); researchSession.current.experiments.clear(); researchSession.current.executions.clear(); researchIdentity.current = null; };
  const reload = useCallback(() => {
    const request = ++generation.current;
    controller.current?.abort();
    if (deadline.current !== null) clearTimeout(deadline.current);
    const nextController = new AbortController(); controller.current = nextController;
    // Revalidation removes all earlier identity/capabilities until the current
    // request succeeds. An older response cannot restore revoked navigation.
    setRuntime({ status: "loading" }); setAccountOpen(false);
    const timer = setTimeout(() => {
      if (request !== generation.current) return;
      nextController.abort(); setRuntime({ status: "error", message: "The v1 service did not respond in time", retryable: true });
    }, 10_000);
    deadline.current = timer;
    void dependency.load(nextController.signal).then((result) => {
      if (nextController.signal.aborted || request !== generation.current) return;
      if (result.status === "ready") {
        try {
          const verified = parseRuntimeBootstrap(result.bootstrap);
          const identity = `${verified.identity.id}:${verified.permission_revision}`;
          if (researchIdentity.current !== identity) researchSession.current.runs.clear();
          researchSession.current.drafts.bind({ accountId: verified.identity.id, permissionRevision: verified.permission_revision });
          researchSession.current.experiments.bind(identity); researchSession.current.executions.bind(identity);
          researchIdentity.current = identity;
          setRuntime({ status: "ready", bootstrap: verified });
        }
        catch { setRuntime({ status: "error", message: "The v1 runtime response could not be verified", retryable: true }); }
      } else { if (result.status === "unauthorized" || result.status === "forbidden") clearResearch(); setRuntime(result); }
    }).catch(() => {
      if (!nextController.signal.aborted && request === generation.current) setRuntime({ status: "error", message: "The v1 service could not be reached", retryable: true });
    }).finally(() => clearTimeout(timer));
  }, [dependency]);
  useEffect(() => {
    reload();
    const focus = () => reload();
    const visible = () => { if (document.visibilityState === "visible") reload(); };
    window.addEventListener("focus", focus); document.addEventListener("visibilitychange", visible);
    return () => { ++generation.current; controller.current?.abort(); if (deadline.current !== null) clearTimeout(deadline.current); window.removeEventListener("focus", focus); document.removeEventListener("visibilitychange", visible); };
  }, [reload]);
  useEffect(() => {
    try { setPreferences(restorePresentation(localStorage.getItem(PRESENTATION_STORAGE_KEY))); } catch { setStorageAvailable(false); }
    setPresentationReady(true);
    const locate = () => setDestination(canonical(destinationFromLocation(window.location.pathname, window.location.search, initialDestination)));
    locate(); window.addEventListener("popstate", locate); return () => window.removeEventListener("popstate", locate);
  }, [initialDestination]);
  useEffect(() => {
    if (!presentationReady) return;
    try { localStorage.setItem(PRESENTATION_STORAGE_KEY, serializePresentation(preferences)); } catch { setStorageAvailable(false); }
  }, [preferences, presentationReady]);
  useEffect(() => {
    document.documentElement.dataset.theme = preferences.theme;
    document.documentElement.lang = locale;
    document.title = `OCEAN · ${label(destination, locale)}`;
  }, [preferences.theme, locale, destination]);
  const navigate = (link: ShellLink) => {
    const next = canonical(link.id as ShellDestination);
    if (next !== destination) { window.history.pushState(null, "", destinationPath(next)); setDestination(next); }
    requestAnimationFrame(() => document.getElementById("main-content")?.focus({ preventScroll: true }));
  };
  const home = () => navigate({ id: "research", href: destinationPath("research"), label: label("research", locale) });
  const bootstrap = runtime.status === "ready" ? runtime.bootstrap : undefined;
  const runTransport = researchRunTransport ?? (bootstrap?.research_runs?.transport === "http-v1" ? serviceRuns : undefined);
  const runSource = researchRunTransport ? "development-fixture" as const : "service" as const;
  const links = (destinations: RuntimeDestination[]): ShellLink[] => destinations.filter((item) => bootstrap && capabilityVisible(bootstrap, item)).map((item) => {
    const Icon = icons[item]; return { id: item, href: destinationPath(item), label: label(item, locale), icon: <Icon size={16} /> };
  });
  const primaryLinks = links(primary), supportLinks = links(support);
  const account = bootstrap?.identity;
  const accountType = account ? language(locale, { research: "Research account", commercial: "Commercial account", internal: "Internal account" }[account.account_type], { research: "研究用アカウント", commercial: "商用アカウント", internal: "内部アカウント" }[account.account_type]) : "";
  const accountRole = account ? language(locale, { viewer: "Viewer", researcher: "Researcher", admin: "Administrator" }[account.role], { viewer: "閲覧者", researcher: "研究者", admin: "管理者" }[account.role]) : "";
  const accessibilityLabel = language(locale, "Account", "アカウント");
  const actions = <>
    {account && <button className="runtime-account" onClick={() => setAccountOpen(true)} aria-label={`${accessibilityLabel}: ${accountType}, ${accountRole}`}><UserRound size={15} /><span><strong>{accountType}</strong>{accountRole}</span><ChevronDown size={12} /></button>}
    <button className="icon-button language-button" aria-label={language(locale, "Switch language", "言語を切り替え")} onClick={() => setPreferences((current) => ({ ...current, locale: current.locale === "en" ? "ja" : "en" }))}><Globe2 size={16} /><span>{locale === "en" ? "EN" : "JA"}</span></button>
    <button className="icon-button" aria-label={language(locale, preferences.theme === "light" ? "Dark theme" : "Light theme", preferences.theme === "light" ? "ダークテーマ" : "ライトテーマ")} onClick={() => setPreferences((current) => ({ ...current, theme: current.theme === "light" ? "dark" : "light" }))}>{preferences.theme === "light" ? <Moon size={17} /> : <Sun size={17} />}</button>
    <button className="icon-button" aria-label={language(locale, "Refresh access", "アクセス権を再確認")} title={language(locale, "Refresh access", "アクセス権を再確認")} onClick={reload}><RefreshCw size={16} className={runtime.status === "loading" ? "runtime-refreshing" : undefined} /></button>
  </>;
  const sidebar = <>
    <nav aria-label={language(locale, "Destinations", "移動先")}>{primaryLinks.map((link) => <a key={link.id} className={`sidebar-link ${destination === link.id ? "selected" : ""}`} href={link.href} aria-current={destination === link.id ? "page" : undefined} onClick={(event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); navigate(link); }}>{link.icon}<span>{link.label}</span></a>)}</nav>
    <nav className="runtime-support-links" aria-label={language(locale, "Account and support", "アカウントとサポート")}>{supportLinks.map((link) => <a key={link.id} className={`sidebar-link ${destination === link.id ? "selected" : ""}`} href={link.href} aria-current={destination === link.id ? "page" : undefined} onClick={(event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); navigate(link); }}>{link.icon}<span>{link.label}</span></a>)}</nav>
  </>;
  const permitted = bootstrap && routeAccessible(bootstrap, destination);
  const content = !bootstrap ? <RuntimeBoundary state={runtime} locale={locale} retry={reload} />
    : !permitted ? <RuntimeMessage kind="denied" locale={locale} title={language(locale, "Access is restricted", "アクセスが制限されています")} />
    : destination === "research" && capabilityReady(bootstrap, destination) ? <ResearchWorkspace key={`${bootstrap.identity.id}:${bootstrap.permission_revision}`} accessKey={`${bootstrap.identity.id}:${bootstrap.permission_revision}`} locale={locale} session={researchSession.current} preferences={preferences} onPreferences={patch => setPreferences(current => ({ ...current, ...patch }))} onAccessLost={reload} client={hostInvestigations} catalogueClient={hostCatalogue} runTransport={runTransport} runSource={runSource} runSubmitEnabled={!!researchRunTransport || bootstrap.research_runs?.submit_enabled === true} answerClient={!researchRunTransport && bootstrap.research_evidence?.transport === "http-v1" ? serviceAnswers : undefined} evidenceClient={!researchRunTransport && bootstrap.research_evidence?.transport === "http-v1" ? serviceEvidence : undefined} answerSubmitEnabled={!researchRunTransport && bootstrap.research_evidence?.submit_enabled === true} experimentClient={bootstrap.research_experiments?.proposal_transport === "http-v1" ? serviceExperiments : undefined} executionClient={bootstrap.research_experiments?.execution_transport === "http-v1" ? serviceExecutions : undefined} experimentApprovalEnabled={bootstrap.research_experiments?.approval_enabled === true} canExport={bootstrap.identity.permissions.includes("data:export")} />
    : destination === "catalogue" && capabilityReady(bootstrap, destination) ? <CatalogueBrowser key={`${bootstrap.identity.id}:${bootstrap.permission_revision}`} accessKey={`${bootstrap.identity.id}:${bootstrap.permission_revision}`} locale={locale} client={hostCatalogue} onAccessLost={reload} />
    : destination === "settings" && capabilityReady(bootstrap, destination) ? <section className="runtime-page"><PageHeading destination={destination} locale={locale} /><div className="runtime-preferences"><label>{language(locale, "Language", "言語")}<select value={locale} onChange={(event) => setPreferences((current) => ({ ...current, locale: event.target.value as Locale }))}><option value="en">English</option><option value="ja">日本語</option></select></label><label>{language(locale, "Theme", "テーマ")}<select value={preferences.theme} onChange={(event) => setPreferences((current) => ({ ...current, theme: event.target.value as "light" | "dark" }))}><option value="light">{language(locale, "Light", "ライト")}</option><option value="dark">{language(locale, "Dark", "ダーク")}</option></select></label></div></section>
    : destination === "about" && capabilityReady(bootstrap, destination) ? <section className="runtime-page"><PageHeading destination={destination} locale={locale} /><dl className="runtime-account-details"><div><dt>{language(locale, "Application", "アプリケーション")}</dt><dd>OCEAN</dd></div></dl></section>
    : <section className="runtime-destination"><PageHeading destination={destination} locale={locale} />{destination === "research" || destination === "catalogue" ? <ShellSplitPanels
      locale={locale} width={preferences.workspaceWidth} open={preferences.workspaceOpen} active={preferences.mobilePane === "workspace" ? "secondary" : "primary"}
      onWidth={(workspaceWidth) => setPreferences((current) => ({ ...current, workspaceWidth }))} onOpen={(workspaceOpen) => setPreferences((current) => ({ ...current, workspaceOpen }))} onActive={(active) => setPreferences((current) => ({ ...current, mobilePane: active === "secondary" ? "workspace" : "chat" }))}
      primaryLabel={label(destination, locale)} secondaryLabel={language(locale, destination === "catalogue" ? "Inspector" : "Workspace", destination === "catalogue" ? "インスペクター" : "ワークスペース")}
      primary={<PendingDestination destination={destination} locale={locale} status={getCapability(bootstrap, destination)?.status} />}
      secondary={<RuntimeMessage kind="empty" locale={locale} title={language(locale, destination === "catalogue" ? "Select a catalogue object" : "Your research context", destination === "catalogue" ? "カタログ項目を選択" : "リサーチのコンテキスト")} />}
    /> : <><PendingDestination destination={destination} locale={locale} status={getCapability(bootstrap, destination)?.status} /></>}</section>;

  return <><ApplicationShell locale={locale} current={destination} primaryLinks={primaryLinks} onNavigate={navigate} onHome={home} actions={actions} sidebar={sidebar} dialogOpen={accountOpen}
    notice={!storageAvailable ? language(locale, "Presentation storage is unavailable. Changes last for this session.", "表示設定を保存できません。このセッションの間のみ変更が保持されます。") : undefined}>
    {content}
  </ApplicationShell>{accountOpen && account && <ShellDialog title={accessibilityLabel} locale={locale} onClose={() => setAccountOpen(false)}><dl className="runtime-account-details"><div><dt>{language(locale, "Name", "名前")}</dt><dd>{account.display_name ?? language(locale, "Not provided", "未提供")}</dd></div><div><dt>{language(locale, "Account type", "アカウント種別")}</dt><dd>{accountType}</dd></div><div><dt>{language(locale, "Role", "ロール")}</dt><dd>{accountRole}</dd></div></dl><button className="button secondary" onClick={() => { setAccountOpen(false); reload(); }}>{language(locale, "Refresh access", "アクセス権を再確認")}<RefreshCw size={15} /></button></ShellDialog>}</>;
}

function PageHeading({ destination, locale }: { destination: RuntimeDestination; locale: Locale }) {
  return <header className="runtime-page-heading"><h1>{label(destination, locale)}</h1></header>;
}

function PendingDestination({ destination, locale, status }: { destination: RuntimeDestination; locale: Locale; status?: string }) {
  return <RuntimeMessage kind="unavailable" locale={locale} title={language(locale, `${label(destination, locale)} unavailable`, `${label(destination, locale)}は利用できません`)} status={status} />;
}

function RuntimeBoundary({ state, locale, retry }: { state: RuntimeState; locale: Locale; retry: () => void }) {
  if (state.status === "ready") return null;
  const copy = state.status === "loading" ? ["Loading…", "読み込み中…"]
    : state.status === "unauthorized" ? ["Sign in required", "ログインが必要です"]
    : state.status === "forbidden" ? ["Access restricted", "アクセスが制限されています"]
    : state.status === "unavailable" ? ["OCEAN unavailable", "OCEANを利用できません"]
    : ["Connection failed", "接続できませんでした"];
  return <RuntimeMessage kind={state.status === "loading" ? "loading" : state.status === "unauthorized" || state.status === "forbidden" ? "denied" : "error"} locale={locale} title={language(locale, copy[0], copy[1])} retry={state.status === "loading" ? undefined : retry} />;
}

function RuntimeMessage({ kind, title, locale, retry, status }: { kind: "loading" | "denied" | "error" | "unavailable" | "empty"; title: string; locale: Locale; retry?: () => void; status?: string }) {
  const Icon = kind === "denied" ? LockKeyhole : kind === "empty" ? Layers3 : kind === "error" ? Info : Database;
  return <div className={`runtime-state runtime-state-${kind}`} role={kind === "error" ? "alert" : "status"} aria-busy={kind === "loading"}><Icon size={29} strokeWidth={1.4} /><h2>{title}</h2>{status && <span className="small-badge">{language(locale, "Service status", "サービスの状態")}: {status}</span>}{retry && <button className="button secondary" onClick={retry}>{language(locale, "Try again", "再試行")}<ArrowRight size={15} /></button>}</div>;
}
