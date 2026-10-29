"use client";

/** C25 service UI. Private state is volatile and bound to the current account/context. */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Locale } from "./model";
import type { ContextReference } from "./investigation-service";
import type { ExperimentSnapshot, ExperimentContextBinding, ExperimentProposal, ExperimentEventsResponse } from "./experiment-contract";
import { executeExperimentMutation, sameExperimentBinding, type ExperimentClient, type ExperimentMutationIntent } from "./experiment-service";
import { experimentDecision, ExperimentSession, parseExperimentSelection, experimentSelectionUrl, mergeExperimentSnapshot, type ExperimentSelection } from "./experiment-state";
import { ExperimentReview } from "./research-experiments-view";
import { collectArtifact, executionRequest, ExecutionSession, mergeExecution, type ExperimentExecutionClient, type ExecutionResponse, type ExecutionEventsResponse, type ExecutionArtifact, type PendingExecutionCancel } from "./experiment-execution-service";
import { experimentCanonical } from "./experiment-http";
import "./research-experiments.css";

const say = (locale: Locale, en: string, ja: string) => locale === "en" ? en : ja;
const statusCode = (error: unknown) => error !== null && typeof error === "object" && "status_code" in error && typeof error.status_code === "number" ? error.status_code : 503;
const activeState = (state: string) => ["queued", "running", "cancelling"].includes(state);
const terminalText: Record<string, readonly [string, string]> = { queued: ["Queued", "待機中"], running: ["Running", "実行中"], cancelling: ["Cancellation requested", "キャンセル要求済み"], completed: ["Completed", "完了"], failed: ["Failed", "失敗"], cancelled: ["Cancelled", "キャンセル済み"], timed_out: ["Timed out", "時間切れ"] };
export type ExperimentsProps = {
  locale: Locale; accessKey: string; active: boolean; binding: ExperimentContextBinding | null;
  client?: ExperimentClient; executionClient?: ExperimentExecutionClient;
  session: ExperimentSession; executionSession: ExecutionSession;
  canApprove: boolean; canRevise: boolean; canCancel: boolean; canAttach: boolean; canExport: boolean; externalBusy: boolean;
  onAccessLost: () => void; onAttach: (reference: ContextReference) => boolean | Promise<boolean>;
};
type ReviewState = { scope: string; list: ExperimentSnapshot[]; next: string | null; proposal: ExperimentSnapshot | null };
export function ResearchExperiments(props: ExperimentsProps) {
  const { locale, accessKey, binding, client, executionClient, session, executionSession } = props;
  const scope = `${accessKey}:${binding?.investigation_id}:${binding?.conversation_id}`;
  const callbacks = useRef(props); callbacks.current = props;
  const [selection, setSelection] = useState<ExperimentSelection | null>(null);
  const selectionRef = useRef(selection); selectionRef.current = selection;
  const [after, setAfter] = useState<string | null>(null), [previous, setPrevious] = useState<(string | null)[]>([]);
  const [review, setReview] = useState<ReviewState | null>(null);
  const reviewRef = useRef<ReviewState | null>(null);
  const [projectionState, setExecution] = useState<ExecutionResponse | null>(null);
  const executionRef = useRef<ExecutionResponse | null>(null);
  const [proposalAfter, setProposalAfter] = useState(0), [proposalPrevious, setProposalPrevious] = useState<number[]>([]);
  const [proposalEvents, setProposalEvents] = useState<ExperimentEventsResponse | null>(null);
  const [executionEvents, setExecutionEvents] = useState<ExecutionEventsResponse | null>(null);
  const [eventAfter, setEventAfter] = useState(0), [eventPrevious, setEventPrevious] = useState<number[]>([]);
  const [executionError, setExecutionError] = useState(false);
  const [notice, setNotice] = useState(""), [error, setError] = useState<number | null>(null);
  const [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<ExperimentMutationIntent | null>(null), [pendingCancel, setPendingCancel] = useState<PendingExecutionCancel | null>(null);
  const [preview, setPreview] = useState<{ artifact: ExecutionArtifact; table: Awaited<ReturnType<typeof collectArtifact>>["preview"]; image: string | null } | null>(null);
  const [downloadBytes, setDownloadBytes] = useState<number | null>(null);
  const imageUrl = useRef<string | null>(null);
  const epoch = useRef(0), mounted = useRef(false), lock = useRef(false);
  const pollAbort = useRef<AbortController | null>(null), actionAbort = useRef<AbortController | null>(null);
  const visible = review?.scope === scope ? review : null;
  const candidate = visible?.proposal;
  const proposal = candidate && candidate.id === selection?.experiment_id && (!selection.proposal_revision_id || candidate.proposal_revision_id === selection.proposal_revision_id) ? candidate : null;
  const execution = projectionState && proposal && projectionState.experiment_id === proposal.id && projectionState.proposal_revision_id === proposal.proposal_revision_id && projectionState.proposal_version === proposal.version && sameExperimentBinding(projectionState.binding, proposal.binding) && experimentCanonical(projectionState.hashes) === experimentCanonical(proposal.hashes) ? projectionState : null;
  const clearPreview = useCallback(() => { if (imageUrl.current) URL.revokeObjectURL(imageUrl.current); imageUrl.current = null; setPreview(null); setDownloadBytes(null); }, []);
  const fail = useCallback((failure: unknown) => {
    const status = statusCode(failure); setError(status); clearPreview();
    if (status === 401 || status === 403) { ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); session.clear(); executionSession.clear(); reviewRef.current = null; executionRef.current = null; setReview(null); setExecution(null); setProposalEvents(null); setExecutionEvents(null); setPending(null); setPendingCancel(null); callbacks.current.onAccessLost(); }
  }, [session, executionSession, clearPreview]);
  const select = useCallback((next: ExperimentSelection | null, replace = false) => {
    ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); lock.current = false; setBusy(false); clearPreview();
    const url = experimentSelectionUrl(window.location.search, next);
    window.history[replace ? "replaceState" : "pushState"](null, "", window.location.pathname + url + window.location.hash);
    selectionRef.current = next; setSelection(next); setEventAfter(0); setEventPrevious([]); setProposalAfter(0); setProposalPrevious([]); setExecution(null); executionRef.current = null; setExecutionEvents(null); setProposalEvents(null); setError(null); setNotice("");
    // Retain the list but hide the previous proposal synchronously on selection.
    reviewRef.current = reviewRef.current ? { ...reviewRef.current, proposal: null } : null; setReview(reviewRef.current);
  }, [clearPreview]);
  useEffect(() => {
    mounted.current = true; session.bind(accessKey); executionSession.bind(accessKey);
    const restore = () => { lock.current = false; setBusy(false); reviewRef.current = reviewRef.current ? { ...reviewRef.current, proposal: null } : null; setReview(reviewRef.current); ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); clearPreview(); const next = parseExperimentSelection(window.location.search); selectionRef.current = next; setSelection(next); setExecution(null); executionRef.current = null; setExecutionEvents(null); setProposalEvents(null); setEventAfter(0); setEventPrevious([]); setProposalAfter(0); setProposalPrevious([]); setError(null); setRefresh(x => x + 1); };
    restore(); window.addEventListener("popstate", restore);
    return () => { mounted.current = false; ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); if (imageUrl.current) URL.revokeObjectURL(imageUrl.current); window.removeEventListener("popstate", restore); };
  }, [accessKey, session, executionSession, clearPreview]);
  useEffect(() => {
    ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); lock.current = false; setBusy(false); setAfter(null); setPrevious([]); setError(null); setNotice(""); clearPreview(); reviewRef.current = null; setReview(null); executionRef.current = null; setExecution(null); setProposalEvents(null); setExecutionEvents(null); setEventAfter(0); setEventPrevious([]);
    const restored = parseExperimentSelection(window.location.search); selectionRef.current = restored; setSelection(restored); setProposalAfter(0); setProposalPrevious([]);
    setPending(binding ? session.getPending(binding) : null); setPendingCancel(binding ? executionSession.get(binding) : null);
  }, [scope, session, executionSession, clearPreview]);
  useEffect(() => {
    ++epoch.current; pollAbort.current?.abort(); actionAbort.current?.abort(); lock.current = false; setBusy(false); clearPreview(); setPending(binding ? session.getPending(binding) : null); setPendingCancel(binding ? executionSession.get(binding) : null); setRefresh(x => x + 1);
  }, [binding?.context_revision_id, binding?.context_payload_sha256, session, executionSession, clearPreview]);
  useEffect(() => {
    if (!props.active || !binding || !client) return;
    let closed = false, inFlight = false, timer: ReturnType<typeof setTimeout> | null = null;
    const load = async () => {
      if (closed || inFlight) return;
      if (closed || lock.current || callbacks.current.externalBusy || document.visibilityState === "hidden") { timer = setTimeout(load, 10000); return; }
      inFlight = true;
      const mine = epoch.current, generation = session.generation, selected = selectionRef.current;
      const abort = new AbortController(); pollAbort.current?.abort(); pollAbort.current = abort;
      const deadline = setTimeout(() => abort.abort(), 15000); setLoading(true);
      try {
        const page = await client.list({ investigation_id: binding.investigation_id, conversation_id: binding.conversation_id, limit: 25, after_id: after }, abort.signal);
        let item: ExperimentSnapshot | null = null;
        if (selected) item = (await client.get({ experiment_id: selected.experiment_id, proposal_revision_id: selected.proposal_revision_id }, abort.signal)).experiment;
        const belongs = (value: ExperimentSnapshot) => value.binding.investigation_id === binding.investigation_id && value.binding.conversation_id === binding.conversation_id;
        if (page.items.some(value => !belongs(value)) || item && !belongs(item)) throw { status_code: 409 };
        let executionFailed = false;
        let projection: ExecutionResponse | null = null, events: ExecutionEventsResponse | null = null, history: ExperimentEventsResponse | null = null;
        if (item) {
          history = await client.events({ experiment_id: item.id, after_cursor: proposalAfter, limit: 100 }, abort.signal);
          if (executionClient) {
            try {
            projection = await executionClient.status({ ...executionRequest(item), execution_id: null }, abort.signal);
            if (projection.execution) events = await executionClient.events({ ...executionRequest(item), execution_id: projection.execution.id, after_cursor: eventAfter, limit: 100 }, abort.signal);
            if (events) projection = mergeExecution(projection, events);
            } catch (failure) { if ([401, 403, 409].includes(statusCode(failure))) throw failure; executionFailed = true; projection = null; events = null; }
          }
        }
        if (closed || !mounted.current || mine !== epoch.current || !session.isCurrent(accessKey, generation) || abort.signal.aborted) return;
        const priorItem = reviewRef.current?.proposal;
        if (item && priorItem?.id === item.id) item = mergeExperimentSnapshot(priorItem, item);
        const next = { scope, list: page.items, next: page.next_cursor, proposal: item };
        reviewRef.current = next; setReview(next); setProposalEvents(history); setError(null); setExecutionError(executionFailed);
        const priorProjection = executionRef.current;
        projection = projection ? mergeExecution(priorProjection?.proposal_revision_id === projection.proposal_revision_id ? priorProjection : null, projection) : null; executionRef.current = projection; setExecution(projection); setExecutionEvents(events);
        if (priorProjection?.execution && (!projection?.execution || projection.execution.id !== priorProjection.execution.id || projection.execution.outputs_manifest_sha256 !== priorProjection.execution.outputs_manifest_sha256 || projection.proposal_revision_id !== priorProjection.proposal_revision_id)) clearPreview();
      } catch (failure) { if (!closed && mounted.current && mine === epoch.current) { reviewRef.current = null; setReview(null); executionRef.current = null; setExecution(null); setExecutionEvents(null); setProposalEvents(null); fail(failure); } }
      finally { inFlight = false; clearTimeout(deadline); if (!closed && mine === epoch.current) setLoading(false); if (!closed) timer = setTimeout(load, 10000); }
    };
    void load(); const focused = () => { if (document.visibilityState !== "hidden" && !lock.current && !inFlight) { if (timer) clearTimeout(timer); pollAbort.current?.abort(); timer = setTimeout(load, 0); } };
    window.addEventListener("focus", focused); document.addEventListener("visibilitychange", focused);
    return () => { closed = true; if (timer) clearTimeout(timer); pollAbort.current?.abort(); window.removeEventListener("focus", focused); document.removeEventListener("visibilitychange", focused); };
  }, [props.active, scope, binding?.context_revision_id, binding?.context_payload_sha256, client, executionClient, after, eventAfter, proposalAfter, selection?.experiment_id, selection?.proposal_revision_id, refresh, session, accessKey, fail, clearPreview]);
  const mutate = async (intent: ExperimentMutationIntent) => {
    if (!client || !binding || lock.current || callbacks.current.externalBusy || executionSession.get(binding)) return;
    const generation = session.generation;
    const mine = ++epoch.current; pollAbort.current?.abort(); clearPreview(); const abort = new AbortController(); actionAbort.current = abort;
    lock.current = true; setBusy(true); setError(null); setNotice(""); const deadline = setTimeout(() => abort.abort(), 15000);
    try {
      session.rememberPending(intent.binding, intent); setPending(intent);
      const result = await executeExperimentMutation(client, intent, abort.signal);
      if (!mounted.current || mine !== epoch.current || !session.isCurrent(accessKey, generation) || abort.signal.aborted) return;
      if (result.operation?.state === "unavailable" && result.operation.error_code === "conflict") { session.forgetPending(intent.binding, intent); setPending(null); throw { status_code: 409 }; }
      if (result.operation?.state !== "ready" || !result.experiment) { setNotice(say(locale, "The request is retained but its outcome is not confirmed. Retry the same action to reconcile it.", "リクエストは保持されていますが、結果は未確認です。同じ操作を再試行して確認してください。")); return; }
      session.forgetPending(intent.binding, intent); setPending(null); setExecution(null); executionRef.current = null; setExecutionEvents(null); setProposalEvents(null); setProposalAfter(0); setProposalPrevious([]);
      const next = { experiment_id: result.experiment.id, proposal_revision_id: null };
      window.history.replaceState(null, "", window.location.pathname + experimentSelectionUrl(window.location.search, next)); selectionRef.current = next; setSelection(next);
      reviewRef.current = { scope, list: reviewRef.current?.list ?? [], next: reviewRef.current?.next ?? null, proposal: result.experiment }; setReview(reviewRef.current);
      setNotice(say(locale, "Saved. Review the current version below. Approval does not launch Python.", "保存しました。下で現在の版を確認してください。承認だけではPythonを実行しません。"));
    } catch (failure) { if (mounted.current && mine === epoch.current && session.isCurrent(accessKey, generation)) { if (statusCode(failure) < 500) { session.forgetPending(intent.binding, intent); setPending(null); } fail(failure); } }
    finally { clearTimeout(deadline); if (mine === epoch.current) { lock.current = false; setBusy(false); setRefresh(x => x + 1); } }
  };
  const cancel = async (intent?: PendingExecutionCancel) => {
    const current = executionRef.current?.execution, item = reviewRef.current?.proposal;
    if (!executionClient || !binding || lock.current || callbacks.current.externalBusy || session.getPending(binding) || !callbacks.current.canCancel) return;
    if (!intent && (!current || !item || !activeState(current.state))) return;
    const request: PendingExecutionCancel = intent ?? { binding: item!.binding, request: { ...executionRequest(item!), execution_id: current!.id, idempotency_key: crypto.randomUUID() } };
    const generation = session.generation;
    const mine = ++epoch.current, abort = new AbortController(); pollAbort.current?.abort(); actionAbort.current = abort; lock.current = true; setBusy(true); setNotice(""); clearPreview(); const deadline = setTimeout(() => abort.abort(), 15000);
    try {
      executionSession.remember(request); setPendingCancel(request);
      const result = await executionClient.cancel(request.request, abort.signal);
      if (!mounted.current || mine !== epoch.current || !session.isCurrent(accessKey, generation) || abort.signal.aborted) return;
      executionSession.forget(request); setPendingCancel(null);
      if (reviewRef.current?.proposal && reviewRef.current.proposal.id === result.experiment_id && reviewRef.current.proposal.proposal_revision_id === result.proposal_revision_id && reviewRef.current.proposal.version === result.proposal_version && sameExperimentBinding(reviewRef.current.proposal.binding, result.binding) && experimentCanonical(reviewRef.current.proposal.hashes) === experimentCanonical(result.hashes)) { const merged = mergeExecution(executionRef.current, result); executionRef.current = merged; setExecution(merged); }
      setNotice(say(locale, "Cancellation request acknowledged. Completion waits for the retained terminal observation.", "キャンセル要求を受理しました。完了は保持された終了観測を待ちます。"));
    } catch (failure) { if (mounted.current && mine === epoch.current && session.isCurrent(accessKey, generation)) { if (statusCode(failure) < 500) { executionSession.forget(request); setPendingCancel(null); } fail(failure); } }
    finally { clearTimeout(deadline); if (mine === epoch.current) { lock.current = false; setBusy(false); setRefresh(x => x + 1); } }
  };
  const output = async (artifact: ExecutionArtifact, download: boolean) => {
    const item = reviewRef.current?.proposal, running = executionRef.current?.execution;
    if (!executionClient || !item || !running || !binding || lock.current || props.externalBusy || pending || pendingCancel || download && !props.canExport) return;
    const generation = session.generation;
    const mine = ++epoch.current, abort = new AbortController(); pollAbort.current?.abort(); actionAbort.current = abort; lock.current = true; setBusy(true); setNotice(""); clearPreview(); const deadline = setTimeout(() => abort.abort(), 120000);
    try {
      const result = await collectArtifact(executionClient, item, running, artifact, abort.signal, bytes => { if (mine === epoch.current) setDownloadBytes(bytes); });
      if (!mounted.current || mine !== epoch.current || !session.isCurrent(accessKey, generation) || abort.signal.aborted) return;
      if (download) {
        const bundle = { version: "c25-experimental-result-bundle-v1", authority: "experimental", scientific_approval: "not_independently_verified", execution_source: running.source, execution_performed: running.execution_performed, experiment_id: item.id, proposal_revision_id: item.proposal_revision_id, binding: item.binding, hashes: item.hashes, proposal: item.proposal, manifest_metadata: item.manifest, execution_id: running.id, execution_state: running.state, termination_verified: running.termination_verified, termination_proof_sha256: running.termination_proof_sha256, environment: item.environment, seeds: item.proposal.seeds, resources: item.proposal.resources, outputs_manifest_sha256: running.outputs_manifest_sha256, artifact, content_base64: bytesBase64(result.data) };
        downloadBlob(JSON.stringify(bundle, null, 2), `experimental-${item.binding.snapshot_id.slice(0, 12)}-${artifact.name}.json`, "application/json");
      } else {
        const image = artifact.kind === "raster" ? URL.createObjectURL(new Blob([result.data.slice().buffer], { type: "image/png" })) : null;
        imageUrl.current = image; setPreview({ artifact, table: result.preview, image });
      }
    } catch (failure) { if (mounted.current && mine === epoch.current && session.isCurrent(accessKey, generation)) fail(failure); }
    finally { clearTimeout(deadline); if (mine === epoch.current) { lock.current = false; setBusy(false); setDownloadBytes(null); setRefresh(x => x + 1); } }
  };
  const attach = async (artifact: ExecutionArtifact) => {
    const item = reviewRef.current?.proposal, current = executionRef.current?.execution;
    if (!props.canAttach || !artifact.attachment_reference || !item || !current || !executionClient || lock.current || props.externalBusy || pending || pendingCancel) return;
    const generation = session.generation;
    const mine = ++epoch.current, abort = new AbortController(); pollAbort.current?.abort(); actionAbort.current = abort; lock.current = true; setBusy(true); setNotice(""); const deadline = setTimeout(() => abort.abort(), 15000);
    try { const fresh = await executionClient.artifact({ ...executionRequest(item), execution_id: current.id, artifact_id: artifact.id, expected_sha256: artifact.sha256, offset: 0, limit: 1 }, abort.signal);
      if (!mounted.current || mine !== epoch.current || !session.isCurrent(accessKey, generation) || !callbacks.current.binding || !binding || !sameExperimentBinding(callbacks.current.binding, binding) || abort.signal.aborted || experimentCanonical(fresh.artifact) !== experimentCanonical(artifact)) return;
      if (fresh.artifact.attachment_reference && await callbacks.current.onAttach(fresh.artifact.attachment_reference) && mounted.current && mine === epoch.current) setNotice(say(locale, "Experimental evidence attached for future questions.", "次の質問に使う実験エビデンスを追加しました。"));
    } catch (failure) { if (mounted.current && mine === epoch.current && session.isCurrent(accessKey, generation)) fail(failure); }
    finally { clearTimeout(deadline); if (mine === epoch.current) { lock.current = false; setBusy(false); setRefresh(x => x + 1); } }
  };
  const blocked = busy || props.externalBusy || !!pending || !!pendingCancel;
  if (!binding) return <div className="re-workspace"><h3>{say(locale, "Experiments", "実験")}</h3><p>{say(locale, "Choose an investigation and conversation to review its experiment plans.", "調査とチャットを選択して、その実験計画を確認してください。")}</p></div>;
  if (!client) return <div className="re-workspace"><h3>{say(locale, "Experiments", "実験")}</h3><p role="status">{say(locale, "Experiment review services are unavailable. Saved context and other Workspace tabs remain accessible.", "実験計画の確認サービスを利用できません。保存済みコンテキストと他のタブは引き続き利用できます。")}</p></div>;
  return <section className="re-workspace" aria-label={say(locale, "Experiment Workspace", "実験ワークスペース")}>
    <div className="re-toolbar"><h3>{say(locale, "Experiments", "実験")}</h3><button type="button" className="button secondary" disabled={busy} onClick={() => { setError(null); setRefresh(x => x + 1); }}>{say(locale, "Refresh", "再読込")}</button></div>
    {execution?.capability.source === "synthetic-fixture" && <p className="rw-fixture-label">{say(locale, "Synthetic interface fixture. Python has not executed; terminal states do not prove real termination.", "合成された画面検証用データです。Pythonは実行しておらず、終了状態は実際の停止の証明ではありません。")}</p>}
    <p className="muted small">{say(locale, "Plans belong to this conversation. Browsing a plan does not change investigation scope.", "計画はこのチャットに属します。計画の閲覧によって調査の対象範囲は変わりません。")}</p>
    {error && <div className="rw-alert" role="alert">{say(locale, error === 409 ? "The proposal, context or access changed. Refresh and review the current version." : "This experiment view could not be verified. Refresh to check current access.", error === 409 ? "計画・コンテキスト・アクセス条件が変わりました。再読込して現在の版を確認してください。" : "この実験ビューを確認できませんでした。再読込して現在のアクセス権を確認してください。")}</div>}
    {notice && <p role="status">{notice}</p>}
    {pending && <div className="rw-alert" role="alert"><p>{say(locale, "The last proposal action may have been saved. Reconcile it using the same request.", "前の計画操作が保存された可能性があります。同じリクエストで確認してください。")}</p><button className="button secondary" disabled={busy} onClick={() => void mutate(pending)}>{say(locale, "Retry retained proposal action", "保持された計画操作を再試行")}</button></div>}
    {pendingCancel && <div className="rw-alert" role="alert"><p>{say(locale, "The cancellation outcome is uncertain. Retry the retained request; capacity is not released by this message.", "キャンセル要求の結果は未確認です。保持されたリクエストを再試行してください。この表示だけでは実行枠を解放しません。")}</p><button className="button secondary" disabled={busy} onClick={() => void cancel(pendingCancel)}>{say(locale, "Retry cancellation request", "キャンセル要求を再試行")}</button></div>}
    {loading && !visible && <p role="status">{say(locale, "Checking saved plans…", "保存された計画を確認しています…")}</p>}
    {visible && !visible.list.length && <p>{say(locale, "No saved plans on this page. Plans prepared for this conversation will appear here.", "このページには保存された計画がありません。このチャット用に準備した計画がここに表示されます。")}</p>}
    <ul className="re-list">{visible?.list.map(item => <li key={item.id}><button type="button" disabled={busy} aria-current={selection?.experiment_id === item.id ? "true" : undefined} onClick={() => select({ experiment_id: item.id, proposal_revision_id: null })}>{item.proposal.question}<small>{say(locale, "Version", "版")} {item.version} · {item.approval?.status === "current" ? say(locale, "Approved", "承認済み") : say(locale, "Needs review", "確認が必要")}</small></button></li>)}</ul>
    <div className="re-pager"><button className="button secondary" disabled={busy || !previous.length} onClick={() => { const values = [...previous]; setAfter(values.pop() ?? null); setPrevious(values); }}>{say(locale, "Previous plans", "前の計画")}</button><button className="button secondary" disabled={busy || !visible?.next} onClick={() => { if (visible?.next) { setPrevious([...previous, after]); setAfter(visible.next); } }}>{say(locale, "More plans", "次の計画")}</button></div>
    {proposal && <><ExperimentReview key={`${proposal.id}:${proposal.proposal_revision_id}:${proposal.version}`} locale={locale} value={proposal} currentContext={sameExperimentBinding(proposal.binding, binding)} busy={blocked} canApprove={props.canApprove && selection?.proposal_revision_id === null} canRevise={props.canRevise && selection?.proposal_revision_id === null}
      onApprove={item => void mutate({ method: "approve", binding: item.binding, request: experimentDecision(item, crypto.randomUUID()) })}
      onRevise={(plan: ExperimentProposal) => void mutate({ method: "revise", binding: proposal.binding, request: { ...proposal.binding, experiment_id: proposal.id, expected_version: proposal.version, expected_proposal_revision_id: proposal.proposal_revision_id, proposal: plan, idempotency_key: crypto.randomUUID() } })} />
      {selection?.proposal_revision_id && <button className="button secondary" disabled={busy} onClick={() => select({ experiment_id: proposal.id, proposal_revision_id: null })}>{say(locale, "Review latest version", "最新の版を確認")}</button>}
      <details><summary>{say(locale, "Proposal activity", "計画の履歴")}</summary><ol className="re-events">{proposalEvents?.items.map(item => <li key={item.cursor}>{item.summary[locale]}</li>)}</ol><div className="re-pager"><button className="button secondary" disabled={busy || !proposalPrevious.length} onClick={() => { const values = [...proposalPrevious]; setProposalAfter(values.pop() ?? 0); setProposalPrevious(values); }}>{say(locale, "Earlier proposal activity", "前の計画履歴")}</button><button className="button secondary" disabled={busy || !proposalEvents?.has_more} onClick={() => { if (proposalEvents) { setProposalPrevious([...proposalPrevious, proposalAfter]); setProposalAfter(proposalEvents.next_cursor); } }}>{say(locale, "More proposal activity", "次の計画履歴")}</button></div></details>
      <section className="re-execution">{executionError && <p className="rw-alert" role="status">{say(locale, "Execution updates are unavailable. Proposal review remains available; refresh to verify results again.", "実行の更新情報を取得できません。計画の確認は利用できます。再読込して結果を再確認してください。")}</p>}<h4>{say(locale, "Execution and outputs", "実行と出力")}</h4>
        {!execution?.execution ? <p role="status">{say(locale, "No confirmed execution is available for this version. Approval alone does not start Python.", "この版で確認済みの実行はありません。承認だけではPythonを開始しません。")}</p> : <><p role="status"><strong>{execution.execution.source === "synthetic-fixture" ? say(locale, "Simulation", "シミュレーション") + ": " : ""}{terminalText[execution.execution.state]?.[locale === "en" ? 0 : 1]}</strong></p>
          {execution.execution.cancel_requested && activeState(execution.execution.state) && <p>{say(locale, "Cancellation is requested. Wait for a verified terminal observation before treating the process as stopped.", "キャンセル要求済みです。停止済みと判断する前に、検証された終了観測を待ってください。")}</p>}
          {execution.execution.source === "retained-operator" && execution.execution.termination_verified && <p>{say(locale, "The service retains a verified termination reference. Scientific approval remains unverified.", "サービスに検証済みの終了参照があります。科学的な承認は未検証のままです。")}</p>}
          <button className="button secondary" disabled={blocked || !props.canCancel || !execution.capability.cancel_enabled || !activeState(execution.execution.state) || execution.execution.cancel_requested} onClick={() => void cancel()}>{say(locale, "Request cancellation", "キャンセルを要求")}</button>
          <ol className="re-events">{executionEvents?.items.map(item => <li key={item.cursor}>{item.summary[locale]}</li>)}</ol><div className="re-pager"><button className="button secondary" disabled={busy || !eventPrevious.length} onClick={() => { const values = [...eventPrevious]; setEventAfter(values.pop() ?? 0); setEventPrevious(values); }}>{say(locale, "Earlier activity", "前の履歴")}</button><button className="button secondary" disabled={busy || !executionEvents?.has_more} onClick={() => { if (executionEvents) { setEventPrevious([...eventPrevious, eventAfter]); setEventAfter(executionEvents.next_cursor); } }}>{say(locale, "More activity", "次の履歴")}</button></div>
          {execution.execution.artifacts.length > 0 && <><h4>{say(locale, "Validated outputs", "検証済みの出力")}</h4><ul>{execution.execution.artifacts.map(artifact => <li key={artifact.id}><strong>{artifact.name}</strong> · {artifact.size_bytes.toLocaleString(locale === "en" ? "en" : "ja")} bytes<div className="rw-actions"><button className="button secondary" disabled={blocked || !execution.capability.artifacts_enabled} onClick={() => void output(artifact, false)}>{say(locale, "Inspect output", "出力を確認")}</button><button className="button secondary" disabled={blocked || !props.canExport || !execution.capability.artifacts_enabled} onClick={() => void output(artifact, true)}>{say(locale, "Download result bundle", "結果一式をダウンロード")}</button><button className="button secondary" disabled={blocked || !artifact.attachment_reference || !props.canAttach} onClick={() => void attach(artifact)}>{say(locale, "Attach experimental evidence", "実験エビデンスを追加")}</button></div></li>)}</ul></>}
        </>}
        <p className="muted small">{say(locale, "Starting real execution is unavailable in this service configuration. Beta hosting, queue and worker integration remain separate gates.", "このサービス設定では実際の実行を開始できません。ベータ版のホスティング・キュー・ワーカーの統合は別途必要です。")}</p>
        {downloadBytes !== null && <p role="status">{say(locale, "Received bytes; verifying the complete file", "受信バイト数・ファイル全体を検証中")}: {downloadBytes.toLocaleString()}</p>}
        {preview && <section aria-label={say(locale, "Experimental output preview", "実験出力のプレビュー")}><h4>{preview.artifact.name}</h4><p>{say(locale, "Experimental · not independently scientifically verified", "実験的・独立した科学的検証なし")}</p>{preview.image && <img className="re-artifact-image" src={preview.image} alt={say(locale, "Validated experimental raster plot", "検証済みの実験ラスタープロット")} />}{preview.table && <><p>{preview.table.rows.length} / {preview.table.total_rows} {say(locale, "rows shown", "行を表示")}{preview.table.truncated ? " · " + say(locale, "Preview only", "プレビューのみ") : ""}</p><div className="re-table-wrap"><table><caption>{say(locale, "Validated table preview; exact machine bytes remain in the result bundle", "検証済みの表プレビュー。正確な機械バイトは結果一式に保持されます")}</caption><thead><tr>{preview.table.columns.map((name, index) => <th key={index} scope="col">{name}</th>)}</tr></thead><tbody>{preview.table.rows.map((row, index) => <tr key={index}>{row.map((cell, column) => <td key={column}>{cell ?? "—"}</td>)}</tr>)}</tbody></table></div></>}</section>}
      </section></>}
  </section>;
}
function bytesBase64(bytes: Uint8Array) { const parts: string[] = []; for (let at = 0; at < bytes.length; at += 8192) parts.push(String.fromCharCode(...bytes.subarray(at, at + 8192))); return btoa(parts.join("")); }
function downloadBlob(text: string, filename: string, mediaType: string) { const url = URL.createObjectURL(new Blob([text], { type: mediaType })), link = document.createElement("a"); link.href = url; link.download = filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
