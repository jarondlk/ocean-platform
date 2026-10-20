"use client";
import { useEffect, useRef, useState } from "react";
import { ResearchHistoryScheduler } from "./research-history-scheduler";
import { loadAnswerHistory } from "./research-answer-history";
import { answerActive, mergeAnswerSnapshot, type AnswerView } from "./research-answer-state";
import { answerAddress, executeAnswerMutation, sameAnswerBinding, type AnswerClient, type AnswerMutationIntent, type EvidenceClient } from "./research-evidence-service";
import type { AnswerJob, AnswerListResponse, EvidenceReceipt, EvidenceResponse, EvidencePageResponse, ContextReference, ResultColumn } from "./research-evidence-contract";
import { ResearchDraftStore, type AnswerSelection } from "./research-state";
import type { ResearchRun } from "./research-run-contract";
import type { Locale } from "./model";
import { downloadBlob } from "./exports";
import "./research-activity.css";

const say = (locale: Locale, en: string, ja: string) => locale === "en" ? en : ja;
const statusCode = (error: unknown): number => error !== null && typeof error === "object" && "status_code" in error && typeof error.status_code === "number" ? error.status_code : 503;
const emptySelection = (): AnswerSelection => ({ runId: null, jobId: null, receiptId: null });
const receiptAddress = (id: string) => ({ receipt_id: id, expected_sha256: id.slice("c21:receipt:".length) });
type Props = { locale: Locale; accessKey: string; investigationId: string | null; conversationId: string | null; contextRevision: string | null; drafts: ResearchDraftStore; runs: readonly ResearchRun[];
  answers?: AnswerClient; evidence?: EvidenceClient; submitEnabled: boolean; canExport: boolean; canAttach: boolean; externalBusy: boolean; onAttach: (reference: ContextReference) => Promise<boolean>; onAccessLost: () => void; onOpenEvidence: () => void };
