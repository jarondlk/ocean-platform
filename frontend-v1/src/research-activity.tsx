"use client";

import { useId, useState } from "react";
import type { Locale } from "./model";
import { canCancelRun, canContinueRun, formatActiveElapsed, isRunActive, type ResearchRun, type ResearchRunStatus, type RunEvidence } from "./research-run-contract";
import "./research-activity.css";

const say = (locale: Locale, en: string, ja: string) => locale === "en" ? en : ja;
const statuses: Record<ResearchRunStatus, readonly [string, string]> = {
  queued: ["Queued", "待機中"], running: ["Running", "実行中"], awaiting_clarification: ["Awaiting clarification", "確認待ち"], awaiting_approval: ["Awaiting approval", "承認待ち"],
  completed: ["Completed", "完了"], partial: ["Partial output", "途中結果"], failed: ["Failed", "失敗"], cancelled: ["Cancelled", "キャンセル済み"],
};
const authorities = { published: ["Published analysis", "公開済みの解析"], descriptive: ["Descriptive query", "記述的なクエリ"], experimental: ["Experimental output", "実験的な出力"] } as const;
type EvidenceAction = (evidence: RunEvidence, run: ResearchRun) => void;
export type ResearchActivityProps = {
  locale: Locale; runs: readonly ResearchRun[]; busy?: boolean; executionAvailable?: boolean;
  onStatus?: (run: ResearchRun) => void; onEvents?: (run: ResearchRun) => void;
  onCancel?: (run: ResearchRun) => void; onClarify?: (run: ResearchRun, answer: string) => void;
  onContinue?: (run: ResearchRun) => void; onOpenEvidence?: EvidenceAction;
};

/** Controlled presentation. Handlers and actual transport stay with the owner. */
export function ResearchActivity({ locale, runs, busy = false, executionAvailable = false, onStatus, onEvents, onCancel, onClarify, onContinue, onOpenEvidence }: ResearchActivityProps) {
  return <section className="ra-activity" aria-label={say(locale, "Conversation activity", "会話の実行履歴")}>
    {!executionAvailable && <p className="ra-unavailable" role="status">{say(locale, "Research execution is unavailable. You can still review saved activity.", "リサーチの実行は利用できません。保存された履歴は確認できます。")}</p>}
    {runs.length === 0 ? <div className="ra-empty"><h3>{say(locale, "No submitted activity", "実行履歴はありません")}</h3><p>{say(locale, "Review the snapshot, attachments and restrictions before a future submission. No result has been generated.", "送信する前にスナップショット、添付、制約を確認してください。結果はまだ生成されていません。")}</p></div>
      : <ol className="ra-runs">{runs.map((run) => <li key={run.id}><RunCard {...{ locale, run, busy, onStatus, onEvents, onCancel, onClarify, onContinue, onOpenEvidence }} /></li>)}</ol>}
  </section>;
}

