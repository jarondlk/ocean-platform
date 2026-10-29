/** The exact nine C22 review actions. Fake dispatch never means Python execution. */
import { createExperimentHttp, ExperimentClientError, experimentCanonical, type ExperimentHttpOptions } from "./experiment-http.ts";
import { parseExperimentModel, normalizeExperimentProposal, type ExperimentModels, type ExperimentResponse, type ExperimentListResponse, type ExperimentEventsResponse, type ExperimentSnapshot, type ExperimentContextBinding } from "./experiment-contract.ts";
export type { ExperimentHttpOptions } from "./experiment-http.ts";
export { normalizeExperimentProposal } from "./experiment-contract.ts";
export type ExperimentRequests = {
  create: ExperimentModels["ExperimentCreateRequest"]; revise: ExperimentModels["ExperimentReviseRequest"];
  get: ExperimentModels["ExperimentGetRequest"]; status: ExperimentModels["ExperimentAddressRequest"];
  list: ExperimentModels["ExperimentListRequest"]; approve: ExperimentModels["ExperimentApprovalRequest"];
  dispatch: ExperimentModels["ExperimentDispatchRequest"]; events: ExperimentModels["ExperimentEventsRequest"];
  retry: ExperimentModels["ExperimentRetryRequest"];
};
export type ExperimentResponses = { [K in keyof ExperimentRequests]: K extends "list" ? ExperimentListResponse : K extends "events" ? ExperimentEventsResponse : ExperimentResponse };
export type ExperimentClient = { [K in keyof ExperimentRequests]: (request: ExperimentRequests[K], signal?: AbortSignal) => Promise<ExperimentResponses[K]> };
export type ExperimentMutationMethod = "create" | "revise" | "approve" | "dispatch" | "retry";
export type ExperimentMutationIntent = { [K in ExperimentMutationMethod]: { method: K; request: ExperimentRequests[K]; binding: ExperimentContextBinding } }[ExperimentMutationMethod];
const models = {
  create: ["ExperimentCreateRequest", "ExperimentResponse"], revise: ["ExperimentReviseRequest", "ExperimentResponse"],
  get: ["ExperimentGetRequest", "ExperimentResponse"], status: ["ExperimentAddressRequest", "ExperimentResponse"],
  list: ["ExperimentListRequest", "ExperimentListResponse"], approve: ["ExperimentApprovalRequest", "ExperimentResponse"],
  dispatch: ["ExperimentDispatchRequest", "ExperimentResponse"], events: ["ExperimentEventsRequest", "ExperimentEventsResponse"],
  retry: ["ExperimentRetryRequest", "ExperimentResponse"],
} as const;
const fail = (): never => { throw new ExperimentClientError("invalid_response", "The experiment response does not match the requested review"); };
const abort = (signal?: AbortSignal) => { if (signal?.aborted) throw new DOMException("The experiment request was cancelled", "AbortError"); };
export function sameExperimentBinding(left: ExperimentContextBinding, right: ExperimentContextBinding): boolean {
  return left.investigation_id === right.investigation_id && left.conversation_id === right.conversation_id
    && left.context_revision_id === right.context_revision_id && left.snapshot_id === right.snapshot_id && left.context_payload_sha256 === right.context_payload_sha256;
}
function bound(method: keyof ExperimentRequests, request: any, response: ExperimentResponse | ExperimentListResponse | ExperimentEventsResponse): void {
  if (method === "events") {
    const result = response as ExperimentEventsResponse;
    if (result.experiment_id !== request.experiment_id || result.after_cursor !== (request.after_cursor ?? 0) || result.items.length > (request.limit ?? 100)) return fail();
    return;
  }
  const result = response as ExperimentResponse;
  if (["create", "revise", "approve", "dispatch", "retry"].includes(method) && (!result.operation
    || result.operation.state === "ready" && (!result.experiment || result.operation.result_revision_id !== result.experiment.proposal_revision_id))) return fail();
  const items = method === "list" ? (response as ExperimentListResponse).items : result.experiment ? [result.experiment] : [];
  if (method === "retry" && result.operation?.id !== request.operation_id) return fail();
  for (const item of items) {
    if (request.experiment_id && item.id !== request.experiment_id) return fail();
    const preparing = (method === "create" || method === "revise") && result.operation?.state !== "ready";
    const keys = preparing ? ["investigation_id", "conversation_id"] : ["investigation_id", "conversation_id", "context_revision_id", "snapshot_id", "context_payload_sha256"];
    for (const key of keys) if (request[key] !== undefined && request[key] !== null && (item.binding as any)[key] !== request[key]) return fail();
    const revision = method === "get" ? request.proposal_revision_id : method === "approve" || method === "dispatch" ? request.expected_proposal_revision_id : undefined;
    if (revision && item.proposal_revision_id !== revision) return fail();
    if ((method === "approve" || method === "dispatch") && experimentCanonical(item.hashes) !== experimentCanonical(request.expected_hashes)) return fail();
    if ((method === "create" || method === "revise") && !preparing && (result.operation?.result_revision_id !== item.proposal_revision_id
      || experimentCanonical(item.proposal) !== experimentCanonical(normalizeExperimentProposal(request.proposal)))) return fail();
  }
  if (method === "list") {
    const list = response as ExperimentListResponse;
    if (list.items.length > (request.limit ?? 25) || list.next_cursor !== null && (!list.items.length || list.next_cursor !== list.items.at(-1)!.id || list.next_cursor === request.after_id)) return fail();
    let previous = request.after_id ?? "";
    for (const item of list.items) { if (item.id <= previous) return fail(); previous = item.id; }
  }
}
export function createExperimentClient(options: ExperimentHttpOptions = {}): ExperimentClient {
  const http = createExperimentHttp(options);
  const call = async (method: keyof ExperimentRequests, supplied: unknown, signal?: AbortSignal) => {
    abort(signal); let input;
    try { input = await parseExperimentModel(models[method][0], supplied); }
    catch { throw new ExperimentClientError("invalid_request", "The experiment request is invalid", 422); }
    abort(signal);
    const response = await parseExperimentModel(models[method][1], await http(method, input, signal));
    abort(signal); bound(method, input, response as ExperimentResponse | ExperimentListResponse | ExperimentEventsResponse); return response;
  };
  return Object.fromEntries(Object.keys(models).map(method => [method, (request: unknown, signal?: AbortSignal) => call(method as keyof ExperimentRequests, request, signal)])) as unknown as ExperimentClient;
}
export function experimentAddress(snapshot: ExperimentSnapshot): ExperimentRequests["status"] { return { experiment_id: snapshot.id }; }
export async function executeExperimentMutation(client: ExperimentClient, intent: ExperimentMutationIntent, signal?: AbortSignal): Promise<ExperimentResponse> {
  if (!intent || !["create", "revise", "approve", "dispatch", "retry"].includes(intent.method)) throw new ExperimentClientError("invalid_request", "The experiment mutation is invalid", 422);
  await parseExperimentModel("ExperimentContextBinding", intent.binding);
  if (intent.method !== "retry" && !sameExperimentBinding(intent.binding, intent.request)) throw new ExperimentClientError("invalid_request", "The experiment request changed its context", 422);
  const result = await (client[intent.method] as (request: ExperimentMutationIntent["request"], signal?: AbortSignal) => Promise<ExperimentResponse>)(intent.request, signal);
  if (result.experiment && (result.experiment.binding.investigation_id !== intent.binding.investigation_id || result.experiment.binding.conversation_id !== intent.binding.conversation_id
    || result.operation?.state === "ready" && !sameExperimentBinding(result.experiment.binding, intent.binding))) return fail();
  return result;
}