/** Owns one set of verified state shared by Chat, Results and Evidence panels. */
export function useResearchAnswers(props: Props) {
  const { locale, drafts, answers, evidence, investigationId, conversationId } = props;
  const key = `${props.accessKey}:${investigationId}:${conversationId}`;
  const [selection, setSelection] = useState<AnswerSelection>(emptySelection), [views, setViews] = useState<AnswerView[]>([]), [discovery, setDiscovery] = useState<AnswerListResponse | null>(null);
  const [receipts, setReceipts] = useState<EvidenceReceipt[]>([]), [opened, setOpened] = useState<EvidenceResponse | null>(null), [page, setPage] = useState<EvidencePageResponse | null>(null);
  const [pages, setPages] = useState(1), [next, setNext] = useState<string | null>(null), [receiptLimit, setReceiptLimit] = useState(100), [moreReceipts, setMoreReceipts] = useState(false);
  const [offset, setOffset] = useState(0), [section, setSection] = useState<"rows" | "inputs">("rows"), [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false), [error, setError] = useState<number | null>(null), [notice, setNotice] = useState("");
  const [pending, setPending] = useState<AnswerMutationIntent | null>(null);
  const epoch = useRef(0), pollEpoch = useRef(0), mounted = useRef(false), cache = useRef<AnswerView[]>([]), scheduler = useRef<ResearchHistoryScheduler | null>(null), receiptScheduler = useRef<ResearchHistoryScheduler | null>(null), actionAbort = useRef<AbortController | null>(null);
  const actionLock = useRef(false), selectionRef = useRef(selection); selectionRef.current = selection;
  const answerPolicy = useRef<string | null>(null), receiptPolicy = useRef<{ id: string; revision: string; receipt: EvidenceReceipt } | null>(null);
  const slot = investigationId && conversationId ? `${investigationId}:${conversationId}` : null;
  const callbacks = useRef(props); callbacks.current = props;
  const clearViews = () => { cache.current = []; setViews([]); setDiscovery(null); setReceipts([]); setOpened(null); setPage(null); answerPolicy.current = null; receiptPolicy.current = null; };
  const failure = (error: unknown) => {
    const code = statusCode(error); ++epoch.current; ++pollEpoch.current; scheduler.current?.dispose(); receiptScheduler.current?.dispose(); actionAbort.current?.abort(); actionLock.current = false; setBusy(false); clearViews(); setError(code);
    if (code === 401 || code === 403) { ++epoch.current; scheduler.current?.dispose(); actionAbort.current?.abort(); drafts.clear(); setPending(null); setSelection(emptySelection()); callbacks.current.onAccessLost(); }
  };
  const select = (value: AnswerSelection) => { if (investigationId && conversationId) drafts.selectAnswer(investigationId, conversationId, value); selectionRef.current = value; setSelection(value); };
  useEffect(() => {
    mounted.current = true; ++epoch.current; actionAbort.current?.abort(); scheduler.current?.dispose(); receiptScheduler.current?.dispose(); clearViews(); setBusy(false); actionLock.current = false; setError(null); setNotice(""); setPages(1); setReceiptLimit(100); setOffset(0);
    const saved = investigationId && conversationId ? drafts.answerSelection(investigationId, conversationId) : emptySelection(); setSelection(saved); selectionRef.current = saved;
    setPending(slot ? drafts.pendingAnswerMutation(slot) : null);
    return () => { mounted.current = false; ++epoch.current; scheduler.current?.dispose(); receiptScheduler.current?.dispose(); actionAbort.current?.abort(); };
  }, [key, drafts]);
  useEffect(() => {
    if (!investigationId || !conversationId || selection.runId || !props.runs.length) return;
    const run = [...props.runs].reverse().find(item => item.status === "completed" || item.status === "partial") ?? props.runs.at(-1)!;
    select({ runId: run.id, jobId: null, receiptId: null });
  }, [key, props.runs, selection.runId]);
  useEffect(() => {
    setViews([]); setDiscovery(null); setReceipts([]); setError(null);
    if (!answers || !evidence || !investigationId || !conversationId || !selection.runId) return;
    const mine = epoch.current, runId = selection.runId, address = { investigation_id: investigationId, conversation_id: conversationId, run_id: runId };
    const current = () => mounted.current && epoch.current === mine && selectionRef.current.runId === runId;
    const poll = new ResearchHistoryScheduler({ run: async signal => {
      const tick = ++pollEpoch.current, fresh = () => { if (signal.aborted || !current() || pollEpoch.current !== tick) throw new DOMException("Cancelled", "AbortError"); };
      const result = await loadAnswerHistory({ answers, evidence, address, pages, receiptLimit, selectedJobId: selectionRef.current.jobId,
        cached: cache.current, expectedAccessRevision: answerPolicy.current, signal, isCurrent: () => current() && pollEpoch.current === tick });
      fresh(); answerPolicy.current = result.listing.access_revision; cache.current = result.views; setViews(result.views); setDiscovery(result.listing); setNext(result.next); setReceipts(result.receipts); setMoreReceipts(result.moreReceipts);
      if (result.unavailableJobId && selectionRef.current.jobId === result.unavailableJobId) select({ ...selectionRef.current, jobId: null });
    }, onFailure: error => { if (current()) failure(error); }, onTimeout: () => { if (current()) failure({ status_code: 503 }); } });
    scheduler.current = poll; if (actionLock.current || props.externalBusy) poll.pause(); poll.request();
    return () => { poll.dispose(); ++pollEpoch.current; if (scheduler.current === poll) scheduler.current = null; };
  }, [key, selection.runId, answers, evidence, pages, receiptLimit, refresh, props.contextRevision, props.externalBusy]);
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") scheduler.current?.request(); }, views.some(view => answerActive(view.job)) ? 2000 : 10000);
    const check = () => { scheduler.current?.request(); receiptScheduler.current?.request(); }; window.addEventListener("focus", check);
    return () => { clearInterval(timer); window.removeEventListener("focus", check); };
  }, [views]);
  useEffect(() => {
    setOpened(null); setPage(null); if (!evidence || !selection.receiptId) return;
    const id = selection.receiptId, mine = epoch.current, runId = selection.runId;
    const current = () => mounted.current && epoch.current === mine && selectionRef.current.runId === runId && selectionRef.current.receiptId === id;
    const poll = new ResearchHistoryScheduler({ run: async signal => {
      const opened = await evidence.open(receiptAddress(id), signal); if (!current() || signal.aborted) return;
      if (receiptPolicy.current?.id === id && (receiptPolicy.current.revision !== opened.access_revision || JSON.stringify(receiptPolicy.current.receipt) !== JSON.stringify(opened.receipt))) { receiptPolicy.current = null; throw { status_code: 409 }; }
      const result = await evidence.page({ ...receiptAddress(id), section, offset, limit: 100 }, signal); if (!current() || signal.aborted) return;
      if (result.access_revision !== opened.access_revision || JSON.stringify(result.receipt) !== JSON.stringify(opened.receipt)) throw { status_code: 409 };
      receiptPolicy.current = { id, revision: opened.access_revision, receipt: opened.receipt }; setOpened(opened); setPage(result);
    }, onFailure: error => { if (current()) failure(error); }, onTimeout: () => { if (current()) failure({ status_code: 503 }); } });
    receiptScheduler.current = poll; if (actionLock.current || props.externalBusy) poll.pause(); poll.request();
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") poll.request(); }, 10000);
    return () => { poll.dispose(); clearInterval(timer); if (receiptScheduler.current === poll) receiptScheduler.current = null; };
  }, [key, selection.receiptId, selection.runId, section, offset, evidence, refresh, props.contextRevision, props.externalBusy]);
  const openReceipt = (id: string) => { setOffset(0); setSection("rows"); select({ ...selectionRef.current, receiptId: id }); callbacks.current.onOpenEvidence(); };
  const mutate = async (intent: AnswerMutationIntent) => {
    if (!answers || !slot || actionLock.current) return; const mine = epoch.current, abort = new AbortController(); actionAbort.current?.abort(); actionAbort.current = abort;
    actionLock.current = true; setBusy(true); setError(null); scheduler.current?.pause(); receiptScheduler.current?.pause(); ++pollEpoch.current; const timer = setTimeout(() => abort.abort(), 15000);
    try {
      drafts.rememberAnswerMutation(slot, intent); setPending(intent);
      const response = await executeAnswerMutation(answers, intent, abort.signal);
      if (!mounted.current || epoch.current !== mine || abort.signal.aborted) return;
      if (!sameAnswerBinding(response.job.binding, intent.binding)) throw new Error("Answer binding changed");
      drafts.forgetAnswerMutation(slot); setPending(null); select({ ...selectionRef.current, jobId: response.job.id });
      const view = mergeAnswerSnapshot(cache.current.find(value => value.job.id === response.job.id), response.job);
      cache.current = [view]; setViews([view]); setOpened(null); setPage(null); answerPolicy.current = response.access_revision; scheduler.current?.request();
    } catch (error) { if (mounted.current && epoch.current === mine) { if (statusCode(error) < 500) { drafts.forgetAnswerMutation(slot); setPending(null); } failure(error); } }
    finally { clearTimeout(timer); if (epoch.current === mine) { actionLock.current = false; setBusy(false); scheduler.current?.resume(); receiptScheduler.current?.resume(); setRefresh(value => value + 1); } }
  };
  const prepare = () => { if (!discovery?.eligible || !props.submitEnabled || !slot || !selection.runId || pending || busy || props.externalBusy) return;
    void mutate({ method: "submit", binding: discovery.binding, request: { investigation_id: investigationId!, conversation_id: conversationId!, run_id: selection.runId, input_version: discovery.input_version, locale, idempotency_key: crypto.randomUUID() } }); };
  const cancel = (job: AnswerJob) => void mutate({ method: "cancel", binding: job.binding, request: { ...answerAddress(job), idempotency_key: crypto.randomUUID() } });
  const exportPage = async (format: "csv" | "json") => {
    if (!evidence || !opened || !props.canExport || actionLock.current || props.externalBusy) return; const mine = epoch.current, id = opened.receipt.id, abort = new AbortController(); actionAbort.current?.abort(); actionAbort.current = abort;
    actionLock.current = true; setBusy(true); scheduler.current?.pause(); receiptScheduler.current?.pause(); ++pollEpoch.current;
    const timer = setTimeout(() => abort.abort(), 15000);
    try { const result = await evidence.export({ ...receiptAddress(id), section, offset, limit: 100, format }, abort.signal);
      if (!mounted.current || epoch.current !== mine || selectionRef.current.receiptId !== id || abort.signal.aborted) return;
      if (result.access_revision !== opened.access_revision || JSON.stringify(result.receipt) !== JSON.stringify(opened.receipt)) throw { status_code: 409 }; downloadBlob(result.content_text, result.filename, result.mime_type);
    } catch (error) { if (mounted.current && epoch.current === mine) failure(error); } finally { clearTimeout(timer); if (epoch.current === mine) { actionLock.current = false; setBusy(false); scheduler.current?.resume(); receiptScheduler.current?.resume(); } }
  };
  const attach = async () => {
    if (!evidence || !opened || !props.canAttach || actionLock.current || props.externalBusy) return; const mine = epoch.current, id = opened.receipt.id, abort = new AbortController(); actionAbort.current?.abort(); actionAbort.current = abort;
    actionLock.current = true; setBusy(true); scheduler.current?.pause(); receiptScheduler.current?.pause(); ++pollEpoch.current; const timer = setTimeout(() => abort.abort(), 15000);
    try { const result = await evidence.open(receiptAddress(id), abort.signal);
      if (!mounted.current || epoch.current !== mine || selectionRef.current.receiptId !== id || abort.signal.aborted) return;
      if (result.access_revision !== opened.access_revision || JSON.stringify(result.receipt) !== JSON.stringify(opened.receipt)) throw { status_code: 409 };
      if (await callbacks.current.onAttach(result.receipt.attachment_reference) && mounted.current && epoch.current === mine) setNotice(say(locale, "Retained evidence was attached for future questions.", "次の質問に使う保持済みエビデンスを追加しました。"));
    } catch (error) { if (mounted.current && epoch.current === mine) failure(error); } finally { clearTimeout(timer); if (epoch.current === mine) { actionLock.current = false; setBusy(false); scheduler.current?.resume(); receiptScheduler.current?.resume(); } }
  };
  const controls = <section className="ra-results" aria-label={say(locale, "Answers and retained evidence", "回答と保持済みエビデンス")}>
    <h3>{say(locale, "Answers", "回答")}</h3>{!answers || !evidence ? <p>{say(locale, "Answer and evidence services are unavailable.", "回答・エビデンスサービスを利用できません。")}</p> : <>
      <label>{say(locale, "Exploration", "探索")}<select value={selection.runId ?? ""} disabled={busy || !!pending} onChange={event => { ++epoch.current; actionAbort.current?.abort(); scheduler.current?.dispose(); receiptScheduler.current?.dispose(); clearViews(); setPages(1); setOffset(0); select({ runId: event.target.value || null, jobId: null, receiptId: null }); }}><option value="">{say(locale, "Choose an exploration", "探索を選択")}</option>{props.runs.map(run => <option key={run.id} value={run.id}>{run.question}</option>)}{selection.runId && !props.runs.some(run => run.id === selection.runId) && <option value={selection.runId}>{say(locale, "Selected exploration", "選択した探索")}</option>}</select></label>
      <button type="button" className="button primary" onClick={prepare} disabled={!discovery?.eligible || !props.submitEnabled || busy || !!pending || props.externalBusy}>{say(locale, "Prepare answer", "回答を準備")}</button>
      {discovery && (!discovery.eligible || !props.submitEnabled) && <p>{discovery.reason?.[locale] ?? say(locale, "New answers are unavailable. Permitted retained evidence remains readable.", "新しい回答は利用できません。アクセス可能な保持済みエビデンスは確認できます。")}</p>}
      {pending && !busy && <div role="alert"><p>{say(locale, "The last answer action may have been saved. Retry the same request to recover it.", "前の回答操作が保存された可能性があります。同じリクエストで復旧できます。")}</p><button className="button secondary" onClick={() => void mutate(pending)}>{say(locale, "Retry last answer action", "前の回答操作を再試行")}</button></div>}
      {error && <div role="alert"><p>{say(locale, error === 409 ? "Answer or evidence access changed. Reload the current view." : "The answer or evidence could not be verified.", error === 409 ? "回答またはエビデンスのアクセス条件が変わりました。現在のビューを再読込してください。" : "回答またはエビデンスを確認できませんでした。")}</p><button className="button secondary" onClick={() => setRefresh(value => value + 1)}>{say(locale, "Reload answers and evidence", "回答・エビデンスを再読込")}</button></div>}
      {notice && <p role="status">{notice}</p>}
      {!views.length && !error && <p role="status">{say(locale, discovery ? "No prepared answer for this exploration." : "Checking saved answers…", discovery ? "この探索の回答はまだありません。" : "保存された回答を確認しています…")}</p>}
      {views.map(view => <AnswerCard key={view.job.id} locale={locale} view={view} busy={busy || !!pending || props.externalBusy} onCancel={() => cancel(view.job)} onCitation={openReceipt} receipts={receipts} />)}
      {next && pages < 20 && <button className="button secondary" disabled={busy} onClick={() => setPages(value => Math.min(20, value + 1))}>{say(locale, "More saved answers", "保存された回答をさらに表示")}</button>}
      <h4>{say(locale, "Retained evidence", "保持済みエビデンス")}</h4><ul>{receipts.map(receipt => <li key={receipt.id}><button className="text-button" onClick={() => openReceipt(receipt.id)}>{receipt.operation_id ?? receipt.observation_id}</button> · {receipt.authority}</li>)}</ul>
      {moreReceipts && receiptLimit < 2000 && <button className="button secondary" onClick={() => setReceiptLimit(value => Math.min(2000, value + 100))}>{say(locale, "More retained evidence", "保持済みエビデンスをさらに表示")}</button>}
    </>}
  </section>;
  const evidencePanel = !selection.receiptId ? <p>{say(locale, "Open an answer citation or retained evidence receipt.", "回答の引用または保持済みエビデンスを開いてください。")}</p> : !opened || !page ? <div role="status"><p>{say(locale, error ? "Retained evidence is unavailable. Reload to check current access." : "Checking retained evidence…", error ? "保持済みエビデンスを利用できません。現在のアクセス条件を再確認してください。" : "保持済みエビデンスを確認しています…")}</p>{error && <button className="button secondary" onClick={() => setRefresh(value => value + 1)}>{say(locale, "Reload evidence", "エビデンスを再読込")}</button>}</div> : <RetainedEvidence locale={locale} value={page} section={section} busy={busy || props.externalBusy} canExport={props.canExport} canAttach={props.canAttach} onSection={value => { setOffset(0); setSection(value); }} onPage={setOffset} onExport={format => void exportPage(format)} onAttach={() => void attach()} />;
  return { controls, evidencePanel, active: !!selection.receiptId };
}