function RunCard({ locale, run, busy, onStatus, onEvents, onCancel, onClarify, onContinue, onOpenEvidence }: Omit<ResearchActivityProps, "runs" | "executionAvailable"> & { run: ResearchRun }) {
  const [answer, setAnswer] = useState(""); const id = useId(); const index = locale === "en" ? 0 : 1;
  const active = isRunActive(run.status); const waiting = run.status === "awaiting_clarification"; const approval = run.status === "awaiting_approval";
  return <article className="ra-run" data-run-id={run.id} data-status={run.status}>
    <header><h3>{run.question}</h3><span className="ra-status" role="status">{statuses[run.status][index]}</span></header>
    {run.synthetic && <p className="ra-synthetic">{say(locale, "Synthetic development activity · test data", "合成された開発用の処理・テストデータ")}</p>}
    <div className="ra-run-meta"><span>{say(locale, "Active elapsed time", "実行時間")}: <time>{formatActiveElapsed(run.active_elapsed_ms)}</time>{(waiting || approval) && ` · ${say(locale, "paused while waiting", "確認待ちのため一時停止中")}`}</span><code>{run.id}</code></div>
    {approval && <p className="ra-unavailable">{say(locale, "Approval is required. Approval controls are not available here yet.", "承認が必要です。ここでは承認操作をまだ利用できません。")}</p>}
    {run.status === "completed" && !run.result && <p className="ra-unavailable">{say(locale, "Exploration finished. An answer is not available yet.", "探索が完了しました。回答はまだありません。")}</p>}
    {run.continuation_of && <p className="ra-continuation">{say(locale, "Continuation of", "継続元")}: <code>{run.continuation_of}</code></p>}
    <details className="ra-binding"><summary>{say(locale, "Submitted context — fixed for this run", "送信時の対象範囲・この実行では固定")}</summary><dl>
      {([["Snapshot", "スナップショット", run.context.binding.snapshot_id], ["Context revision", "コンテキストの版", run.context.binding.revision_id], ["Context payload SHA-256", "コンテキストのSHA-256", run.context.binding.payload_sha256], ["Investigation", "調査", run.context.binding.investigation_id], ["Conversation", "会話", run.context.binding.conversation_id]] as const).map(([en, ja, value]) => <div key={en}><dt>{say(locale, en, ja)}</dt><dd><code>{value}</code></dd></div>)}
      <div><dt>{say(locale, "Attachments / pins", "添付 / 固定した制約")}</dt><dd>{run.context.attachments.length} / {run.context.pins.length}</dd></div>
    </dl><pre>{JSON.stringify({ scope: run.context.scope, attachments: run.context.attachments, pins: run.context.pins }, null, 2)}</pre></details>
    <details className="ra-public-events"><summary>{say(locale, "Public activity", "公開された処理状況")} ({run.activity.length})</summary><ol>{run.activity.map((event) => <li key={event.cursor}><time>{formatActiveElapsed(event.elapsed_ms)}</time><span>{event.summary[locale]}</span></li>)}</ol></details>
    {run.latest_event_cursor !== undefined && run.event_cursor < run.latest_event_cursor && <p className="ra-unavailable">{say(locale, `Showing ${run.event_cursor} of ${run.latest_event_cursor} saved activity updates. Check activity to load more.`, `保存された処理状況${run.latest_event_cursor}件のうち${run.event_cursor}件を表示しています。「処理状況を確認」で追加の状況を読み込めます。`)}</p>}
    {run.error && <p className="ra-error" role="alert">{run.error[locale]}</p>}
    {run.status === "partial" && <p className="ra-partial">{say(locale, "This output is incomplete. Its limitations remain part of the result.", "これは途中結果です。制約を含めて確認してください。")}</p>}
    {run.status === "cancelled" && <p className="ra-unavailable">{say(locale, "Activity stopped. Cancellation does not turn partial output into a complete result.", "処理は停止しました。キャンセルしても途中結果が完了した結果になることはありません。")}</p>}
    {active && !run.result && <p className="ra-unavailable">{say(locale, "No output is available yet.", "出力はまだありません。")}</p>}
    {run.result && <ResultBody {...{ locale, run, onOpenEvidence }} />}
    <div className="ra-controls">
      <button type="button" className="button subtle" disabled={busy || !onStatus} onClick={() => onStatus?.(run)}>{say(locale, "Check status", "状態を確認")}</button>
      <button type="button" className="button subtle" disabled={busy || !onEvents} onClick={() => onEvents?.(run)}>{say(locale, "Check activity", "処理状況を確認")}</button>
      {canCancelRun(run.status) && <button type="button" className="button subtle" disabled={busy || !onCancel} onClick={() => onCancel?.(run)}>{say(locale, "Cancel activity", "処理をキャンセル")}</button>}
      {canContinueRun(run.status) && <button type="button" className="button subtle" disabled={busy || !onContinue} onClick={() => onContinue?.(run)}>{say(locale, "Continue with submitted context", "送信時の対象範囲で継続")}</button>}
    </div>
    {waiting && <form className="ra-clarification" onSubmit={(event) => { event.preventDefault(); if (answer.trim() && onClarify && !busy) { onClarify(run, answer); setAnswer(""); } }}><label htmlFor={id}>{run.clarification?.[locale] ?? say(locale, "Clarification required", "確認事項があります")}</label><textarea id={id} value={answer} maxLength={8000} disabled={busy || !onClarify} onChange={(event) => setAnswer(event.target.value)} /><button className="button" type="submit" disabled={busy || !onClarify || !answer.trim()}>{say(locale, "Send clarification", "確認への回答を送信")}</button></form>}
  </article>;
}

