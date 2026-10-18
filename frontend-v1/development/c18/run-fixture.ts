/** Explicit development dependency. Never imported by a production entry point.
 * These deterministic synthetic outcomes perform no network, model or data work.
 */
import {
  assertRunKey, assertRunText, canContinueRun, freezeRunContext, freezeRunValue, isRunActive,
  type ClarifyRunRequest, type ContinueRunRequest, type ResearchRun, type ResearchRunAddress,
  type ResearchRunStatus, type ResearchRunTransport, type RunEventPage, type RunPublicEvent,
  type RunResult, type SubmitRunRequest,
} from "../../src/research-run-contract.ts";

export type C18RunScenario = "completed" | "partial" | "failed" | "clarification" | "running";
export type C18RunFixture = ResearchRunTransport & { setScenario(scenario: C18RunScenario): void };
type Stored = { run: ResearchRun; scenario: C18RunScenario; phase: number; updatedAt: number; clarified: boolean };
const text = (en: string, ja: string) => ({ en, ja });
const aborted = (signal?: AbortSignal) => { if (signal?.aborted) throw new DOMException("Aborted", "AbortError"); };

export function createC18RunFixture(options: { scenario?: C18RunScenario; now?: () => number } = {}): C18RunFixture {
  let scenario = options.scenario ?? "completed"; let sequence = 0;
  const now = options.now ?? Date.now;
  const runs = new Map<string, Stored>();
  const keys = new Map<string, { request: string; run_id: string }>();
  const clock = () => { const value = now(); if (!Number.isSafeInteger(value) || value < 0) throw new Error("Invalid synthetic clock"); return value; };
  const read = (request: ResearchRunAddress, signal?: AbortSignal) => {
    aborted(signal); const item = runs.get(request.run_id);
    if (!item || item.run.context.binding.investigation_id !== request.investigation_id || item.run.context.binding.conversation_id !== request.conversation_id) throw new Error("Synthetic run unavailable for this conversation");
    return item;
  };
  const update = (item: Stored, patch: Partial<ResearchRun>, kind?: RunPublicEvent["kind"], summary?: RunPublicEvent["summary"]) => {
    const current = clock();
    const elapsed = item.run.active_elapsed_ms + (isRunActive(item.run.status) ? Math.max(0, current - item.updatedAt) : 0);
    item.updatedAt = Math.max(current, item.updatedAt);
    const event = kind ? { cursor: item.run.event_cursor + 1, run_id: item.run.id, elapsed_ms: elapsed, kind, summary: summary! } : null;
    item.run = freezeRunValue({ ...item.run, ...patch, active_elapsed_ms: elapsed,
      ...(event ? { event_cursor: event.cursor, activity: [...item.run.activity, event] } : {}) });
    return item.run;
  };
  const idempotent = (key: string, request: unknown, perform: () => ResearchRun): ResearchRun => {
    assertRunKey(key); const serialized = JSON.stringify(request); const old = keys.get(key);
    if (old) {
      if (old.request !== serialized) throw new Error("Synthetic operation key reused with different input");
      return runs.get(old.run_id)!.run;
    }
    const value = perform(); keys.set(key, { request: serialized, run_id: value.id }); return value;
  };
  const result = (run: ResearchRun, complete: boolean): RunResult => ({
    kind: "descriptive_query", complete,
    body: text(complete ? "Synthetic descriptive result for interface verification. No scientific computation was performed." : "Synthetic partial output. Remaining work was not completed.", complete ? "画面検証用の合成された記述的な結果です。科学的な計算は行っていません。" : "合成された途中結果です。残りの処理は完了していません。"),
    evidence: [{ id: `${run.id}:evidence`, title: text("Synthetic evidence example", "合成されたエビデンス例"), authority: "descriptive",
      snapshot_id: run.context.binding.snapshot_id, revision_id: run.context.binding.revision_id, artifact_id: null,
      availability: "unavailable", synthetic: true,
      qualification: text("Development example only. No retained artifact or independent scientific approval exists.", "開発用の例です。保持された成果物や独立した科学的な承認はありません。") }],
  });
  const create = (request: SubmitRunRequest, continuation: string | null) => {
    assertRunText(request.question); const context = freezeRunContext(request.context);
    const id = `c18-synthetic-${++sequence}`;
    const item: Stored = { scenario, phase: 0, updatedAt: clock(), clarified: false, run: freezeRunValue({ id, context, question: request.question,
      status: "queued", active_elapsed_ms: 0, event_cursor: 1,
      activity: [{ cursor: 1, run_id: id, elapsed_ms: 0, kind: "accepted", summary: text("Synthetic request accepted", "合成リクエストを受理") }],
      continuation_of: continuation, clarification: null, result: null, error: null, synthetic: true }) };
    runs.set(id, item); return item.run;
  };
  return {
    setScenario(value) {
      if (!["completed", "partial", "failed", "clarification", "running"].includes(value)) throw new Error("Unknown synthetic scenario"); scenario = value;
    },
    async submit(request, signal) {
      aborted(signal); return idempotent(request.idempotency_key, ["submit", request], () => create(request, null));
    },
    async status(request, signal) {
      const item = read(request, signal);
      if (!isRunActive(item.run.status)) return item.run;
      if (item.phase++ === 0) return update(item, { status: "running" }, "started", text("Synthetic activity started", "合成された処理を開始"));
      if (item.scenario === "running") return update(item, {}, "progress", text("Synthetic activity remains running", "合成された処理を実行中"));
      if (item.scenario === "clarification" && !item.clarified) return update(item, { status: "awaiting_clarification", clarification: text("Synthetic clarification: confirm the intended comparison.", "合成された確認事項：比較の対象を確認してください。") }, "clarification", text("Waiting for clarification; active time is paused", "確認待ち：実行時間の計測を一時停止"));
      const status: ResearchRunStatus = item.scenario === "failed" ? "failed" : item.scenario === "partial" ? "partial" : "completed";
      return update(item, { status, result: status === "failed" ? null : result(item.run, status === "completed"), error: status === "failed" ? text("Synthetic execution failure. No result is available.", "合成された実行エラーです。結果はありません。") : null }, status, text(`Synthetic activity ${status}`, status === "failed" ? "合成された処理が失敗" : status === "partial" ? "合成された処理が一部完了" : "合成された処理が完了"));
    },
    async events(request, signal): Promise<RunEventPage> {
      const item = read(request, signal);
      if (!Number.isSafeInteger(request.after_cursor) || request.after_cursor < 0 || request.after_cursor > item.run.event_cursor) throw new Error("Invalid synthetic event cursor");
      return freezeRunValue({ run_id: item.run.id, binding: item.run.context.binding, after_cursor: request.after_cursor,
        next_cursor: item.run.event_cursor, events: item.run.activity.filter((event) => event.cursor > request.after_cursor) });
    },
    async cancel(request, signal) {
      const item = read(request, signal);
      if (!isRunActive(item.run.status) && item.run.status !== "awaiting_clarification") return item.run;
      return update(item, { status: "cancelled", clarification: null }, "cancelled", text("Synthetic activity cancelled", "合成された処理をキャンセル"));
    },
    async clarify(request: ClarifyRunRequest, signal) {
      const item = read(request, signal); assertRunText(request.answer);
      return idempotent(request.idempotency_key, ["clarify", request], () => {
        if (item.run.status !== "awaiting_clarification") throw new Error("Synthetic run is not awaiting clarification");
        item.clarified = true; item.updatedAt = clock();
        return update(item, { status: "running", clarification: null }, "resumed", text("Synthetic activity resumed with clarification", "確認後、合成された処理を再開"));
      });
    },
    async continue(request: ContinueRunRequest, signal) {
      const item = read(request, signal);
      return idempotent(request.idempotency_key, ["continue", request], () => {
        if (!canContinueRun(item.run.status)) throw new Error("Synthetic run cannot be continued in its current state");
        return create({ idempotency_key: request.idempotency_key, context: item.run.context, question: item.run.question }, item.run.id);
      });
    },
  };
}
