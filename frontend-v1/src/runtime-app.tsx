"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, ChevronDown, Database, Globe2, Info, Layers3, LockKeyhole, MessageSquare, Moon, RefreshCw, Settings2, ShieldCheck, Sun, UserRound, Wrench } from "lucide-react";
import { ApplicationShell, ShellDialog, type ShellLink } from "./application-shell";
import { ShellSplitPanels } from "./shell-panels";
import {
  capabilityReady, capabilityVisible, createRuntimeTransport, destinationFromLocation,
  destinationPath, getCapability, parseRuntimeBootstrap, routeAccessible,
  type RuntimeDestination, type RuntimeState, type RuntimeTransport, type ShellDestination,
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

export function RuntimeApp({ initialDestination = "research", transport }: { initialDestination?: ShellDestination; transport?: RuntimeTransport }) {
  const dependency = useMemo(() => transport ?? createRuntimeTransport(), [transport]);
  const [runtime, setRuntime] = useState<RuntimeState>({ status: "loading" });
  const [destination, setDestination] = useState<RuntimeDestination>(() => canonical(initialDestination));
  const [preferences, setPreferences] = useState(defaultPresentation);
  const [presentationReady, setPresentationReady] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [accountOpen, setAccountOpen] = useState(false);
  const generation = useRef(0); const controller = useRef<AbortController | null>(null);
  const deadline = useRef<ReturnType<typeof setTimeout> | null>(null);
  const locale = preferences.locale;
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
        try { setRuntime({ status: "ready", bootstrap: parseRuntimeBootstrap(result.bootstrap) }); }
        catch { setRuntime({ status: "error", message: "The v1 runtime response could not be verified", retryable: true }); }
      } else setRuntime(result);
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
    window.history.pushState(null, "", destinationPath(next)); setDestination(next);
    requestAnimationFrame(() => document.getElementById("main-content")?.focus({ preventScroll: true }));
  };
  const home = () => navigate({ id: "research", href: destinationPath("research"), label: label("research", locale) });
  const bootstrap = runtime.status === "ready" ? runtime.bootstrap : undefined;
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
    <div className="sidebar-section-label">OCEAN / v1</div>
    <nav aria-label={language(locale, "Destinations", "移動先")}>{primaryLinks.map((link) => <a key={link.id} className={`sidebar-link ${destination === link.id ? "selected" : ""}`} href={link.href} aria-current={destination === link.id ? "page" : undefined} onClick={(event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); navigate(link); }}>{link.icon}<span>{link.label}</span></a>)}</nav>
    <div className="runtime-sidebar-context"><LockKeyhole size={15} /><p>{language(locale, "Your access is checked by the v1 service.", "アクセス権はv1サービスで確認されます。")}</p></div>
    <nav className="runtime-support-links" aria-label={language(locale, "Account and support", "アカウントとサポート")}>{supportLinks.map((link) => <a key={link.id} className={`sidebar-link ${destination === link.id ? "selected" : ""}`} href={link.href} aria-current={destination === link.id ? "page" : undefined} onClick={(event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); navigate(link); }}>{link.icon}<span>{link.label}</span></a>)}</nav>
  </>;
  const permitted = bootstrap && routeAccessible(bootstrap, destination);
  const content = !bootstrap ? <RuntimeBoundary state={runtime} locale={locale} retry={reload} />
    : !permitted ? <RuntimeMessage kind="denied" locale={locale} title={language(locale, "Access is restricted", "アクセスが制限されています")} detail={language(locale, "Your current account cannot open this destination.", "現在のアカウントではこの移動先を開けません。")} />
    : destination === "settings" && capabilityReady(bootstrap, destination) ? <section className="runtime-page"><PageHeading destination={destination} locale={locale} /><p className="runtime-intro">{language(locale, "Choose how this workspace looks on this device.", "この端末でのワークスペースの表示を選択できます。")}</p><div className="runtime-preferences"><label>{language(locale, "Language", "言語")}<select value={locale} onChange={(event) => setPreferences((current) => ({ ...current, locale: event.target.value as Locale }))}><option value="en">English</option><option value="ja">日本語</option></select></label><label>{language(locale, "Theme", "テーマ")}<select value={preferences.theme} onChange={(event) => setPreferences((current) => ({ ...current, theme: event.target.value as "light" | "dark" }))}><option value="light">{language(locale, "Light", "ライト")}</option><option value="dark">{language(locale, "Dark", "ダーク")}</option></select></label></div><p className="muted small">{language(locale, "These preferences do not change your account, permissions or scientific scope.", "表示設定によってアカウント・権限・科学的な対象範囲は変わりません。")}</p></section>
    : destination === "about" && capabilityReady(bootstrap, destination) ? <section className="runtime-page"><PageHeading destination={destination} locale={locale} /><p className="runtime-intro">{language(locale, "OCEAN brings marine data, context and evidence into a research workspace.", "OCEANは海洋データ・コンテキスト・根拠をリサーチワークスペースにまとめます。")}</p><div className="runtime-info-grid"><article><Layers3 size={22} /><h2>{language(locale, "Context before conclusions", "結論の前にコンテキストを")}</h2><p>{language(locale, "Source scope, coverage and qualifications stay with the information they describe.", "ソースの対象範囲・カバレッジ・条件を、それぞれの情報とともに示します。")}</p></article><article><ShieldCheck size={22} /><h2>{language(locale, "Current access", "現在のアクセス権")}</h2><p>{language(locale, "Available destinations follow the permissions supplied by the v1 service.", "利用できる移動先はv1サービスが提供する権限に従います。")}</p></article></div></section>
    : <section className="runtime-destination"><PageHeading destination={destination} locale={locale} />{destination === "research" || destination === "catalogue" ? <ShellSplitPanels
      locale={locale} width={preferences.workspaceWidth} open={preferences.workspaceOpen} active={preferences.mobilePane === "workspace" ? "secondary" : "primary"}
      onWidth={(workspaceWidth) => setPreferences((current) => ({ ...current, workspaceWidth }))} onOpen={(workspaceOpen) => setPreferences((current) => ({ ...current, workspaceOpen }))} onActive={(active) => setPreferences((current) => ({ ...current, mobilePane: active === "secondary" ? "workspace" : "chat" }))}
      primaryLabel={label(destination, locale)} secondaryLabel={language(locale, destination === "catalogue" ? "Inspector" : "Workspace", destination === "catalogue" ? "インスペクター" : "ワークスペース")}
      primary={<PendingDestination destination={destination} locale={locale} status={getCapability(bootstrap, destination)?.status} />}
      secondary={<RuntimeMessage kind="empty" locale={locale} title={language(locale, destination === "catalogue" ? "Select a catalogue object" : "Your research context", destination === "catalogue" ? "カタログ項目を選択" : "リサーチのコンテキスト")} detail={language(locale, destination === "catalogue" ? "Object details will appear when catalogue browsing is connected." : "Context, results and evidence will appear when research services are connected.", destination === "catalogue" ? "カタログ閲覧サービスの接続後に、項目の詳細を表示します。" : "リサーチサービスの接続後に、コンテキスト・結果・根拠を表示します。")} />}
    /> : <><PendingDestination destination={destination} locale={locale} status={getCapability(bootstrap, destination)?.status} />{destination === "tools" && <div className="runtime-tool-groups">{[["Data", "データ"], ["Explore", "探索"], ["Provenance", "来歴"], ["Evaluation", "評価"]].map(([english, japanese]) => <article key={english}><Database size={18} /><h2>{language(locale, english, japanese)}</h2><span className="small-badge">{language(locale, "Unavailable", "利用できません")}</span></article>)}</div>}</>}</section>;

  return <><ApplicationShell locale={locale} current={destination} primaryLinks={primaryLinks} onNavigate={navigate} onHome={home} actions={actions} sidebar={sidebar} dialogOpen={accountOpen}
    notice={!storageAvailable ? language(locale, "Presentation storage is unavailable. Changes last for this session.", "表示設定を保存できません。このセッションの間のみ変更が保持されます。") : undefined}>
    {content}
  </ApplicationShell>{accountOpen && account && <ShellDialog title={accessibilityLabel} locale={locale} onClose={() => setAccountOpen(false)}><p className="muted small">{language(locale, "Identity supplied by the v1 service", "v1サービスが提供したアカウント情報")}</p><dl className="runtime-account-details"><div><dt>{language(locale, "Name", "名前")}</dt><dd>{account.display_name ?? language(locale, "Not provided", "未提供")}</dd></div><div><dt>{language(locale, "Account type", "アカウント種別")}</dt><dd>{accountType}</dd></div><div><dt>{language(locale, "Role", "ロール")}</dt><dd>{accountRole}</dd></div></dl><button className="button secondary" onClick={() => { setAccountOpen(false); reload(); }}>{language(locale, "Refresh access", "アクセス権を再確認")}<RefreshCw size={15} /></button></ShellDialog>}</>;
}

