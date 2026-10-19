/** C18 presentation boundary. C20 supplies production execution and authorization.
 * No transport or synthetic implementation is selected by this module.
 */
import type { EvidenceScope } from "./catalogue-contract.ts";
import type { Text } from "./model.ts";

export type RunContextBinding = Readonly<{
  investigation_id: string; conversation_id: string; revision_id: string;
  snapshot_id: string; payload_sha256: string;
}>;
export type RunReference = Readonly<{ kind: "catalogue" | "artifact"; id: string; snapshot_id: string }>;
export type RunContext = Readonly<{
  binding: RunContextBinding; scope: EvidenceScope;
  attachments: readonly RunReference[]; pins: readonly RunReference[];
}>;
export type ResearchRunStatus = "queued" | "running" | "awaiting_clarification" | "awaiting_approval" | "completed" | "partial" | "failed" | "cancelled";
export type ResearchRunAddress = Readonly<{ run_id: string; investigation_id: string; conversation_id: string }>;
export type RunEvidence = Readonly<{
  id: string; title: Text; authority: "published" | "descriptive" | "experimental";
  snapshot_id: string; revision_id: string; artifact_id: string | null;
  availability: "retained" | "unavailable"; qualification: Text;
  /** Development examples are never retained production artifacts. */
  synthetic: boolean;
}>;
export type RunResult = Readonly<{
  kind: "published_analysis" | "descriptive_query" | "experiment";
  body: Text; complete: boolean; evidence: readonly RunEvidence[];
}>;
export type RunPublicEvent = Readonly<{
  cursor: number; run_id: string; elapsed_ms: number;
  kind: "accepted" | "started" | "progress" | "clarification" | "approval" | "resumed" | "completed" | "partial" | "failed" | "cancelled";
  /** Public activity summaries only; private model reasoning has no field. */
  summary: Text;
}>;
export type ResearchRun = Readonly<{
  id: string; context: RunContext; question: string; status: ResearchRunStatus;
  active_elapsed_ms: number; event_cursor: number; activity: readonly RunPublicEvent[];
  continuation_of: string | null; clarification: Text | null;
  /** Optional only for the earlier explicit development fixture. HTTP requires these. */
  latest_event_cursor?: number; clarification_id?: string | null;
  result: RunResult | null; error: Text | null; synthetic: boolean;
}>;
export type RunEventPage = Readonly<{
  run_id: string; binding: RunContextBinding; after_cursor: number;
  next_cursor: number; events: readonly RunPublicEvent[];
  latest_event_cursor?: number; has_more?: boolean;
}>;
export type SubmitRunRequest = Readonly<{ idempotency_key: string; context: RunContext; question: string }>;
export type ClarifyRunRequest = ResearchRunAddress & Readonly<{ idempotency_key: string; answer: string; clarification_id?: string }>;
export type ContinueRunRequest = ResearchRunAddress & Readonly<{ idempotency_key: string }>;
export type CancelRunRequest = ResearchRunAddress & Readonly<{ idempotency_key?: string }>;
export type RunListRequest = Readonly<{ investigation_id: string; conversation_id: string; limit?: number; cursor?: string | null }>;
export type RunListPage = Readonly<{ items: readonly ResearchRun[]; next_cursor: string | null }>;
export interface ResearchRunTransport {
  submit(request: SubmitRunRequest, signal?: AbortSignal): Promise<ResearchRun>;
  status(request: ResearchRunAddress, signal?: AbortSignal): Promise<ResearchRun>;
  events(request: ResearchRunAddress & Readonly<{ after_cursor: number; limit?: number }>, signal?: AbortSignal): Promise<RunEventPage>;
  cancel(request: CancelRunRequest, signal?: AbortSignal): Promise<ResearchRun>;
  clarify(request: ClarifyRunRequest, signal?: AbortSignal): Promise<ResearchRun>;
  continue(request: ContinueRunRequest, signal?: AbortSignal): Promise<ResearchRun>;
  /** Durable production discovery; absent from the explicit C18 fixture. */
  list?(request: RunListRequest, signal?: AbortSignal): Promise<RunListPage>;
}
export type RunMutationIntent =
  | Readonly<{ method: "submit"; request: SubmitRunRequest }>
  | Readonly<{ method: "cancel"; request: CancelRunRequest & { idempotency_key: string }; binding: RunContextBinding }>
  | Readonly<{ method: "clarify"; request: ClarifyRunRequest; binding: RunContextBinding }>
  | Readonly<{ method: "continue"; request: ContinueRunRequest; binding: RunContextBinding }>;
