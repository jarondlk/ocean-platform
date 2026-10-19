"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronRight, Layers3, MessageSquare, Plus } from "lucide-react";
import { CatalogueBrowser } from "./catalogue-browser";
import { createCatalogueClient, defaultCatalogueScope, type CatalogueClient, type EvidenceScope } from "./catalogue-service";
import type { CatalogueSelectionEvent } from "./catalogue-browser-state";
import { createInvestigationClient, executeInvestigationMutation, type InvestigationMutationIntent, type Investigation, type Conversation, type InvestigationContext, type InvestigationClient, type ContextReference } from "./investigation-service";
import { ResearchDraftStore, parseResearchLocation, researchLocationUrl, updateResearchLocation, type ResearchLocation } from "./research-state";
import { ResearchActivity, ResearchResults, ResearchEvidence } from "./research-activity";
import { ResearchHistoryScheduler } from "./research-history-scheduler";
import { executeRunMutation, freezeRunContext, isRunActive, mergeRunEvents, mergeRunSnapshot, researchRunAddress, sameRunBinding, type ResearchRun, type ResearchRunTransport, type RunEvidence, type RunContextBinding, type RunMutationIntent } from "./research-run-contract";
import { ShellSplitPanels, ShellTabs } from "./shell-panels";
import type { PresentationPreferences } from "./presentation";
import type { Locale } from "./model";
import "./research-workspace.css";

const say = (locale: Locale, en: string, ja: string) => locale === "en" ? en : ja;
const families = ["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"] as const;
const familyNames = ["CTD", "Metagenome", "SST", "eDNA"];
type Active = { investigation: Investigation; context: InvestigationContext };
/** Kept by the shell across ordinary navigation/revalidation, never persisted. */
export type ResearchSession = { drafts: ResearchDraftStore; runs: Map<string, ResearchRun[]> };
export function createResearchSession(): ResearchSession { return { drafts: new ResearchDraftStore(), runs: new Map() }; }
export type ResearchWorkspaceProps = {
  locale: Locale; accessKey: string; session: ResearchSession;
  preferences: PresentationPreferences; onPreferences: (patch: Partial<PresentationPreferences>) => void;
  onAccessLost: () => void; client?: InvestigationClient; catalogueClient?: CatalogueClient;
  /** Production uses verified runtime discovery; development may explicitly inject a fixture. */
  runTransport?: ResearchRunTransport;
  runSource?: "service" | "development-fixture";
  runSubmitEnabled?: boolean;
};
function currentLocation(): ResearchLocation { return parseResearchLocation(window.location.search); }
function code(error: unknown): number { return error !== null && typeof error === "object" && "status_code" in error && typeof error.status_code === "number" && error.status_code >= 400 && error.status_code <= 599 ? error.status_code : 503; }
class ContextReviewRequired extends Error {}
function requestKey() { return crypto.randomUUID(); }
function refKey(value: ContextReference) { return `${value.kind}:${value.id}:${value.snapshot_id}`; }