export function AnswerCard({ locale, view, busy, onCancel, onCitation, receipts = [] }: { locale: Locale; view: AnswerView; busy: boolean; onCancel: () => void; onCitation: (id: string) => void; receipts?: readonly EvidenceReceipt[] }) {
  const { job } = view, answer = job.answer;
  return <article className="ra-run" data-answer-status={job.status}><header><h4>{say(locale, "Answer", "回答")} · {job.locale.toUpperCase()}</h4><span role="status">{answerStatus(job.status, locale)}</span></header>
    <p>{say(locale, "Answer preparation active time", "回答準備の実行時間")}: {Math.floor(job.active_elapsed_ms / 1000)}s</p>
    {answerActive(job) && <button type="button" className="button secondary" disabled={busy} onClick={onCancel}>{say(locale, "Cancel answer preparation", "回答準備をキャンセル")}</button>}
    {job.error && <p role="alert">{job.error[locale]}</p>}{job.status === "cancelled" && <p>{say(locale, "Answer preparation was cancelled.", "回答準備はキャンセルされました。")}</p>}
    {answer && <><p className={answer.completion === "partial" ? "ra-partial" : "ra-status"}>{say(locale, answer.completion === "partial" ? "Partial answer — unresolved work remains." : "Complete against the retained requested evidence.", answer.completion === "partial" ? "途中の回答です。未解決の作業が残っています。" : "保持された要求エビデンスに対して完了しています。")}</p>
      {answer.blocks.map(block => <section key={block.id} data-answer-kind={block.kind}><p>{[...new Set(block.receipt_ids.map(id => receipts.find(receipt => receipt.id === id)?.authority).filter(Boolean))].map(authority => authorityLabel(authority!, locale)).join(" · ")}</p><p>{block.text}</p><div>{block.receipt_ids.map((id, index) => <button key={id} type="button" className="text-button" onClick={() => onCitation(id)}>{say(locale, "Open evidence", "エビデンスを開く")} {index + 1}</button>)}</div>{block.data && <><AnswerTables locale={locale} data={block.data} /><details><summary>{say(locale, "Retained values", "保持された値")}</summary><pre>{JSON.stringify(block.data, null, 2)}</pre></details></>}</section>)}
      {answer.qualifications.map((text, index) => <p key={index} className="ra-partial">{text}</p>)}<p>{say(locale, "Structured source selections are not independent scientific verification.", "構造化されたソースの選択は、独立した科学的検証を意味しません。")}</p></>}
    <details><summary>{say(locale, "Submitted context and shared budget", "送信時の対象範囲と共有の実行予算")}</summary><pre>{JSON.stringify({ binding: job.binding, input_version: job.input_version, budget: job.budget }, null, 2)}</pre></details>
    <details><summary>{say(locale, "Answer preparation activity", "回答準備の処理状況")} ({view.event_cursor}/{job.latest_event_cursor})</summary><ol>{view.activity.map(event => <li key={event.cursor}>{event.summary[locale]}</li>)}</ol></details>
  </article>;
}
export function RetainedEvidence({ locale, value, section, busy, canExport, canAttach, onSection, onPage, onExport, onAttach }: { locale: Locale; value: EvidencePageResponse; section: "rows" | "inputs"; busy: boolean; canExport: boolean; canAttach: boolean; onSection: (section: "rows" | "inputs") => void; onPage: (offset: number) => void; onExport: (format: "csv" | "json") => void; onAttach: () => void }) {
  const receipt = value.receipt, columns = section === "rows" ? receipt.columns.map(column => ({ key: column.key, title: column.title[locale], unit: column.unit })) : [...new Set(value.rows.flatMap(row => Object.keys(row)))].map(key => ({ key, title: key, unit: null }));
  const display = (cell: unknown) => cell === null || cell === undefined ? say(locale, "Missing", "欠損") : typeof cell === "string" ? cell : JSON.stringify(cell);
  return <article className="ra-evidence"><h3>{receipt.operation_id ?? receipt.observation_id}</h3><p>{authorityLabel(receipt.authority, locale)} · {receipt.kind} · {receipt.source_completeness} · {receipt.query_completion}</p>
    <p>{say(locale, "Retained original snapshot", "保持された元のスナップショット")}: <code>{receipt.binding.snapshot_id}</code></p>
    {receipt.qualifications.map((text, index) => <p className="ra-partial" key={index}>{text}</p>)}
    <dl>{receipt.counts.map((count, index) => <div key={index}><dt>{count.entity} · {count.denominator}</dt><dd>{count.state === "known" ? count.value : say(locale, "Unknown", "不明")}{count.reason && ` · ${count.reason}`}</dd></div>)}</dl>
    <label>{say(locale, "Evidence section", "エビデンスの区分")}<select value={section} disabled={busy} onChange={event => onSection(event.target.value as "rows" | "inputs")}><option value="rows">{say(locale, "Result rows", "結果の行")}</option><option value="inputs">{say(locale, "Complete input identities", "完全な入力識別情報")}</option></select></label>
    <p>{value.rows.length} {say(locale, "shown on this page", "件をこのページに表示")} · {say(locale, "Retained section total", "保持された区分の総数")}: {value.section_total.state === "known" ? value.section_total.value : say(locale, "Unknown", "不明")}{value.section_total.reason && ` · ${value.section_total.reason}`}</p>
    <p>{say(locale, "Preview length does not establish input or result population.", "プレビューの長さは入力や結果の母集団を表しません。")}</p>
    {columns.length ? <div className="cb-table-scroll" tabIndex={0}><table><caption>{say(locale, "Retained evidence page", "保持済みエビデンスのページ")}</caption><thead><tr>{columns.map(column => <th key={column.key} scope="col">{column.title}{column.unit && ` (${column.unit})`}</th>)}</tr></thead><tbody>{value.rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column.key}>{display(row[column.key])}</td>)}</tr>)}</tbody></table></div>
      : <ol aria-label={say(locale, "Retained literal objects", "保持された元のオブジェクト")}>{value.rows.map((row, index) => <li key={index}><pre>{JSON.stringify(row, null, 2)}</pre></li>)}</ol>}
    {!value.rows.length && <p>{say(locale, value.section_total.state === "known" && value.section_total.value === 0 ? "No matching retained rows." : "No rows available on this page.", value.section_total.state === "known" && value.section_total.value === 0 ? "一致する保持行はありません。" : "このページに表示できる行はありません。")}</p>}
    <div className="ra-controls"><button className="button secondary" disabled={busy || value.offset === 0} onClick={() => onPage(Math.max(0, value.offset - 100))}>{say(locale, "Previous page", "前のページ")}</button><button className="button secondary" disabled={busy || value.next_offset === null} onClick={() => value.next_offset !== null && onPage(value.next_offset)}>{say(locale, "Next page", "次のページ")}</button>
      <button className="button secondary" disabled={busy || !canExport} onClick={() => onExport("csv")}>{say(locale, "Download page CSV", "ページのCSVをダウンロード")}</button><button className="button secondary" disabled={busy || !canExport} onClick={() => onExport("json")}>{say(locale, "Download page JSON", "ページのJSONをダウンロード")}</button>
      <button className="button secondary" disabled={busy || !canAttach} onClick={onAttach}>{say(locale, "Attach retained evidence", "保持済みエビデンスを追加")}</button></div>
    {!canExport && <p>{say(locale, "Downloads require current export permission.", "ダウンロードには現在のエクスポート権限が必要です。")}</p>}<p>{say(locale, "Attachment adds retained evidence to shared context for future questions; it does not copy answer prose or restrict inventory.", "追加は次の質問の共有コンテキストに保持済みエビデンスを加えます。回答文のコピーや一覧の制限は行いません。")}</p>
    <details><summary>{say(locale, "Operation, scope and provenance", "操作・対象範囲・来歴")}</summary><pre>{JSON.stringify(receipt, null, 2)}</pre></details>
  </article>;
}

