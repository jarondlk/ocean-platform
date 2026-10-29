/** Memory-only review recovery and URL selection. No private requests in storage. */
import { ExperimentClientError, experimentJson, experimentCanonical, freezeExperimentValue } from "./experiment-http.ts";
import type { ExperimentSnapshot, ExperimentContextBinding, ExperimentEventsResponse, ExperimentEvent } from "./experiment-contract.ts";
import type { ExperimentRequests, ExperimentMutationIntent } from "./experiment-service.ts";
import { sameExperimentBinding } from "./experiment-service.ts";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$(?![\s\S])/;
const hash = /^[a-f0-9]{64}$(?![\s\S])/;
const fail = (): never => { throw new ExperimentClientError("invalid_state", "Review the current experiment before continuing", 409); };
const integer = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
export function assertExperimentBinding(binding: ExperimentContextBinding): void {
  if (!binding || Object.keys(binding).sort().join(",") !== "context_payload_sha256,context_revision_id,conversation_id,investigation_id,snapshot_id"
    || !uuid.test(binding.investigation_id) || !uuid.test(binding.conversation_id) || !uuid.test(binding.context_revision_id)
    || !hash.test(binding.snapshot_id) || !hash.test(binding.context_payload_sha256)) return fail();
}
export function experimentDecision(snapshot: ExperimentSnapshot, idempotencyKey: string): ExperimentRequests["approve"] {
  assertExperimentBinding(snapshot.binding);
  if (!uuid.test(idempotencyKey) || !uuid.test(snapshot.id) || !uuid.test(snapshot.proposal_revision_id) || !integer(snapshot.version) || snapshot.version < 1
    || snapshot.execution_performed !== false || Object.keys(snapshot.hashes).sort().join(",") !== "code_sha256,environment_sha256,input_manifest_sha256,proposal_sha256,resources_sha256"
    || Object.values(snapshot.hashes).some(value => !hash.test(value))) return fail();
  return freezeExperimentValue({ ...snapshot.binding, experiment_id: snapshot.id, expected_version: snapshot.version,
    expected_proposal_revision_id: snapshot.proposal_revision_id, expected_hashes: { ...snapshot.hashes }, idempotency_key: idempotencyKey });
}
export class ExperimentSession {
  private access: string | null = null;
  private epoch = 0;
  private readonly pending = new Map<string, ExperimentMutationIntent>();
  get generation(): number { return this.epoch; }
  bind(accessKey: string | null): void {
    if (accessKey !== null && (typeof accessKey !== "string" || !accessKey || !accessKey.isWellFormed() || accessKey.length > 8192)) return fail();
    if (this.access !== accessKey) { this.pending.clear(); this.epoch++; this.access = accessKey; }
  }
  clear(): void { this.pending.clear(); this.access = null; this.epoch++; }
  isCurrent(accessKey: string, generation: number): boolean { return this.access !== null && this.access === accessKey && this.epoch === generation; }
  private slot(binding: ExperimentContextBinding): string {
    if (this.access === null) return fail(); assertExperimentBinding(binding); return `${binding.investigation_id}/${binding.conversation_id}`;
  }
  getPending(binding: ExperimentContextBinding): ExperimentMutationIntent | null { return this.pending.get(this.slot(binding)) ?? null; }
  rememberPending(binding: ExperimentContextBinding, intent: ExperimentMutationIntent): void {
    const slot = this.slot(binding), copied = experimentJson(intent) as ExperimentMutationIntent;
    if (!copied || Object.keys(copied).sort().join(",") !== "binding,method,request" || !["create", "revise", "approve", "dispatch", "retry"].includes(copied.method)) return fail();
    assertExperimentBinding(copied.binding);
    if (!sameExperimentBinding(binding, copied.binding) || !copied.request || new TextEncoder().encode(JSON.stringify(copied.request)).byteLength > 65536) return fail();
    if (copied.method === "retry" ? !uuid.test(copied.request.operation_id) : !uuid.test(copied.request.idempotency_key)) return fail();
    if (copied.method !== "retry" && !sameExperimentBinding(binding, copied.request)) return fail();
    const previous = this.pending.get(slot);
    if (previous && experimentCanonical(previous) !== experimentCanonical(copied) || !previous && this.pending.size >= 64) return fail();
    this.pending.set(slot, freezeExperimentValue(copied));
  }
  forgetPending(binding: ExperimentContextBinding, intent: ExperimentMutationIntent): void {
    const slot = this.slot(binding), previous = this.pending.get(slot);
    if (previous && experimentCanonical(previous) === experimentCanonical(intent)) this.pending.delete(slot);
  }
}
export type ExperimentSelection = { experiment_id: string; proposal_revision_id: string | null };
export function parseExperimentSelection(search: string): ExperimentSelection | null {
  const query = new URLSearchParams(search), experiment = query.get("experiment"), proposal = query.get("proposal");
  if (query.getAll("experiment").length > 1 || query.getAll("proposal").length > 1 || !experiment || !uuid.test(experiment) || proposal !== null && !uuid.test(proposal)) return null;
  return { experiment_id: experiment, proposal_revision_id: proposal };
}
export function experimentSelectionUrl(search: string, selection: ExperimentSelection | null): string {
  const query = new URLSearchParams(search); query.delete("experiment"); query.delete("proposal");
  if (selection) {
    if (!uuid.test(selection.experiment_id) || selection.proposal_revision_id !== null && !uuid.test(selection.proposal_revision_id)) return fail();
    query.set("experiment", selection.experiment_id); if (selection.proposal_revision_id) query.set("proposal", selection.proposal_revision_id);
  }
  const result = query.toString(); return result ? "?" + result : "";
}
function scope(search: string): string | null {
  const query = new URLSearchParams(search), investigation = query.get("investigation"), conversation = query.get("conversation");
  if (query.getAll("view").length > 1 || query.getAll("investigation").length !== 1 || query.getAll("conversation").length !== 1
    || query.has("view") && query.get("view") !== "research" || !investigation || !conversation || !uuid.test(investigation) || !uuid.test(conversation)) return null;
  return `${investigation}/${conversation}`;
}
export function reconcileExperimentSelection(previousSearch: string, nextSearch: string): string {
  const previous = scope(previousSearch), next = scope(nextSearch), query = new URLSearchParams(nextSearch);
  const explicit = query.has("experiment") || query.has("proposal");
  return experimentSelectionUrl(nextSearch, previous && previous === next ? parseExperimentSelection(explicit ? nextSearch : previousSearch) : null);
}
export type ExperimentReviewHistory = { snapshot: ExperimentSnapshot; event_cursor: number; events: readonly ExperimentEvent[] };
export function mergeExperimentEvents(history: ExperimentReviewHistory, page: ExperimentEventsResponse): ExperimentReviewHistory {
  if (page.experiment_id !== history.snapshot.id || page.after_cursor !== history.event_cursor || page.next_cursor !== page.after_cursor + page.items.length
    || page.latest_event_cursor < page.next_cursor || page.latest_event_cursor < history.snapshot.latest_event_cursor || page.has_more !== (page.next_cursor < page.latest_event_cursor) || page.has_more && !page.items.length
    || page.items.some((item, index) => item.cursor !== page.after_cursor + index + 1)) return fail();
  return freezeExperimentValue({ snapshot: { ...history.snapshot, latest_event_cursor: Math.max(history.snapshot.latest_event_cursor, page.latest_event_cursor) },
    event_cursor: page.next_cursor, events: [...history.events, ...page.items] });
}
export function mergeExperimentSnapshot(previous: ExperimentSnapshot | undefined, snapshot: ExperimentSnapshot): ExperimentSnapshot {
  if (previous && (previous.id !== snapshot.id || previous.binding.investigation_id !== snapshot.binding.investigation_id || previous.binding.conversation_id !== snapshot.binding.conversation_id
    || snapshot.version < previous.version || snapshot.latest_event_cursor < previous.latest_event_cursor
    || previous.proposal_revision_id !== snapshot.proposal_revision_id && snapshot.version <= previous.version
    || previous.proposal_revision_id === snapshot.proposal_revision_id && (!sameExperimentBinding(previous.binding, snapshot.binding)
      || experimentCanonical(previous.hashes) !== experimentCanonical(snapshot.hashes) || experimentCanonical(previous.proposal) !== experimentCanonical(snapshot.proposal)))) return fail();
  return snapshot;
}