export function ResearchWorkspace({ locale, accessKey, session, preferences, onPreferences, onAccessLost, client: suppliedClient, catalogueClient: suppliedCatalogue, runTransport, runSource = "development-fixture", runSubmitEnabled = true }: ResearchWorkspaceProps) {
  const client = useMemo(() => suppliedClient ?? createInvestigationClient(), [suppliedClient]);
  const catalogue = useMemo(() => suppliedCatalogue ?? createCatalogueClient(), [suppliedCatalogue]);
  const [location, setLocation] = useState<ResearchLocation>(() => parseResearchLocation(""));
  const [located, setLocated] = useState(false);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [investigationPages, setInvestigationPages] = useState(1);
  const [conversationPages, setConversationPages] = useState(1);
  const [nextInvestigation, setNextInvestigation] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [nextConversation, setNextConversation] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [active, setActive] = useState<Active | null>(null);
  const [catalogueStatus, setCatalogueStatus] = useState<"loading" | "ready" | "error">("loading");
  const [snapshots, setSnapshots] = useState<{ snapshot_id: string; label: { en: string; ja: string } }[]>([]);
  const [selected, setSelected] = useState<CatalogueSelectionEvent | null>(null);
  const [browse, setBrowse] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(true);
  const [newName, setNewName] = useState(""); const [newSnapshot, setNewSnapshot] = useState("");
  const [conversationName, setConversationName] = useState("");
  const [rename, setRename] = useState(""); const [chatRename, setChatRename] = useState("");
  const [refreshName, setRefreshName] = useState(""); const [refreshSnapshot, setRefreshSnapshot] = useState("");
  const [draft, setDraft] = useState(""); const [runs, setRuns] = useState<ResearchRun[]>([]);
  const [evidence, setEvidence] = useState<RunEvidence | null>(null);
  const [error, setError] = useState<number | null>(null); const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false); const [checking, setChecking] = useState(false);
  const [tick, setTick] = useState(0); const [listTick, setListTick] = useState(0);
  const [pending, setPending] = useState<InvestigationMutationIntent | null>(null);
  const [pendingRun, setPendingRun] = useState<RunMutationIntent | null>(null);
  const [historyVerified, setHistoryVerified] = useState(false);
  const [historyPages, setHistoryPages] = useState(1);
  const [nextRunPage, setNextRunPage] = useState<string | null>(null);
  const [conflict, setConflict] = useState<InvestigationMutationIntent | null>(null);
  const mounted = useRef(false); const locationRef = useRef(location); locationRef.current = location;
  const activeRef = useRef(active); activeRef.current = active;
  const key = `${accessKey}:${location.investigationId}:${location.conversationId}`;
  const selectionEpoch = useRef(0);
  const operation = useRef<symbol | null>(null);
  const guard = useRef(key); guard.current = `${key}:${selectionEpoch.current}`;
  const selectionAbort = useRef<AbortController | null>(null);
  const mutationAbort = useRef<AbortController | null>(null);
  const runAbort = useRef<AbortController | null>(null);
  const historyScheduler = useRef<ResearchHistoryScheduler | null>(null);
  const historyEpoch = useRef(0);
  const metadataSource = useRef<{ investigationId: string; name: string; conversationId: string | null; conversationName: string } | null>(null);
  const blocked = busy || pending !== null || pendingRun !== null;
  const fail = useCallback((failure: unknown) => {
    const status = code(failure); setError(status);
    if (status === 401 || status === 403) {
      ++selectionEpoch.current; guard.current = `denied:${selectionEpoch.current}`;
      selectionAbort.current?.abort(); mutationAbort.current?.abort(); runAbort.current?.abort(); historyScheduler.current?.dispose(); ++historyEpoch.current;
      session.drafts.clear(); session.runs.clear(); setActive(null); setConversations([]); setInvestigations([]); setConversation(null); setDraft(""); setRuns([]); setEvidence(null); onAccessLost();
    }
  }, [onAccessLost, session]);
  const transition = useCallback((next: ResearchLocation) => {
    const previous = locationRef.current;
    const changed = previous.investigationId !== next.investigationId || previous.conversationId !== next.conversationId;
    if (changed) {
      if (window.matchMedia("(max-width: 950px)").matches) setNavigationOpen(false);
      ++selectionEpoch.current; guard.current = `${accessKey}:${next.investigationId}:${next.conversationId}:${selectionEpoch.current}`;
      selectionAbort.current?.abort(); mutationAbort.current?.abort(); runAbort.current?.abort(); historyScheduler.current?.dispose(); ++historyEpoch.current; operation.current = null; setBusy(false); setHistoryVerified(false); setHistoryPages(1); setNextRunPage(null); setRuns([]);
      if (previous.investigationId !== next.investigationId) { setActive(null); setConversations([]); setConversationPages(1); setBrowse(false); }
      setConversation(null); setSelected(null); setEvidence(null);
    }
    setError(null); setLocated(true); locationRef.current = next; setLocation(next);
  }, [accessKey]);
  const navigate = useCallback((patch: Partial<ResearchLocation>, replace = false) => {
    const next = updateResearchLocation(locationRef.current, patch);
    window.history[replace ? "replaceState" : "pushState"](null, "", researchLocationUrl(next)); transition(next);
  }, [transition]);
  useEffect(() => {
    mounted.current = true;
    const restore = () => { try { transition(currentLocation()); } catch {
      ++selectionEpoch.current; guard.current = `invalid:${selectionEpoch.current}`;
      selectionAbort.current?.abort(); mutationAbort.current?.abort(); runAbort.current?.abort(); historyScheduler.current?.dispose(); ++historyEpoch.current; operation.current = null;
      setError(422); setLocated(false); setActive(null); setConversation(null); setConversations([]); setDraft(""); setRuns([]); setEvidence(null); setPending(null); setSelected(null); setBusy(false);
    } };
    const narrow = window.matchMedia("(max-width: 950px)");
    const resizeNavigation = () => setNavigationOpen(!narrow.matches);
    restore(); resizeNavigation(); narrow.addEventListener("change", resizeNavigation); window.addEventListener("popstate", restore);
    const refresh = () => { if (document.visibilityState !== "hidden") { setTick(v => v + 1); setListTick(v => v + 1); historyScheduler.current?.request(); } };
    const timer = setInterval(refresh, 10_000); window.addEventListener("focus", refresh);
    return () => { mounted.current = false; selectionAbort.current?.abort(); mutationAbort.current?.abort(); runAbort.current?.abort(); historyScheduler.current?.dispose(); ++historyEpoch.current; clearInterval(timer); narrow.removeEventListener("change", resizeNavigation); window.removeEventListener("popstate", restore); window.removeEventListener("focus", refresh); };
  }, [transition]);
  useEffect(() => {
    setCatalogueStatus("loading");
    const abort = new AbortController(); const timer = setTimeout(() => { abort.abort(); setInvestigations([]); setSnapshots([]); setCatalogueStatus("error"); setError(503); }, 8_000);
    void Promise.all([loadInvestigationPages(client, investigationPages, abort.signal), catalogue.snapshots({ scope: defaultCatalogueScope(), limit: 500 }, abort.signal)]).then(([page, available]) => {
      if (abort.signal.aborted) return; setInvestigations(page.items); setNextInvestigation(page.next_after_id); setSnapshots(available.snapshots); setCatalogueStatus("ready");
      setNewSnapshot(current => available.snapshots.some(item => item.snapshot_id === current) ? current : "");
      setRefreshSnapshot(current => available.snapshots.some(item => item.snapshot_id === current) ? current : "");
    }).catch(e => { if (!abort.signal.aborted) { setInvestigations([]); setSnapshots([]); setCatalogueStatus("error"); fail(e); } }).finally(() => clearTimeout(timer));
    return () => { abort.abort(); clearTimeout(timer); };
  }, [client, catalogue, listTick, accessKey, fail, investigationPages]);
  useEffect(() => {
    if (!located) return;
    selectionAbort.current?.abort(); const abort = new AbortController(); selectionAbort.current = abort;
    const timer = setTimeout(() => { abort.abort(); setChecking(false); setError(503); setActive(null); setConversation(null); setConversations([]); setRuns([]); setEvidence(null); }, 8_000);
    const selectedId = location.investigationId;
    if (!selectedId) { clearTimeout(timer); setActive(null); setConversations([]); setConversation(null); setChecking(false); return; }
    setChecking(true); setError(null);
    if (activeRef.current?.investigation.id !== selectedId) { setActive(null); setConversations([]); setConversation(null); setBrowse(false); setEvidence(null); }
    void Promise.all([client.get({ investigation_id: selectedId }, abort.signal), loadConversationPages(client, selectedId, conversationPages, abort.signal), location.conversationId ? client.getConversation({ investigation_id: selectedId, conversation_id: location.conversationId }, abort.signal) : Promise.resolve(null)]).then(([bundle, chats, chat]) => {
      if (abort.signal.aborted) return;
      if (activeRef.current?.investigation.id === selectedId && activeRef.current.context.id !== bundle.context.id) setNotice(say(locale, "Shared context changed. Future submissions will use this revision; existing activity keeps its original context.", "共有コンテキストが更新されました。次の送信にはこの版を使い、既存の実行は元のコンテキストを保持します。"));
      setActive(bundle); setConversations(chats.items); setNextConversation(chats.next_after_id); setConversation(chat?.conversation ?? null);
      if (chat && runSource !== "service") setRuns(session.runs.get(`${selectedId}:${chat.conversation.id}`) ?? []);
      const previous = metadataSource.current;
      setRename(current => previous?.investigationId === selectedId && current !== previous.name ? current : bundle.investigation.name);
      setChatRename(current => previous?.conversationId === (chat?.conversation.id ?? null) && current !== previous?.conversationName ? current : (chat?.conversation.name ?? ""));
      metadataSource.current = { investigationId: selectedId, name: bundle.investigation.name, conversationId: chat?.conversation.id ?? null, conversationName: chat?.conversation.name ?? "" };
    }).catch(e => { if (!abort.signal.aborted) { setActive(null); setConversation(null); setConversations([]); setRuns([]); setEvidence(null); fail(e); } }).finally(() => { clearTimeout(timer); if (!abort.signal.aborted) setChecking(false); });
    return () => { abort.abort(); clearTimeout(timer); };
  }, [client, accessKey, located, location.investigationId, location.conversationId, tick, fail, locale, conversationPages, session, runSource]);
  useEffect(() => { setSelected(null); }, [active?.context.id]);
  useEffect(() => {
    setEvidence(null); setConflict(null); setNotice("");
    if (!located) return;
    if (location.investigationId && location.conversationId) {
      setDraft(session.drafts.readDraft(location.investigationId, location.conversationId)); setRuns(runSource === "service" ? [] : session.runs.get(`${location.investigationId}:${location.conversationId}`) ?? []);
    } else { setDraft(""); setRuns([]); }
    setPending(session.drafts.pendingMutation(location.investigationId ?? "new"));
    setPendingRun(location.investigationId && location.conversationId ? session.drafts.pendingRunMutation(`${location.investigationId}:${location.conversationId}`) : null);
  }, [key, session, located, location.investigationId, location.conversationId, runSource]);
  useEffect(() => {
    if (!located || !location.investigationId || !location.conversationId || runSource !== "service" || !runTransport?.list) { setHistoryVerified(runSource !== "service"); return; }
    const mine = guard.current;
    const address = { investigation_id: location.investigationId, conversation_id: location.conversationId };
    const slot = `${address.investigation_id}:${address.conversation_id}`;
    const current = () => mounted.current && guard.current === mine;
    const scheduler = new ResearchHistoryScheduler({
      run: async signal => {
        const epoch = ++historyEpoch.current;
        const snapshots: ResearchRun[] = []; let cursor: string | null = null; const cursors = new Set<string>();
        for (let pageIndex = 0; pageIndex < historyPages; pageIndex++) {
          const page = await runTransport.list!({ ...address, limit: 25, cursor }, signal);
          for (const item of page.items) { if (snapshots.some(prior => prior.id === item.id)) throw new Error("Repeated run page"); snapshots.push(item); }
          cursor = page.next_cursor; if (cursor === null) break;
          if (cursors.has(cursor)) throw new Error("Repeated run cursor"); cursors.add(cursor);
        }
        const cached = session.runs.get(slot) ?? [], merged: ResearchRun[] = [];
        for (const snapshot of snapshots) {
          let item = mergeRunSnapshot(cached.find(prior => prior.id === snapshot.id), snapshot);
          for (let pageIndex = 0; pageIndex < 20 && item.event_cursor < (item.latest_event_cursor ?? item.event_cursor); pageIndex++) {
            item = mergeRunEvents(item, await runTransport.events({ ...researchRunAddress(item), after_cursor: item.event_cursor, limit: 100 }, signal));
          }
          merged.push(item);
        }
        if (signal.aborted || !current() || historyEpoch.current !== epoch) return;
        session.runs.set(slot, merged); setRuns(merged); setNextRunPage(cursor); setHistoryVerified(true);
      },
      onFailure: error => { if (current()) { setRuns([]); setHistoryVerified(false); fail(error); } },
      onTimeout: () => { if (current()) { setRuns([]); setHistoryVerified(false); setError(503); } },
    });
    historyScheduler.current = scheduler;
    if (operation.current !== null) scheduler.pause();
    scheduler.request();
    return () => { scheduler.dispose(); ++historyEpoch.current; if (historyScheduler.current === scheduler) historyScheduler.current = null; };
  }, [located, location.investigationId, location.conversationId, runTransport, runSource, historyPages, session, accessKey, fail]);
  useEffect(() => {
    if (runSource !== "service" || !runs.some(run => isRunActive(run.status))) return;
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") historyScheduler.current?.request(); }, 2000);
    return () => clearInterval(timer);
  }, [runSource, runs]);
  const mutate = async (intent: InvestigationMutationIntent) => {
    if (operation.current !== null) return false; const mine = guard.current; const slot = locationRef.current.investigationId ?? "new";
    const original = session.drafts.pendingMutation(slot);
    if (original && JSON.stringify(original) !== JSON.stringify(intent)) { setPending(original); setNotice(say(locale, "Recover the pending change before making another change here.", "この場所で別の変更をする前に、保留中の変更を復旧してください。")); return false; }
    const token = Symbol(); operation.current = token; setBusy(true); setError(null); setConflict(null);
    historyScheduler.current?.pause(); ++historyEpoch.current;
    const abort = new AbortController(); mutationAbort.current?.abort(); mutationAbort.current = abort;
    const timer = setTimeout(() => abort.abort(), 15_000);
    try {
      session.drafts.rememberMutation(slot, intent); setPending(intent);
      const result = await executeInvestigationMutation(client, intent, abort.signal);
      const fresh = "investigation" in result ? await client.get({ investigation_id: result.investigation.id }, abort.signal) : null;
      if (!mounted.current || guard.current !== mine) return false;
      session.drafts.forgetMutation(slot); setPending(null); setListTick(v => v + 1);
      if ("investigation" in result && "context" in result) {
        if (fresh) setActive(fresh);
        if (intent.method === "create" || intent.method === "refresh") navigate({ investigationId: result.investigation.id, conversationId: null, workspaceTab: "context" });
      }
      if ("conversation" in result) { setConversationName(""); navigate({ conversationId: result.conversation.id }); }
      setTick(v => v + 1); setNotice(say(locale, "Saved to this private investigation; current shared context is refreshed.", "この非公開の調査に保存し、現在の共有コンテキストを確認しました。")); return true;
    } catch (e) {
      if (!mounted.current || guard.current !== mine) return false;
      if (code(e) < 500) { session.drafts.forgetMutation(slot); setPending(null); }
      if (code(e) === 409) { setConflict(intent); setTick(v => v + 1); }
      fail(e); return false;
    } finally { clearTimeout(timer); if (operation.current === token) { operation.current = null; if (mounted.current) { setBusy(false); historyScheduler.current?.resume(); } } }
  };
  const changeContext = (change: Parameters<InvestigationClient["changeContext"]>[0]["change"], revision = active?.context.id) => {
    if (!active || !revision) return Promise.resolve(false); return mutate({ method: "changeContext", request: { investigation_id: active.investigation.id, expected_revision_id: revision, idempotency_key: requestKey(), change } });
  };
  const reference = selected ? { kind: "catalogue" as const, id: selected.object_id, snapshot_id: selected.snapshot_id } : null;
  const unresolved = active?.context.resolution.some(item => item.status !== "available") ?? false;
  const archived = active?.investigation.status !== "active";
  const saveRun = (run: ResearchRun) => {
    const previous = session.runs.get(`${run.context.binding.investigation_id}:${run.context.binding.conversation_id}`) ?? [];
    const updated = mergeRunSnapshot(previous.find(item => item.id === run.id), run);
    const next = previous.some(item => item.id === run.id) ? previous.map(item => item.id === run.id ? updated : item) : [...previous, updated];
    session.runs.set(`${run.context.binding.investigation_id}:${run.context.binding.conversation_id}`, next); setRuns(next);
  };
  const runAction = async (execute: (signal: AbortSignal) => Promise<ResearchRun>, expected?: ResearchRun | RunContextBinding, intent?: RunMutationIntent) => {
    if (!runTransport || operation.current !== null) return; const mine = guard.current; const token = Symbol(); operation.current = token; setBusy(true); setError(null);
    const slot = location.investigationId && location.conversationId ? `${location.investigationId}:${location.conversationId}` : null;
    historyScheduler.current?.pause(); ++historyEpoch.current;
    const abort = new AbortController(); runAbort.current = abort; const timer = setTimeout(() => abort.abort(), 15_000);
    try {
      if (intent && slot) { session.drafts.rememberRunMutation(slot, intent); setPendingRun(intent); }
      const run = await execute(abort.signal); if (!mounted.current || guard.current !== mine) return;
      if (abort.signal.aborted) throw new DOMException("Cancelled", "AbortError");
      if (run.context.binding.investigation_id !== location.investigationId || run.context.binding.conversation_id !== location.conversationId || (expected && !sameRunBinding("context" in expected ? expected.context.binding : expected, run.context.binding))) throw new Error("Run binding mismatch");
      saveRun(run);
      if (intent && slot) { session.drafts.forgetRunMutation(slot); setPendingRun(null); }
      historyScheduler.current?.request();
    } catch (e) { if (mounted.current && guard.current === mine) {
      if (intent && slot && (e instanceof ContextReviewRequired || code(e) < 500)) { session.drafts.forgetRunMutation(slot); setPendingRun(null); }
      if (e instanceof ContextReviewRequired) setNotice(say(locale, "Shared context changed before submission. Review it and submit again.", "送信の前に共有コンテキストが変わりました。確認してからもう一度送信してください。")); else fail(e);
    } }
    finally { clearTimeout(timer); if (operation.current === token) { operation.current = null; if (mounted.current) { setBusy(false); historyScheduler.current?.resume(); } } }
  };
  const submit = () => {
    if (!runTransport || !runSubmitEnabled || !active || !conversation || unresolved || checking || archived || pending || pendingRun || (runSource === "service" && !historyVerified) || !draft.trim()) return;
    const binding = { investigation_id: active.investigation.id, conversation_id: conversation.id, revision_id: active.context.id, snapshot_id: active.context.snapshot_id, payload_sha256: active.context.payload_sha256 };
    const context = freezeRunContext({ binding, scope: active.context.scope, attachments: active.context.attachments, pins: active.context.pins });
    const intent: RunMutationIntent = { method: "submit", request: { context, question: draft, idempotency_key: requestKey() } };
    void runAction(async signal => {
      const [fresh, chat] = await Promise.all([client.get({ investigation_id: binding.investigation_id }, signal), client.getConversation({ investigation_id: binding.investigation_id, conversation_id: binding.conversation_id }, signal)]);
      if (!mounted.current || signal.aborted) throw new DOMException("Cancelled", "AbortError");
      if (fresh.investigation.status !== "active" || fresh.context.resolution.some(item => item.status !== "available") || chat.conversation.id !== binding.conversation_id || !sameRunBinding(binding, { ...binding, revision_id: fresh.context.id, snapshot_id: fresh.context.snapshot_id, payload_sha256: fresh.context.payload_sha256 })) {
        setActive(fresh); throw new ContextReviewRequired();
      }
      return executeRunMutation(runTransport, intent, signal);
    }, binding, intent);
  };
  const mutateRun = (intent: RunMutationIntent) => runTransport && void runAction(signal => executeRunMutation(runTransport, intent, signal), intent.method === "submit" ? intent.request.context.binding : intent.binding, intent);
  const openEvidence = (value: RunEvidence) => { setEvidence(value); navigate({ workspaceTab: "evidence", mobilePane: "workspace" }); onPreferences({ workspaceOpen: true }); };
  const summary = active && <div className="rw-context-summary"><strong>{say(locale, "Context for the next question", "次の質問のコンテキスト")}</strong><span>{families.filter(family => active.context.scope.sources[family].enabled).map(family => familyNames[families.indexOf(family)]).join(" · ") || say(locale, "No enabled sources", "有効なソースなし")}</span><span>{active.context.attachments.length} {say(locale, "attachments", "追加項目")} · {active.context.pins.length} {say(locale, "pinned restrictions", "固定した制限")}</span><details><summary>{say(locale, "Snapshot and revision", "スナップショットと版")}</summary><dl><dt>{say(locale, "Snapshot", "スナップショット")}</dt><dd>{active.context.snapshot_id}</dd><dt>{say(locale, "Revision", "版")}</dt><dd>{active.context.id}</dd><dt>SHA256</dt><dd>{active.context.payload_sha256}</dd></dl></details>{unresolved && <strong role="alert">{say(locale, "Resolve unavailable context before submitting.", "送信する前に利用できないコンテキストを解決してください。")}</strong>}</div>;
  const contextPanel = active ? <div className="rw-context-panel">{summary}{active.investigation.predecessor_investigation_id && <section className="rw-branch-origin"><h3>{say(locale, "Refresh branch", "更新した分岐")}</h3><p>{say(locale, "Original evidence remains in the predecessor investigation. Conversation narrative was not copied.", "元の根拠は分岐元の調査に保持されています。会話文はコピーされていません。")}</p><details><summary>{say(locale, "Predecessor revision", "分岐元の版")}</summary><code>{active.investigation.predecessor_revision_id}</code></details><button className="button secondary" onClick={() => navigate({ investigationId: active.investigation.predecessor_investigation_id, conversationId: null, workspaceTab: "context" })}>{say(locale, "Open original investigation", "元の調査を開く")}</button></section>}<p>{say(locale, "Attachments add context. Pins restrict the investigation. Chats share these settings, not each other’s narrative.", "追加はコンテキストを補い、固定は調査を制限します。チャット間で共有されるのはこれらの設定で、会話文ではありません。")}</p>
    {(["attachments", "pins"] as const).map(group => <section key={group}><h3>{say(locale, group === "attachments" ? "Attached context" : "Pinned restrictions", group === "attachments" ? "追加したコンテキスト" : "固定した制限")}</h3>{!active.context[group].length && <p className="muted">{say(locale, "None selected", "選択なし")}</p>}<ul className="rw-references">{active.context[group].map(item => <li key={refKey(item)}><code>{item.id}</code><span>{active.context.resolution.find(value => refKey(value.reference) === refKey(item))?.status ?? "unavailable"}</span><button className="button secondary" disabled={blocked || archived} onClick={() => changeContext({ op: group === "attachments" ? "detach" : "unpin", reference: item })}>{say(locale, "Remove", "解除")}</button></li>)}</ul></section>)}
    <button className="button secondary" onClick={() => setBrowse(v => !v)}><Layers3 size={16} />{say(locale, browse ? "Close catalogue" : "Browse context catalogue", browse ? "カタログを閉じる" : "コンテキストカタログを開く")}</button>
    {browse && <CatalogueBrowser locale={locale} accessKey={accessKey} client={catalogue} scope={active.context.scope} pinnedSnapshotId={active.context.snapshot_id} onAccessLost={onAccessLost} onSelect={setSelected} />}
    {reference && <div className="rw-selection"><p>{say(locale, "Selected only; your context has not changed.", "選択のみで、コンテキストはまだ変更されていません。")}</p><code>{reference.id}</code><div className="rw-actions"><button className="button primary" disabled={blocked || archived} onClick={() => changeContext({ op: "attach", reference })}>{say(locale, "Attach context", "コンテキストに追加")}</button><button className="button secondary" disabled={blocked || archived} onClick={() => changeContext({ op: "pin", reference })}>{say(locale, "Pin restriction", "制限として固定")}</button></div></div>}
    <ScopeEditor key={active.investigation.id} locale={locale} context={active.context} disabled={blocked || archived} save={(scope, revision) => changeContext({ op: "scope", scope }, revision)} />
    <details className="rw-management"><summary>{say(locale, "Refresh into a new branch", "新しい分岐に更新")}</summary><p>{say(locale, "Choose a new snapshot explicitly. Original context and evidence remain; conversation narrative is not copied.", "新しいスナップショットを指定します。元のコンテキストと根拠は保持され、会話文はコピーされません。")}</p><label>{say(locale, "Branch name", "分岐の名前")}<input maxLength={200} value={refreshName} onChange={e => setRefreshName(e.target.value)} /></label><label>{say(locale, "Target snapshot", "更新先のスナップショット")}<select value={refreshSnapshot} onChange={e => setRefreshSnapshot(e.target.value)}><option value="">{say(locale, "Choose snapshot", "選択してください")}</option>{snapshots.filter(s => s.snapshot_id !== active.context.snapshot_id).map(s => <option value={s.snapshot_id} key={s.snapshot_id}>{s.label[locale]}</option>)}</select></label><button className="button secondary" disabled={blocked || archived || catalogueStatus !== "ready" || !refreshName.trim() || !refreshSnapshot || refreshSnapshot === active.context.snapshot_id} onClick={() => void mutate({ method: "refresh", request: { investigation_id: active.investigation.id, expected_revision_id: active.context.id, target_snapshot_id: refreshSnapshot, name: refreshName.trim(), idempotency_key: requestKey() } })}>{say(locale, "Create refresh branch", "更新した分岐を作成")}</button></details>
  </div> : <p>{say(locale, "Choose an investigation to inspect its context.", "調査を選ぶとコンテキストを確認できます。")}</p>;
  const chatPanel = <div className="rw-chat"><header><MessageSquare size={18} /><h2>{conversation?.name ?? say(locale, "Choose a conversation", "チャットを選択してください")}</h2></header>{active && summary}
    {!runTransport && <p className="rw-unavailable" role="status">{say(locale, "Execution is unavailable until the research run service is connected. You can manage context and keep a draft here.", "実行サービスの接続後に質問を実行できます。ここではコンテキストの管理と下書きの作成ができます。")}</p>}
    {runTransport && runSource === "development-fixture" && <p className="rw-fixture-label">{say(locale, "Development execution · synthetic examples only", "開発用の実行 · 合成サンプルのみ")}</p>}
    {runTransport && runSource === "service" && !runSubmitEnabled && <p className="rw-unavailable" role="status">{say(locale, "New activity is paused. Saved history and cancellation remain available.", "新しい処理は停止中です。保存済みの履歴とキャンセルは利用できます。")}</p>}
    {runSource === "service" && runTransport && !historyVerified && conversation && <p role="status">{say(locale, "Checking saved activity before submission…", "送信の前に保存された履歴を確認しています…")}</p>}
    {pendingRun && !busy && <div className="rw-alert"><p>{say(locale, "The last action may have been saved. Retry the same request to recover it.", "前の操作が保存された可能性があります。同じリクエストを再試行して確認できます。")}</p><button className="button secondary" onClick={() => mutateRun(pendingRun)}>{say(locale, "Retry last activity action", "前の実行操作を再試行")}</button></div>}
    <ResearchActivity locale={locale} runs={runs} busy={blocked} executionAvailable={!!runTransport} onStatus={runTransport ? run => void runAction(signal => runTransport.status(researchRunAddress(run), signal), run) : undefined} onEvents={runTransport ? run => void runAction(async signal => mergeRunEvents(run, await runTransport.events({ ...researchRunAddress(run), after_cursor: run.event_cursor }, signal)), run) : undefined} onCancel={runTransport ? run => mutateRun({ method: "cancel", request: { ...researchRunAddress(run), idempotency_key: requestKey() }, binding: run.context.binding }) : undefined} onClarify={runTransport && runSubmitEnabled ? (run, answer) => mutateRun({ method: "clarify", request: { ...researchRunAddress(run), idempotency_key: requestKey(), answer, ...(run.clarification_id ? { clarification_id: run.clarification_id } : {}) }, binding: run.context.binding }) : undefined} onContinue={runTransport && runSubmitEnabled ? run => mutateRun({ method: "continue", request: { ...researchRunAddress(run), idempotency_key: requestKey() }, binding: run.context.binding }) : undefined} onOpenEvidence={openEvidence} />
    {nextRunPage && <button className="button secondary" disabled={busy} onClick={() => setHistoryPages(value => value + 1)}>{say(locale, "More saved activity", "保存された履歴をさらに表示")}</button>}
    <form className="rw-composer" onSubmit={e => { e.preventDefault(); submit(); }}><label htmlFor="research-question">{say(locale, "Your question", "質問")}</label><textarea id="research-question" value={draft} maxLength={8000} disabled={!conversation} placeholder={say(locale, "Ask about the selected data…", "選択したデータについて質問…")} onChange={e => { setDraft(e.target.value); if (location.investigationId && location.conversationId) session.drafts.writeDraft(location.investigationId, location.conversationId, e.target.value); }} /><button className="button primary" disabled={!runTransport || !runSubmitEnabled || !conversation || blocked || checking || archived || unresolved || (runSource === "service" && !historyVerified) || !draft.trim()}>{say(locale, !runTransport ? "Execution unavailable" : runSource === "development-fixture" ? "Submit development question" : "Submit question", !runTransport ? "実行を利用できません" : runSource === "development-fixture" ? "開発用の質問を送信" : "質問を送信")}<ChevronRight size={16} /></button></form>
    {conversation && <details className="rw-management"><summary>{say(locale, "Rename conversation", "チャットの名前を変更")}</summary><label>{say(locale, "Conversation name", "チャット名")}<input maxLength={200} value={chatRename} onChange={e => setChatRename(e.target.value)} /></label><button className="button secondary" disabled={blocked || archived || !chatRename.trim()} onClick={() => void mutate({ method: "renameConversation", request: { investigation_id: conversation.investigation_id, conversation_id: conversation.id, name: chatRename.trim(), expected_version: conversation.metadata_version, idempotency_key: requestKey() } })}>{say(locale, "Save name", "名前を保存")}</button></details>}
  </div>;
  return <section className="research-workspace"><header className="runtime-page-heading"><div className="eyebrow">OCEAN / v1</div><h1>{say(locale, "Research", "リサーチ")}</h1><p>{say(locale, "Private investigations · shared context · separate conversations", "非公開の調査 · 共有するコンテキスト · 個別の会話")}</p></header>
    {error && <div className="rw-alert" role="alert"><strong>{say(locale, error === 409 ? "A newer version exists. Review current context before applying your change." : error === 404 ? "This investigation or conversation is unavailable." : error === 422 ? "Check the selection or change and try again." : "The research service could not verify this request.", error === 409 ? "新しい版があります。現在のコンテキストを確認してから変更してください。" : error === 404 ? "この調査またはチャットを利用できません。" : error === 422 ? "選択や変更内容を確認してください。" : "リサーチサービスでリクエストを確認できませんでした。")}</strong><button className="button secondary" onClick={() => { setTick(v => v + 1); setListTick(v => v + 1); historyScheduler.current?.request(); }}>{say(locale, "Reload current state", "現在の状態を再読込")}</button></div>}
    {pending && !busy && <div className="rw-alert"><p>{say(locale, "The last change may have reached the service. Retry the same request safely.", "前の変更がサービスに届いた可能性があります。同じリクエストを安全に再試行できます。")}</p><button className="button secondary" onClick={() => void mutate(pending)}>{say(locale, "Retry last change", "前の変更を再試行")}</button></div>}
    {conflict?.method === "changeContext" && active && <button className="button secondary" disabled={blocked || checking} onClick={() => void mutate({ ...conflict, request: { ...conflict.request, expected_revision_id: active.context.id, idempotency_key: requestKey() } })}>{say(locale, "Apply intended change to this reviewed revision", "確認した版にこの変更を適用")}</button>}
    {notice && <p className="rw-notice" role="status">{notice}</p>}{checking && <p className="muted" role="status">{say(locale, "Checking shared context…", "共有コンテキストを確認中…")}</p>}
    <div className="rw-layout"><details className="rw-nav-disclosure" open={navigationOpen} onToggle={event => setNavigationOpen(event.currentTarget.open)}><summary>{say(locale, "Investigations and conversations", "調査とチャット")}</summary><nav className="rw-navigation" aria-label={say(locale, "Investigations and conversations", "調査とチャット")}><h2>{say(locale, "Investigations", "調査")}</h2><ul>{investigations.map(item => <li key={item.id}><button aria-current={location.investigationId === item.id ? "page" : undefined} onClick={() => navigate({ investigationId: item.id, conversationId: null })}>{item.name}<span>{item.status === "archived" ? say(locale, "Archived", "アーカイブ済み") : ""}</span></button></li>)}</ul>{nextInvestigation && <button className="button secondary" onClick={() => setInvestigationPages(value => value + 1)}>{say(locale, "More investigations", "調査をさらに表示")}</button>}
      <details className="rw-management"><summary><Plus size={15} />{say(locale, "New investigation", "調査を作成")}</summary><label>{say(locale, "Investigation name", "調査名")}<input maxLength={200} value={newName} onChange={e => setNewName(e.target.value)} /></label><label>{say(locale, "Snapshot", "スナップショット")}<select disabled={catalogueStatus !== "ready" || !snapshots.length} value={newSnapshot} onChange={e => setNewSnapshot(e.target.value)}><option value="">{say(locale, "Choose snapshot", "選択してください")}</option>{snapshots.map(s => <option value={s.snapshot_id} key={s.snapshot_id}>{s.label[locale]}</option>)}</select></label><button className="button primary" disabled={blocked || catalogueStatus !== "ready" || !newName.trim() || !newSnapshot} onClick={() => void mutate({ method: "create", request: { name: newName.trim(), snapshot_id: newSnapshot, scope: defaultCatalogueScope(), idempotency_key: requestKey() } })}>{say(locale, "Create investigation", "調査を作成")}</button>{catalogueStatus === "loading" ? <p role="status">{say(locale, "Checking available snapshots…", "利用できるスナップショットを確認中…")}</p> : catalogueStatus === "error" ? <p role="status">{say(locale, "Snapshot availability could not be verified. Refresh access to check again.", "スナップショットの利用状況を確認できませんでした。アクセス権を再確認してください。")}</p> : !snapshots.length ? <p role="status">{say(locale, "No eligible snapshot is currently available for a new investigation.", "新しい調査に利用できるスナップショットは現在ありません。")}</p> : null}</details>
      {active && <><h3>{say(locale, "Conversations", "チャット")}</h3><ul>{conversations.map(chat => <li key={chat.id}><button aria-current={location.conversationId === chat.id ? "page" : undefined} onClick={() => navigate({ conversationId: chat.id })}>{chat.name}</button></li>)}</ul>{nextConversation && <button className="button secondary" onClick={() => setConversationPages(value => value + 1)}>{say(locale, "More conversations", "チャットをさらに表示")}</button>}<label>{say(locale, "New conversation name", "新しいチャット名")}<input maxLength={200} value={conversationName} onChange={e => setConversationName(e.target.value)} /></label><button className="button secondary" disabled={blocked || archived || !conversationName.trim()} onClick={() => void mutate({ method: "createConversation", request: { investigation_id: active.investigation.id, name: conversationName.trim(), idempotency_key: requestKey() } })}><Plus size={15} />{say(locale, "New conversation", "チャットを作成")}</button>
      <details className="rw-management"><summary>{say(locale, "Manage investigation", "調査を管理")}</summary><label>{say(locale, "Investigation name", "調査名")}<input maxLength={200} value={rename} onChange={e => setRename(e.target.value)} /></label><button className="button secondary" disabled={blocked || !rename.trim()} onClick={() => void mutate({ method: "rename", request: { investigation_id: active.investigation.id, expected_version: active.investigation.metadata_version, name: rename.trim(), idempotency_key: requestKey() } })}>{say(locale, "Save name", "名前を保存")}</button><button className="button secondary" disabled={blocked} onClick={() => void mutate({ method: "archive", request: { investigation_id: active.investigation.id, expected_version: active.investigation.metadata_version, archived: !archived, idempotency_key: requestKey() } })}>{say(locale, archived ? "Restore investigation" : "Archive investigation", archived ? "調査を復元" : "調査をアーカイブ")}</button></details></>}
    </nav></details><div className="rw-main">{!location.investigationId && <div className="rw-empty"><Layers3 size={30} /><h2>{say(locale, "Start with an investigation", "調査から始めましょう")}</h2><p>{say(locale, "Choose a private investigation or create one with an explicit snapshot.", "非公開の調査を選ぶか、スナップショットを指定して作成してください。")}</p></div>}<ShellSplitPanels locale={locale} width={preferences.workspaceWidth} open={preferences.workspaceOpen} active={location.mobilePane === "workspace" ? "secondary" : "primary"} onWidth={workspaceWidth => onPreferences({ workspaceWidth })} onOpen={workspaceOpen => onPreferences({ workspaceOpen })} onActive={pane => navigate({ mobilePane: pane === "secondary" ? "workspace" : "chat" })} primaryLabel={say(locale, "Chat", "チャット")} secondaryLabel={say(locale, "Workspace", "ワークスペース")} primary={chatPanel} secondary={<ShellTabs label={say(locale, "Workspace sections", "ワークスペースの項目")} active={location.workspaceTab} onChange={workspaceTab => navigate({ workspaceTab: workspaceTab as ResearchLocation["workspaceTab"] })} tabs={[
      { id: "context", label: say(locale, "Context", "コンテキスト"), content: contextPanel },
      { id: "results", label: say(locale, "Results", "結果"), content: <ResearchResults locale={locale} runs={runs} onOpenEvidence={openEvidence} /> },
      { id: "experiments", label: say(locale, "Experiments", "実験"), content: <p>{say(locale, "Experiments are unavailable until proposal and execution services are connected.", "提案・実行サービスの接続後に実験を利用できます。")}</p> },
      { id: "evidence", label: say(locale, "Evidence", "根拠"), content: <ResearchEvidence locale={locale} evidence={evidence} /> },
    ]} />} /></div></div>
  </section>;
}