/** Only declared host table shapes receive a table layout; all other details stay literal JSON. */
function AnswerTables({ locale, data }: { locale: Locale; data: Record<string, unknown> }) {
  const candidates = Array.isArray(data.operation_outputs) ? data.operation_outputs : [data];
  return <>{candidates.map((candidate, index) => {
    if (!candidate || typeof candidate !== "object" || !Array.isArray(candidate.rows) || !Array.isArray(candidate.columns)
      || candidate.rows.some((row: unknown) => row === null || typeof row !== "object" || Array.isArray(row))
      || candidate.columns.some((column: any) => typeof column?.key !== "string" || typeof column?.title?.en !== "string" || typeof column?.title?.ja !== "string" || column.unit != null && typeof column.unit !== "string")) return null;
    const columns = candidate.columns as ResultColumn[];
    return <div key={index} className="cb-table-scroll" tabIndex={0}><table><caption>{say(locale, "Retained row preview; page length is not the population.", "保持された行のプレビューです。ページの長さは母集団の件数ではありません。")}</caption><thead><tr>{columns.map(column => <th key={column.key} scope="col">{column.title[locale]}{column.unit && ` (${column.unit})`}</th>)}</tr></thead><tbody>{candidate.rows.map((row: Record<string, unknown>, rowIndex: number) => <tr key={rowIndex}>{columns.map(column => <td key={column.key}>{row[column.key] == null ? say(locale, "Missing", "欠損") : typeof row[column.key] === "string" ? row[column.key] as string : JSON.stringify(row[column.key])}</td>)}</tr>)}</tbody></table></div>;
  })}</>;
}

function authorityLabel(authority: string, locale: Locale): string { const labels: Record<string, readonly [string, string]> = { descriptive: ["Descriptive query", "記述的なクエリ"], published: ["Published analysis", "公開済みの解析"], experimental: ["Experimental output", "実験的な出力"], documentary: ["Source documentation", "ソース資料"] }; return labels[authority]?.[locale === "en" ? 0 : 1] ?? authority; }
function answerStatus(status: string, locale: Locale): string { const labels: Record<string, readonly [string, string]> = { queued: ["Queued", "待機中"], running: ["Preparing answer", "回答を準備中"], completed: ["Completed", "完了"], partial: ["Partial answer", "途中の回答"], failed: ["Failed", "失敗"], unavailable: ["Unavailable", "利用不可"], cancelled: ["Cancelled", "キャンセル済み"] }; return labels[status]?.[locale === "en" ? 0 : 1] ?? status; }
