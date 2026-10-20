/** Fresh, read-only answer/evidence hydration. Cached private bytes alone never authorize display. */
import { mergeAnswerEvents, mergeAnswerSnapshot, type AnswerView } from "./research-answer-state.ts";
import { sameAnswerBinding, type AnswerClient, type EvidenceClient, answerAddress } from "./research-evidence-service.ts";
import { ResearchEvidenceClientError } from "./research-evidence-http.ts";
import type { AnswerJob, AnswerListResponse, EvidenceReceipt } from "./research-evidence-contract.ts";
type Options = {
  answers: AnswerClient; evidence: EvidenceClient;
  address: { investigation_id: string; conversation_id: string; run_id: string };
  pages: number; receiptLimit: number; selectedJobId: string | null; cached: readonly AnswerView[];
  expectedAccessRevision: string | null; signal: AbortSignal; isCurrent: () => boolean;
};
const invalid = (): never => { throw new ResearchEvidenceClientError("invalid_response", "Saved answers or evidence could not be verified"); };
const changed = (): never => { throw new ResearchEvidenceClientError("conflict", "Answer access changed. Reload the current view", 409); };
export async function loadAnswerHistory(options: Options) {
  const { answers, evidence, address, signal } = options;
  const fresh = () => { if (signal.aborted || !options.isCurrent()) throw new DOMException("Cancelled", "AbortError"); };
  if (!Number.isSafeInteger(options.pages) || options.pages < 1 || options.pages > 20 || !Number.isSafeInteger(options.receiptLimit) || options.receiptLimit < 1 || options.receiptLimit > 2000) return invalid();
  const jobs: AnswerJob[] = []; let cursor: string | null = null, listing: AnswerListResponse | null = null; const cursors = new Set<string>();
  fresh();
  for (let index = 0; index < options.pages; index++) {
    const result = await answers.list({ ...address, cursor, limit: 25 }, signal); fresh();
    if (listing && (result.access_revision !== listing.access_revision || result.input_version !== listing.input_version || !sameAnswerBinding(result.binding, listing.binding))) return changed();
    listing = result;
    for (const job of result.items) { if (jobs.some(value => value.id === job.id)) return invalid(); jobs.push(job); }
    cursor = result.next_cursor; if (cursor === null) break; if (cursors.has(cursor)) return invalid(); cursors.add(cursor);
  }
  if (!listing) return invalid();
  if (options.expectedAccessRevision !== null && options.expectedAccessRevision !== listing.access_revision) return changed();
  let unavailableJobId: string | null = null;
  if (options.selectedJobId && !jobs.some(job => job.id === options.selectedJobId)) {
    try {
      const result = await answers.status({ ...address, job_id: options.selectedJobId }, signal); fresh();
      if (result.access_revision !== listing.access_revision || result.job.input_version !== listing.input_version || !sameAnswerBinding(result.job.binding, listing.binding)) return changed();
      jobs.push(result.job);
    } catch (error) { fresh(); if (!(error instanceof ResearchEvidenceClientError) || error.status_code !== 404) throw error; unavailableJobId = options.selectedJobId; }
  }
  const views: AnswerView[] = [];
  for (const job of jobs) {
    let view = mergeAnswerSnapshot(options.cached.find(value => value.job.id === job.id), job);
    for (let index = 0; index < 20 && view.event_cursor < view.job.latest_event_cursor; index++) {
      const result = await answers.events({ ...answerAddress(job), after_cursor: view.event_cursor, limit: 100 }, signal); fresh();
      if (result.access_revision !== listing.access_revision) return changed();
      view = mergeAnswerEvents(view, result);
    }
    views.push(view);
  }
  const receipts: EvidenceReceipt[] = []; let offset = 0, evidenceRevision: string | null = null, moreReceipts = false;
  while (receipts.length < options.receiptLimit) {
    const result = await evidence.list({ ...address, input_version: listing.input_version, offset, limit: Math.min(100, options.receiptLimit - receipts.length) }, signal); fresh();
    if (evidenceRevision !== null && evidenceRevision !== result.access_revision) return changed(); evidenceRevision = result.access_revision;
    for (const receipt of result.items) { if (receipts.some(value => value.id === receipt.id)) return invalid(); receipts.push(receipt); }
    moreReceipts = result.next_offset !== null; if (!moreReceipts) break;
    if (!result.items.length || result.next_offset! <= offset) return invalid(); offset = result.next_offset!;
  }
  fresh(); return { views, listing, next: cursor, receipts, moreReceipts, unavailableJobId };
}