async function loadInvestigationPages(client: InvestigationClient, count: number, signal: AbortSignal) {
  const items: Investigation[] = []; let next_after_id: string | null = null; const cursors = new Set<string>();
  for (let index = 0; index < count; index++) {
    const page = await client.list({ limit: 100, after_id: next_after_id }, signal);
    if (page.items.some(item => items.some(previous => previous.id === item.id))) throw new Error("Repeated investigation page");
    items.push(...page.items); next_after_id = page.next_after_id;
    if (next_after_id === null) break;
    if (cursors.has(next_after_id)) throw new Error("Repeated investigation cursor"); cursors.add(next_after_id);
  }
  return { items, next_after_id };
}
async function loadConversationPages(client: InvestigationClient, investigation_id: string, count: number, signal: AbortSignal) {
  const items: Conversation[] = []; let next_after_id: string | null = null; const cursors = new Set<string>();
  for (let index = 0; index < count; index++) {
    const page = await client.listConversations({ investigation_id, limit: 100, after_id: next_after_id }, signal);
    if (page.items.some(item => items.some(previous => previous.id === item.id))) throw new Error("Repeated conversation page");
    items.push(...page.items); next_after_id = page.next_after_id;
    if (next_after_id === null) break;
    if (cursors.has(next_after_id)) throw new Error("Repeated conversation cursor"); cursors.add(next_after_id);
  }
  return { items, next_after_id };
}

