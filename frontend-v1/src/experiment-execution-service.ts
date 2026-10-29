/** C25 bounded execution projections. No request launches or proves termination. */
import { executionContractSchema, type ExecutionModels } from "./generated/experiment-execution.generated.ts";
import { validateExperimentSchema, type ExperimentRule, type ExperimentSnapshot, type ExperimentContextBinding } from "./experiment-contract.ts";
import { ExperimentClientError, createExperimentHttp, experimentJson, freezeExperimentValue, experimentCanonical, type ExperimentHttpOptions } from "./experiment-http.ts";
import { assertExperimentBinding } from "./experiment-state.ts";

type Complete<T> = T extends (infer U)[] ? Complete<U>[] : T extends object ? { [K in keyof T]-?: Complete<T[K]> } : T;
export type ExecutionResponse = Complete<ExecutionModels["ExecutionResponse"]>;
export type ExecutionSnapshot = Complete<ExecutionModels["ExecutionSnapshot"]>;
export type ExecutionArtifact = Complete<ExecutionModels["ExecutionArtifact"]>;
export type ExecutionArtifactResponse = Complete<ExecutionModels["ExecutionArtifactResponse"]>;
export type ExecutionEventsResponse = Complete<ExecutionModels["ExecutionEventsResponse"]>;
export type ExecutionCancelResponse = Complete<ExecutionModels["ExecutionCancelResponse"]>;
export type ExecutionCapabilityResponse = Complete<ExecutionModels["ExecutionCapabilityResponse"]>;
export type ExecutionRequests = {
  capability: ExecutionModels["ExecutionCapabilityRequest"]; status: ExecutionModels["ExecutionStatusRequest"];
  events: ExecutionModels["ExecutionEventsRequest"]; cancel: ExecutionModels["ExecutionCancelRequest"];
  artifact: ExecutionModels["ExecutionArtifactRequest"];
};
export type ExecutionResponses = { capability: ExecutionCapabilityResponse; status: ExecutionResponse; events: ExecutionEventsResponse; cancel: ExecutionCancelResponse; artifact: ExecutionArtifactResponse };
export type ExperimentExecutionClient = { [K in keyof ExecutionRequests]: (request: ExecutionRequests[K], signal?: AbortSignal) => Promise<ExecutionResponses[K]> };
export type PendingExecutionCancel = Readonly<{ request: ExecutionRequests["cancel"]; binding: ExperimentContextBinding }>;
const defs = executionContractSchema.$defs as unknown as Record<string, ExperimentRule>;
const terminal = (state: string) => ["completed", "failed", "cancelled", "timed_out"].includes(state);
const invalid = (): never => { throw new ExperimentClientError("invalid_response", "The execution or artifact response could not be verified"); };
export function sameExecutionBinding(a: ExperimentContextBinding, b: ExperimentContextBinding) { return a.investigation_id === b.investigation_id && a.conversation_id === b.conversation_id && a.context_revision_id === b.context_revision_id && a.snapshot_id === b.snapshot_id && a.context_payload_sha256 === b.context_payload_sha256; }
export function executionRequest(value: ExperimentSnapshot) {
  return { experiment_id: value.id, ...value.binding, expected_version: value.version, expected_proposal_revision_id: value.proposal_revision_id, expected_hashes: value.hashes };
}
function semantics(name: string, value: any) {
  if (name === "ExecutionCapability") {
    if (value.start_enabled !== false || (value.transport === "unavailable" ? value.source !== "unavailable" || value.cancel_enabled || value.artifacts_enabled || value.reason === null : value.source === "unavailable" || value.reason !== null)) return invalid();
  }
  if (name === "ExecutionArtifact") {
    if ((value.kind === "raster" ? value.media_type !== "image/png" || !value.name.endsWith(".png") : value.media_type === "image/png" || !value.name.endsWith(value.media_type === "text/csv" ? ".csv" : ".json"))
      || value.attachment_reference !== null && value.attachment_reference.kind !== "artifact") return invalid();
  }
  if (name === "ExecutionSnapshot") {
    if (value.event_cursor !== 0 || value.latest_event_cursor < value.event_cursor
      || value.termination_verified !== (value.termination_proof_sha256 !== null) || value.termination_verified && !terminal(value.state)
      || value.source === "synthetic-fixture" && (value.execution_performed || value.termination_verified || value.termination_proof_sha256 !== null)
      || value.source === "retained-operator" && terminal(value.state) && (!value.termination_verified || value.termination_proof_sha256 === null)
      || value.source === "retained-operator" && value.state === "completed" && !value.execution_performed
      || value.state === "cancelling" && !value.cancel_requested
      || value.artifacts.length && (value.state !== "completed" || value.outputs_manifest_sha256 === null)
      || new Set(value.artifacts.map((a: any) => a.id)).size !== value.artifacts.length || new Set(value.artifacts.map((a: any) => a.name)).size !== value.artifacts.length
      || value.artifacts.reduce((n: number, a: any) => n + a.size_bytes, 0) > 50 * 1024 ** 2) return invalid();
  }
  if (name === "TablePreview" && (value.rows.some((r: any) => !Array.isArray(r) || r.length !== value.columns.length) || value.rows.length > value.total_rows || value.truncated !== (value.rows.length < value.total_rows))) return invalid();
  if (name === "ExecutionEventsResponse" && (value.execution === null || value.execution.id !== value.execution_id
    || value.next_cursor !== value.after_cursor + value.items.length || value.next_cursor > value.latest_event_cursor
    || value.latest_event_cursor !== value.execution.latest_event_cursor
    || value.has_more !== (value.next_cursor < value.latest_event_cursor) || value.has_more && !value.items.length
    || value.items.some((item: any, index: number) => item.cursor !== value.after_cursor + index + 1))) return invalid();
  if (name === "CancellationAcknowledgement" && value.termination_confirmed !== false) return invalid();
  if (["ExecutionResponse", "ExecutionEventsResponse", "ExecutionCancelResponse", "ExecutionArtifactResponse"].includes(name)
    && value.execution && (value.capability.source !== value.execution.source
      || value.execution.artifacts.some((a: ExecutionArtifact) => a.attachment_reference !== null && a.attachment_reference.snapshot_id !== value.binding.snapshot_id))) return invalid();
  if (name === "ExecutionCancelResponse" && (!value.execution || value.cancellation.status === "requested" && !value.execution.cancel_requested
    || value.cancellation.status === "already_terminal" && !terminal(value.execution.state))) return invalid();
  if (name === "ExecutionArtifactResponse") {
    const bytes = decodeArtifactChunk(value.content_base64);
    if (value.next_offset !== value.offset + bytes.length || value.next_offset > value.artifact.size_bytes
      || value.eof !== (value.next_offset === value.artifact.size_bytes) || !bytes.length && !value.eof || bytes.length > 256 * 1024
      || !value.execution || !value.execution.artifacts.some((item: ExecutionArtifact) => experimentCanonical(item) === experimentCanonical(value.artifact))
      || value.preview !== null && (value.offset !== 0 || value.artifact.kind !== "table")) return invalid();
  }
}
export function parseExecutionModel<K extends keyof ExecutionModels>(name: K, supplied: unknown, response = true): ExecutionModels[K] {
  const value = experimentJson(supplied);
  const rule = defs[name as string]; if (!rule) return invalid();
  validateExperimentSchema(defs, rule, value, response, 0, semantics); semantics(name as string, value);
  return freezeExperimentValue(value) as ExecutionModels[K];
}
const models = { capability: ["ExecutionCapabilityRequest", "ExecutionCapabilityResponse"], status: ["ExecutionStatusRequest", "ExecutionResponse"], events: ["ExecutionEventsRequest", "ExecutionEventsResponse"], cancel: ["ExecutionCancelRequest", "ExecutionCancelResponse"], artifact: ["ExecutionArtifactRequest", "ExecutionArtifactResponse"] } as const;
async function verifyReply(action: keyof ExecutionRequests, input: any, supplied: unknown, signal?: AbortSignal): Promise<any> {
  if (signal?.aborted) throw new DOMException("The execution request was cancelled", "AbortError");
  const result: any = parseExecutionModel(models[action][1], supplied);
  if (action !== "capability") {
    if (result.experiment_id !== input.experiment_id || result.proposal_revision_id !== input.expected_proposal_revision_id
      || result.proposal_version !== input.expected_version || !sameExecutionBinding(result.binding, input)
      || experimentCanonical(result.hashes) !== experimentCanonical(input.expected_hashes)
      || input.execution_id != null && (!result.execution || result.execution.id !== input.execution_id)) return invalid();
  }
  if (action === "events" && (result.execution_id !== input.execution_id || result.after_cursor !== (input.after_cursor ?? 0) || result.items.length > (input.limit ?? 100) || result.latest_event_cursor !== result.execution.latest_event_cursor)) return invalid();
  if (action === "cancel" && result.cancellation.idempotency_key !== input.idempotency_key) return invalid();
  if (action === "artifact") {
    const artifact = result.artifact as ExecutionArtifact;
    if (artifact.id !== input.artifact_id || artifact.sha256 !== input.expected_sha256 || result.offset !== (input.offset ?? 0)) return invalid();
    const bytes = decodeArtifactChunk(result.content_base64);
    if (bytes.length > (input.limit ?? 256 * 1024)) return invalid();
    if (result.offset === 0 && result.eof && await digestBytes(bytes) !== artifact.sha256) return invalid();
  }
  if (signal?.aborted) throw new DOMException("The execution request was cancelled", "AbortError");
  return result;
}
export function createExperimentExecutionClient(options: ExperimentHttpOptions = {}): ExperimentExecutionClient {
  const http = createExperimentHttp(options, "execution");
  const call = async (action: keyof ExecutionRequests, supplied: unknown, signal?: AbortSignal) => {
    let input: any;
    try { input = parseExecutionModel(models[action][0], supplied, false); } catch { throw new ExperimentClientError("invalid_request", "The execution request is invalid", 422); }
    return verifyReply(action, input, await http(action, input, signal), signal);
  };
  return Object.fromEntries(Object.keys(models).map(action => [action, (input: unknown, signal?: AbortSignal) => call(action as keyof ExecutionRequests, input, signal)])) as ExperimentExecutionClient;
}
export function decodeArtifactChunk(value: string): Uint8Array {
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) return invalid();
  try { const text = atob(value); if (btoa(text) !== value) return invalid(); return Uint8Array.from(text, ch => ch.charCodeAt(0)); } catch { return invalid(); }
}
export async function digestBytes(bytes: Uint8Array) { return [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes.slice().buffer))].map(v => v.toString(16).padStart(2, "0")).join(""); }
export function mergeExecution(previous: ExecutionResponse | null, next: ExecutionResponse): ExecutionResponse {
  if (!previous) return next;
  if (previous.experiment_id !== next.experiment_id || previous.proposal_revision_id !== next.proposal_revision_id || previous.proposal_version !== next.proposal_version
    || !sameExecutionBinding(previous.binding, next.binding) || experimentCanonical(previous.hashes) !== experimentCanonical(next.hashes)) return invalid();
  if (!previous.execution) return next;
  if (!next.execution || previous.execution.id !== next.execution.id || previous.execution.source !== next.execution.source) return invalid();
  if (next.execution.state_revision < previous.execution.state_revision) return previous;
  if (next.execution.latest_event_cursor < previous.execution.latest_event_cursor) return invalid();
  if (next.execution.state_revision === previous.execution.state_revision && experimentCanonical(next.execution) !== experimentCanonical(previous.execution)) return invalid();
  if (terminal(previous.execution.state) && experimentCanonical(previous.execution) !== experimentCanonical(next.execution)) return invalid();
  if (previous.execution.state === "running" && next.execution.state === "queued" || previous.execution.state === "cancelling" && ["queued", "running"].includes(next.execution.state)
    || previous.execution.cancel_requested && !next.execution.cancel_requested) return invalid();
  return next;
}
export class ExecutionSession {
  private access: string | null = null;
  private epoch = 0;
  private pending = new Map<string, PendingExecutionCancel>();
  get generation() { return this.epoch; }
  bind(access: string | null) {
    if (access !== null && (typeof access !== "string" || !access || !access.isWellFormed() || access.length > 8192)) return invalid();
    if (access !== this.access) { this.pending.clear(); this.access = access; this.epoch++; }
  }
  isCurrent(access: string, generation: number) { return this.access !== null && this.access === access && this.epoch === generation; }
  private key(binding: ExperimentContextBinding) {
    if (this.access === null) return invalid(); assertExperimentBinding(binding); return `${binding.investigation_id}:${binding.conversation_id}`;
  }
  get(binding: ExperimentContextBinding) { return this.pending.get(this.key(binding)) ?? null; }
  remember(value: PendingExecutionCancel) {
    const copied = experimentJson(value) as PendingExecutionCancel;
    if (!copied || Object.keys(copied).sort().join(",") !== "binding,request") return invalid();
    const key = this.key(copied.binding), previous = this.pending.get(key);
    parseExecutionModel("ExecutionCancelRequest", copied.request, false);
    if (!sameExecutionBinding(copied.binding, copied.request)) return invalid();
    if (previous && experimentCanonical(previous) !== experimentCanonical(copied) || !previous && this.pending.size >= 64) throw new Error("Reconcile the pending execution request first");
    this.pending.set(key, freezeExperimentValue(copied));
  }
  forget(value: PendingExecutionCancel) { const key = this.key(value.binding); if (experimentCanonical(this.pending.get(key) ?? null) === experimentCanonical(value)) this.pending.delete(key); }
  clear() { this.pending.clear(); this.access = null; this.epoch++; }
}
export async function collectArtifact(client: ExperimentExecutionClient, proposal: ExperimentSnapshot, execution: ExecutionSnapshot, artifact: ExecutionArtifact, signal: AbortSignal, progress?: (bytes: number) => void) {
  artifact = parseExecutionModel("ExecutionArtifact", artifact) as ExecutionArtifact;
  execution = parseExecutionModel("ExecutionSnapshot", execution) as ExecutionSnapshot;
  const base = parseExecutionModel("ExecutionStatusRequest", executionRequest(proposal), false);
  if (!execution.artifacts.some(value => experimentCanonical(value) === experimentCanonical(artifact))) return invalid();
  let offset = 0, first: ExecutionArtifactResponse | null = null; const parts: Uint8Array[] = [];
  while (offset < artifact.size_bytes) {
    if (signal.aborted) throw new DOMException("Artifact download cancelled", "AbortError");
    const request = { ...base, execution_id: execution.id, artifact_id: artifact.id, expected_sha256: artifact.sha256, offset, limit: 256 * 1024 };
    const page = await verifyReply("artifact", request, await client.artifact(request, signal), signal) as ExecutionArtifactResponse;
    if (page.next_offset <= offset || experimentCanonical(page.artifact) !== experimentCanonical(artifact) || experimentCanonical(page.execution) !== experimentCanonical(execution)) return invalid();
    if (first === null) first = page;
    const bytes = decodeArtifactChunk(page.content_base64); if (bytes.length !== page.next_offset - offset || bytes.length > 256 * 1024) return invalid(); parts.push(bytes); offset = page.next_offset; progress?.(offset);
  }
  const data = new Uint8Array(offset); let at = 0; for (const part of parts) { data.set(part, at); at += part.length; }
  if (data.length !== artifact.size_bytes || await digestBytes(data) !== artifact.sha256) return invalid();
  // Fresh artifact authorization immediately before exposing an assembled download.
  if (signal.aborted) throw new DOMException("Artifact download cancelled", "AbortError");
  const request = { ...base, execution_id: execution.id, artifact_id: artifact.id, expected_sha256: artifact.sha256, offset: 0, limit: 1 };
  const fresh = await verifyReply("artifact", request, await client.artifact(request, signal), signal) as ExecutionArtifactResponse;
  if (signal.aborted) throw new DOMException("Artifact download cancelled", "AbortError");
  if (experimentCanonical(fresh.artifact) !== experimentCanonical(artifact) || experimentCanonical(fresh.execution) !== experimentCanonical(execution)) return invalid();
  return { data, preview: first?.preview ?? null, artifact };
}