function ResultBody({ locale, run, onOpenEvidence }: { locale: Locale; run: ResearchRun; onOpenEvidence?: EvidenceAction }) {
  const result = run.result; if (!result) return null;
  return <div className="ra-result" data-complete={result.complete}>
    <p className="ra-authority">{result.kind === "published_analysis" ? say(locale, "Published analysis", "公開済みの解析") : result.kind === "experiment" ? say(locale, "Experimental output", "実験的な出力") : say(locale, "Descriptive query", "記述的なクエリ")} · {result.complete ? say(locale, "Complete output", "出力完了") : say(locale, "Incomplete output", "未完了の出力")}</p>
    <p className="ra-result-body">{result.body[locale]}</p>
    {result.evidence.length === 0 ? <p className="ra-unavailable">{say(locale, "No retained evidence is linked.", "保持されたエビデンスへのリンクはありません。")}</p> : <ol className="ra-citations">{result.evidence.map((evidence, index) => <li key={evidence.id}><button type="button" disabled={!onOpenEvidence} onClick={() => onOpenEvidence?.(evidence, run)} aria-label={`${say(locale, "Open evidence", "エビデンスを開く")} ${index + 1}: ${evidence.title[locale]}`}>[{index + 1}] {evidence.title[locale]}</button><span>{authorities[evidence.authority][locale === "en" ? 0 : 1]}{evidence.synthetic && ` · ${say(locale, "synthetic", "合成")}`}{evidence.availability !== "retained" && ` · ${say(locale, "retained artifact unavailable", "保持された成果物は利用できません")}`}</span></li>)}</ol>}
  </div>;
}

export function ResearchResults({ locale, runs, onOpenEvidence }: { locale: Locale; runs: readonly ResearchRun[]; onOpenEvidence?: EvidenceAction }) {
  if (!runs.length) return <div className="ra-empty"><h3>{say(locale, "No results", "結果はありません")}</h3><p>{say(locale, "Submitted activity and retained outputs will appear here.", "実行履歴と保持された出力をここに表示します。")}</p></div>;
  return <section className="ra-results" aria-label={say(locale, "Results", "結果")}>{runs.map((run) => <article key={run.id}><h3>{run.question}</h3><p className="ra-status">{statuses[run.status][locale === "en" ? 0 : 1]}</p>{run.synthetic && <p className="ra-synthetic">{say(locale, "Synthetic development output", "合成された開発用の出力")}</p>}{run.result ? <ResultBody {...{ locale, run, onOpenEvidence }} /> : <p className={run.error ? "ra-error" : "ra-unavailable"}>{run.error?.[locale] ?? (isRunActive(run.status) ? say(locale, "Activity is running; output is not available yet.", "処理中です。出力はまだありません。") : run.status === "awaiting_clarification" ? say(locale, "Clarification is required before activity can continue.", "処理を続ける前に確認への回答が必要です。") : run.status === "completed" ? say(locale, "Exploration finished. An answer is not available yet.", "探索が完了しました。回答はまだありません。") : run.status === "awaiting_approval" ? say(locale, "Approval is required before activity can continue.", "処理を続ける前に承認が必要です。") : run.status === "cancelled" ? say(locale, "Cancelled without output.", "出力なしでキャンセルされました。") : say(locale, "No output is available.", "出力はありません。"))}</p>}</article>)}</section>;
}

/** Evidence selection is supplied by the caller; this never reads a legacy URL. */
export function ResearchEvidence({ locale, evidence }: { locale: Locale; evidence: RunEvidence | null }) {
  if (!evidence) return <div className="ra-empty"><h3>{say(locale, "No evidence selected", "エビデンスが選択されていません")}</h3><p>{say(locale, "Open a result citation to inspect its retained identity, authority and limitations.", "結果の引用を開くと、保持された識別情報、位置付け、制約を確認できます。")}</p></div>;
  return <article className="ra-evidence"><h3>{evidence.title[locale]}</h3><p className="ra-authority">{authorities[evidence.authority][locale === "en" ? 0 : 1]}</p>{evidence.synthetic && <p className="ra-synthetic">{say(locale, "Synthetic development example", "合成された開発用の例")}</p>}<p>{evidence.qualification[locale]}</p><p className="ra-unavailable">{evidence.availability === "retained" ? say(locale, "Retained evidence identity. Its content view is not available yet.", "保持されたエビデンスの識別情報です。内容の表示はまだ利用できません。") : say(locale, "Retained artifact content is unavailable. This identity is not scientific verification.", "保持された成果物の内容は利用できません。この識別情報は科学的な検証を意味しません。")}</p><dl>
    <div><dt>{say(locale, "Snapshot", "スナップショット")}</dt><dd><code>{evidence.snapshot_id}</code></dd></div><div><dt>{say(locale, "Context revision", "コンテキストの版")}</dt><dd><code>{evidence.revision_id}</code></dd></div><div><dt>{say(locale, "Artifact", "成果物")}</dt><dd><code>{evidence.artifact_id ?? say(locale, "Unavailable", "利用不可")}</code></dd></div>
  </dl><p className="ra-qualification">{say(locale, "Publication, descriptive query output and experimental output have different authority. Publication alone does not establish independent scientific approval.", "公開済みの解析、記述的なクエリの出力、実験的な出力は異なる位置付けです。公開されていることだけで独立した科学的な承認があるとは限りません。")}</p></article>;
}