function scopeFingerprint(value: unknown): string {
  const canonical = (item: unknown): unknown => Array.isArray(item) ? item.map(canonical) : item !== null && typeof item === "object" ? Object.fromEntries(Object.entries(item).filter(([, child]) => child != null).sort(([left],[right]) => left.localeCompare(right)).map(([key, child]) => [key, canonical(child)])) : item;
  return JSON.stringify(canonical(value));
}

function ScopeEditor({ locale, context, disabled, save }: { locale: Locale; context: InvestigationContext; disabled: boolean; save: (scope: EvidenceScope, revision: string) => Promise<boolean> }) {
  const [scope, setScope] = useState(() => structuredClone(context.scope)); const [revision, setRevision] = useState(context.id); const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!dirty || (context.id !== revision && scopeFingerprint(context.scope) === scopeFingerprint(scope))) { setScope(structuredClone(context.scope)); setRevision(context.id); setDirty(false); } }, [context.id, context.scope, dirty]);
  const change = (family: typeof families[number], key: string, value: unknown) => { setDirty(true); setScope(previous => ({ ...previous, sources: { ...previous.sources, [family]: { ...previous.sources[family], filters: { ...previous.sources[family].filters, [key]: value } } } })); };
  const fields: Record<typeof families[number], string[]> = { ctd: ["bay", "station", "sample_id", "time_from", "time_to"], metagenome: ["bay", "station", "sample_id", "time_from", "time_to"], remote_sensing: ["dataset_id", "lat_min", "lat_max", "lon_min", "lon_max", "time_from", "time_to"], edna_metabarcoding: ["provider", "provider_project_id", "provider_run_id", "sample_id", "sample_kind", "assignment_method", "taxon", "is_control", "lat_min", "lat_max", "lon_min", "lon_max", "time_from", "time_to"] };
  const labels: Record<string, [string,string]> = { bay:["Bay","湾"],station:["Station","観測点"],sample_id:["Sample ID","サンプルID"],time_from:["From (ISO date/time)","開始 (ISO日時)"],time_to:["To (ISO date/time)","終了 (ISO日時)"],dataset_id:["SST product ID","SST製品ID"],lat_min:["Minimum latitude","最小緯度"],lat_max:["Maximum latitude","最大緯度"],lon_min:["Minimum longitude","最小経度"],lon_max:["Maximum longitude","最大経度"],provider:["Provider","提供元"],provider_project_id:["Provider project","提供元プロジェクト"],provider_run_id:["Provider run","提供元の実行"],sample_kind:["Sample kind","サンプル種別"],assignment_method:["Assignment method","割当て方法"],taxon:["Taxon","分類群"],is_control:["Control sample","対照サンプル"] };
  const options: Record<string, string[]> = { bay:["O","I","M"],sample_kind:["environmental","negative_control","positive_control","mock_community","unknown"],assignment_method:["qcauto_target","qcauto_95pct_3nn_target"],is_control:["true","false"] };
  return <details className="rw-scope-editor"><summary>{say(locale, "Edit source scope", "ソースの対象範囲を編集")}</summary><p>{say(locale, "These filters restrict eligible data. Attachments do not replace these filters.", "これらの条件は利用可能なデータを制限します。追加した項目が条件を置き換えることはありません。")}</p>{revision !== context.id && dirty && <p role="alert">{say(locale, "Context changed while editing. Saving will require a conflict review.", "編集中にコンテキストが変わりました。保存時に競合を確認してください。")}</p>}{families.map((family,index) => <fieldset key={family} disabled={disabled}><legend>{familyNames[index]}</legend><label className="rw-check"><input type="checkbox" checked={scope.sources[family].enabled} onChange={e => { const enabled = e.target.checked; setDirty(true); setScope(previous => ({ ...previous, sources: { ...previous.sources, [family]: { ...previous.sources[family], enabled } } })); }} />{say(locale, "Enabled", "有効")}</label><div className="rw-filter-fields">{fields[family].map(field => { const value = (scope.sources[family].filters as Record<string, unknown>)[field]; const title = labels[field][locale === "en" ? 0 : 1]; return <label key={field}>{title}{options[field] ? <select value={value == null ? "" : String(value)} onChange={e => change(family, field, e.target.value === "" ? null : field === "is_control" ? e.target.value === "true" : e.target.value)}><option value="">{say(locale, "Any", "指定なし")}</option>{options[field].map(option => <option key={option}>{option}</option>)}</select> : <input type={/^(lat|lon)_/.test(field) ? "number" : "text"} step="any" value={value == null ? "" : String(value)} onChange={e => change(family, field, e.target.value === "" ? null : /^(lat|lon)_/.test(field) ? Number(e.target.value) : e.target.value)} />}</label>; })}{family === "edna_metabarcoding" && <label>{say(locale, "Published analysis ID", "公開解析ID")}<input value={scope.sources.edna_metabarcoding.analysis_id ?? ""} onChange={e => { const analysis_id = e.target.value || null; setDirty(true); setScope(previous => ({ ...previous, sources: { ...previous.sources, edna_metabarcoding: { ...previous.sources.edna_metabarcoding, analysis_id } } })); }} /></label>}</div></fieldset>)}<div className="rw-actions"><button className="button primary" disabled={disabled || !dirty} onClick={() => void save(scope, revision).then(saved => { if (saved) setDirty(false); })}>{say(locale, "Apply source scope", "対象範囲を適用")}</button><button className="button secondary" disabled={disabled || !dirty} onClick={() => { setScope(structuredClone(context.scope)); setRevision(context.id); setDirty(false); }}>{say(locale, "Discard local edits", "編集を取り消す")}</button></div></details>;
}