export function executeRunMutation(transport: ResearchRunTransport, intent: RunMutationIntent, signal?: AbortSignal): Promise<ResearchRun> {
  switch (intent.method) {
    case "submit": return transport.submit(intent.request, signal);
    case "cancel": return transport.cancel(intent.request, signal);
    case "clarify": return transport.clarify(intent.request, signal);
    case "continue": return transport.continue(intent.request, signal);
  }
}

export class ResearchRunContractError extends Error {
  constructor(message: string) { super(message); this.name = "ResearchRunContractError"; }
}
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const sha256 = /^[a-f0-9]{64}$/;
const fail = (message: string): never => { throw new ResearchRunContractError(message); };
const integer = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
export function assertRunKey(value: string): void { if (typeof value !== "string" || !uuid.test(value)) fail("Expected a canonical UUID operation key"); }
export function assertRunText(value: string): void {
  if (typeof value !== "string" || !value.trim() || [...value].length > 8000 || /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f\ud800-\udfff]/u.test(value)) fail("Expected visible UTF-8 text of at most 8000 characters");
}
export function assertRunBinding(binding: RunContextBinding): void {
  if (!binding || Object.keys(binding).sort().join(",") !== "conversation_id,investigation_id,payload_sha256,revision_id,snapshot_id"
    || !uuid.test(binding.investigation_id) || !uuid.test(binding.conversation_id) || !uuid.test(binding.revision_id)
    || !sha256.test(binding.snapshot_id) || !sha256.test(binding.payload_sha256)) fail("Invalid immutable run context binding");
}
export function sameRunBinding(left: RunContextBinding, right: RunContextBinding): boolean {
  return left.investigation_id === right.investigation_id && left.conversation_id === right.conversation_id
    && left.revision_id === right.revision_id && left.snapshot_id === right.snapshot_id && left.payload_sha256 === right.payload_sha256;
}
function contextIdentity(context: RunContext): string {
  const canonical = (value: unknown): unknown => Array.isArray(value) ? value.map(canonical)
    : value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => [key, canonical(item)])) : value;
  return JSON.stringify(canonical(context));
}
/** JSON-only defensive copy, deeply frozen so later UI edits cannot change a run. */
export function freezeRunValue<T>(value: T): T {
  const seen = new Set<object>();
  const copy = (item: unknown, depth: number): unknown => {
    if (depth > 128) return fail("Run value nesting exceeds 128");
    if (item === null || typeof item === "boolean") return item;
    if (typeof item === "string") {
      if (/[\ud800-\udfff]/u.test(item)) return fail("Run value contains invalid UTF-8 text");
      return item;
    }
    if (typeof item === "number") return Number.isFinite(item) ? item : fail("Run value must be finite");
    if (typeof item !== "object" || seen.has(item) || (!Array.isArray(item) && ![Object.prototype, null].includes(Object.getPrototypeOf(item)))) return fail("Run value must be acyclic JSON");
    seen.add(item);
    const result = Array.isArray(item) ? Array.from(item, (child) => copy(child, depth + 1))
      : Object.fromEntries(Object.entries(item).map(([key, child]) => [key, copy(child, depth + 1)]));
    seen.delete(item); return Object.freeze(result);
  };
  return copy(value, 0) as T;
}
export function freezeRunContext(context: RunContext): RunContext {
  if (!context || Object.keys(context).sort().join(",") !== "attachments,binding,pins,scope") fail("Invalid run context fields");
  assertRunBinding(context.binding);
  for (const references of [context.attachments, context.pins]) {
    if (!Array.isArray(references) || references.length > 256) fail("Run reference collection exceeds its bound");
    const ids = new Set<string>();
    for (const reference of references) {
      if (!reference || Object.keys(reference).sort().join(",") !== "id,kind,snapshot_id"
        || !["catalogue", "artifact"].includes(reference.kind) || typeof reference.id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(reference.id)
        || !sha256.test(reference.snapshot_id)
        || (reference.kind === "catalogue" && reference.snapshot_id !== context.binding.snapshot_id)) fail("Invalid run reference");
      // C17 retained artifacts keep their own snapshot. Only catalogue selections
      // are scoped to this investigation's current scientific snapshot.
      const key = JSON.stringify([reference.kind, reference.id, reference.snapshot_id]);
      if (ids.has(key)) fail("Duplicate run reference"); ids.add(key);
    }
  }
  return freezeRunValue(context);
}
export function researchRunAddress(run: ResearchRun): ResearchRunAddress {
  return { run_id: run.id, investigation_id: run.context.binding.investigation_id, conversation_id: run.context.binding.conversation_id };
}
export function isRunActive(status: ResearchRunStatus): boolean { return status === "queued" || status === "running"; }
export function canContinueRun(status: ResearchRunStatus): boolean { return ["partial", "failed", "cancelled"].includes(status); }
export function canCancelRun(status: ResearchRunStatus): boolean { return isRunActive(status) || status === "awaiting_clarification" || status === "awaiting_approval"; }
export function formatActiveElapsed(milliseconds: number): string {
  if (!integer(milliseconds)) fail("Invalid active elapsed time");
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
/** Reject stale/reordered/gapped pages and context substitution before presentation. */
export function mergeRunEvents(run: ResearchRun, page: RunEventPage): ResearchRun {
  assertRunBinding(page.binding);
  if (page.run_id !== run.id || !sameRunBinding(run.context.binding, page.binding) || page.after_cursor !== run.event_cursor
    || !integer(page.next_cursor) || page.next_cursor !== page.after_cursor + page.events.length) fail("Run event page does not continue the accepted cursor and context");
  let cursor = run.event_cursor; let elapsed = run.activity.at(-1)?.elapsed_ms ?? 0;
  for (const event of page.events) {
    if (event.run_id !== run.id || event.cursor !== ++cursor || !integer(event.elapsed_ms) || event.elapsed_ms < elapsed
      || Object.keys(event).sort().join(",") !== "cursor,elapsed_ms,kind,run_id,summary"
      || !["accepted", "started", "progress", "clarification", "approval", "resumed", "completed", "partial", "failed", "cancelled"].includes(event.kind)
      || !event.summary || Object.keys(event.summary).sort().join(",") !== "en,ja"
      || typeof event.summary.en !== "string" || typeof event.summary.ja !== "string") fail("Invalid public run event");
    elapsed = event.elapsed_ms;
  }
  if (page.latest_event_cursor !== undefined && (!integer(page.latest_event_cursor) || page.latest_event_cursor < page.next_cursor || (run.latest_event_cursor !== undefined && page.latest_event_cursor < run.latest_event_cursor))) fail("Run event high water regressed");
  if (page.has_more !== undefined && page.has_more !== (page.next_cursor < (page.latest_event_cursor ?? page.next_cursor))) fail("Run event continuation is inconsistent");
  const latest = page.latest_event_cursor ?? run.latest_event_cursor;
  return freezeRunValue({ ...run, active_elapsed_ms: Math.max(run.active_elapsed_ms, elapsed), event_cursor: page.next_cursor, ...(latest === undefined ? {} : { latest_event_cursor: latest }), activity: [...run.activity, ...page.events] });
}
/** Fresh status may update state, never erase locally verified consecutive history. */
export function mergeRunSnapshot(previous: ResearchRun | undefined, snapshot: ResearchRun): ResearchRun {
  if (!previous) return snapshot;
  if (previous.id !== snapshot.id || !sameRunBinding(previous.context.binding, snapshot.context.binding) || contextIdentity(previous.context) !== contextIdentity(snapshot.context)
    || previous.question !== snapshot.question || previous.continuation_of !== snapshot.continuation_of
    || previous.synthetic !== snapshot.synthetic || snapshot.active_elapsed_ms < previous.active_elapsed_ms
    || (snapshot.latest_event_cursor ?? snapshot.event_cursor) < (previous.latest_event_cursor ?? previous.event_cursor)) fail("Run status changed its retained identity or regressed");
  if (snapshot.latest_event_cursor !== undefined) {
    if (snapshot.event_cursor === 0) return freezeRunValue({ ...snapshot, activity: previous.activity, event_cursor: previous.event_cursor });
    if (snapshot.event_cursor < previous.event_cursor || snapshot.activity.length !== snapshot.event_cursor
      || JSON.stringify(snapshot.activity.slice(0, previous.activity.length)) !== JSON.stringify(previous.activity)) fail("Run history cannot replace committed events");
  }
  return snapshot; // The explicit development fixture returns its complete in-memory history.
}
