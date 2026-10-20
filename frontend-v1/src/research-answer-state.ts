/** Consecutive public answer activity, kept separately from immutable wire snapshots. */
import type { AnswerEvent, AnswerJob, AnswerEventsResponse } from "./research-evidence-contract.ts";
import { freezeEvidenceValue } from "./research-evidence-contract.ts";
import { sameAnswerBinding } from "./research-evidence-service.ts";
import { ResearchEvidenceClientError } from "./research-evidence-http.ts";
export type AnswerView = { job: AnswerJob; activity: readonly AnswerEvent[]; event_cursor: number };
export const answerActive = (job: AnswerJob) => job.status === "queued" || job.status === "running";
const fail = (): never => { throw new ResearchEvidenceClientError("invalid_response", "Saved answer activity could not be verified"); };
export function mergeAnswerSnapshot(previous: AnswerView | undefined, job: AnswerJob): AnswerView {
  if (previous) {
    const before = previous.job;
    if (before.id !== job.id || before.run_id !== job.run_id || before.input_version !== job.input_version || !sameAnswerBinding(before.binding, job.binding) || before.locale !== job.locale
      || job.active_elapsed_ms < before.active_elapsed_ms || job.latest_event_cursor < before.latest_event_cursor
      || (job.budget.active_elapsed_seconds ?? 0) < (before.budget.active_elapsed_seconds ?? 0) || (job.budget.tool_actions ?? 0) < (before.budget.tool_actions ?? 0) || (job.budget.model_calls ?? 0) < (before.budget.model_calls ?? 0) || (job.budget.malformed_repairs ?? 0) < (before.budget.malformed_repairs ?? 0)
      || before.budget.cancellation_requested === true && job.budget.cancellation_requested !== true
      || !answerActive(before) && before.status !== job.status
      || before.answer !== null && JSON.stringify(before.answer) !== JSON.stringify(job.answer)) return fail();
  }
  return { job, activity: previous?.activity ?? [], event_cursor: previous?.event_cursor ?? 0 };
}
export function mergeAnswerEvents(view: AnswerView, page: AnswerEventsResponse): AnswerView {
  if (page.job_id !== view.job.id || !sameAnswerBinding(page.binding, view.job.binding) || page.after_cursor !== view.event_cursor || page.latest_event_cursor < view.job.latest_event_cursor
    || page.next_cursor !== page.after_cursor + page.events.length || page.next_cursor > page.latest_event_cursor || page.has_more !== (page.next_cursor < page.latest_event_cursor) || page.has_more && !page.events.length) return fail();
  let elapsed = view.activity.at(-1)?.elapsed_ms ?? 0;
  for (const [index, event] of page.events.entries()) { if (event.job_id !== view.job.id || event.cursor !== view.event_cursor + index + 1 || event.elapsed_ms < elapsed) return fail(); elapsed = event.elapsed_ms; }
  return freezeEvidenceValue({ job: { ...view.job, latest_event_cursor: page.latest_event_cursor }, activity: [...view.activity, ...page.events], event_cursor: page.next_cursor });
}