function PageHeading({ destination, locale }: { destination: RuntimeDestination; locale: Locale }) {
  return <header className="runtime-page-heading"><div className="eyebrow">OCEAN / v1</div><h1>{label(destination, locale)}</h1></header>;
}

function PendingDestination({ destination, locale, status }: { destination: RuntimeDestination; locale: Locale; status?: string }) {
  return <RuntimeMessage kind="unavailable" locale={locale} title={language(locale, `${label(destination, locale)} is not available yet`, `${label(destination, locale)}はまだ利用できません`)} detail={language(locale, "This destination will open when its v1 service is connected. Your presentation preferences are kept.", "v1サービスの接続後に、この移動先を利用できます。表示設定は保持されています。")} status={status} />;
}

function RuntimeBoundary({ state, locale, retry }: { state: RuntimeState; locale: Locale; retry: () => void }) {
  if (state.status === "ready") return null;
  const copy = state.status === "loading" ? ["Connecting to OCEAN", "OCEANに接続中", "Checking your current account and available services.", "現在のアカウントと利用できるサービスを確認しています。"]
    : state.status === "unauthorized" ? ["Sign in to continue", "続行するにはログインが必要です", "A valid v1 sign-in is required. Refresh after signing in through your configured identity provider.", "v1への有効なログインが必要です。設定された認証サービスでログインした後に再確認してください。"]
    : state.status === "forbidden" ? ["Access is restricted", "アクセスが制限されています", "The v1 service has not granted this account access.", "このアカウントにはv1サービスのアクセス権が付与されていません。"]
    : state.status === "unavailable" ? ["OCEAN is unavailable", "OCEANを利用できません", "The v1 service is not available. You can check again without changing your preferences.", "v1サービスを利用できません。表示設定を変更せずに再確認できます。"]
    : ["Could not connect", "接続できませんでした", "The v1 response could not be loaded or verified. Please try again.", "v1の応答を読み込めないか、確認できませんでした。再試行してください。"];
  return <RuntimeMessage kind={state.status === "loading" ? "loading" : state.status === "unauthorized" || state.status === "forbidden" ? "denied" : "error"} locale={locale} title={language(locale, copy[0], copy[1])} detail={language(locale, copy[2], copy[3])} retry={state.status === "loading" ? undefined : retry} />;
}

function RuntimeMessage({ kind, title, detail, locale, retry, status }: { kind: "loading" | "denied" | "error" | "unavailable" | "empty"; title: string; detail: string; locale: Locale; retry?: () => void; status?: string }) {
  const Icon = kind === "denied" ? LockKeyhole : kind === "empty" ? Layers3 : kind === "error" ? Info : Database;
  return <div className={`runtime-state runtime-state-${kind}`} role={kind === "error" ? "alert" : "status"} aria-busy={kind === "loading"}><Icon size={29} strokeWidth={1.4} /><h2>{title}</h2><p>{detail}</p>{status && <span className="small-badge">{language(locale, "Service status", "サービスの状態")}: {status}</span>}{retry && <button className="button secondary" onClick={retry}>{language(locale, "Try again", "再試行")}<ArrowRight size={15} /></button>}</div>;
}
