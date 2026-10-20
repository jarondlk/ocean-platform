/** Separate public C21 actions. Reads never dispatch generation or use legacy data. */
import { createEvidenceHttp, ResearchEvidenceClientError, type EvidenceHttpOptions } from "./research-evidence-http.ts";
import { parseEvidenceModel, type EvidenceModels, type ControllerBinding, type AnswerJob } from "./research-evidence-contract.ts";
export type AnswerRequests = { submit: EvidenceModels["AnswerSubmitRequest"]; status: EvidenceModels["AnswerAddressRequest"]; events: EvidenceModels["AnswerEventsRequest"]; cancel: EvidenceModels["AnswerCancelRequest"]; list: EvidenceModels["AnswerListRequest"] };
export type AnswerResponses = { submit: EvidenceModels["AnswerResponse"]; status: EvidenceModels["AnswerResponse"]; events: EvidenceModels["AnswerEventsResponse"]; cancel: EvidenceModels["AnswerResponse"]; list: EvidenceModels["AnswerListResponse"] };
export type EvidenceRequests = { list: EvidenceModels["EvidenceListRequest"]; open: EvidenceModels["EvidenceAddressRequest"]; page: EvidenceModels["EvidencePageRequest"]; export: EvidenceModels["EvidenceExportRequest"] };
export type EvidenceResponses = { list: EvidenceModels["EvidenceListResponse"]; open: EvidenceModels["EvidenceResponse"]; page: EvidenceModels["EvidencePageResponse"]; export: EvidenceModels["EvidenceExportResponse"] };
export type AnswerClient = { [K in keyof AnswerRequests]: (request: AnswerRequests[K], signal?: AbortSignal) => Promise<AnswerResponses[K]> };
export type EvidenceClient = { [K in keyof EvidenceRequests]: (request: EvidenceRequests[K], signal?: AbortSignal) => Promise<EvidenceResponses[K]> };
export type AnswerMutationIntent = { method: "submit"; request: AnswerRequests["submit"]; binding: ControllerBinding } | { method: "cancel"; request: AnswerRequests["cancel"]; binding: ControllerBinding };
const invalid = (): never => { throw new ResearchEvidenceClientError("invalid_response", "The answer or evidence response could not be verified"); };
const abort = (signal?: AbortSignal) => { if (signal?.aborted) throw new DOMException("The request was cancelled", "AbortError"); };
export function sameAnswerBinding(a: ControllerBinding, b: ControllerBinding): boolean { return a.investigation_id === b.investigation_id && a.conversation_id === b.conversation_id && a.revision_id === b.revision_id && a.snapshot_id === b.snapshot_id && a.payload_sha256 === b.payload_sha256; }
export const answerAddress = (job: AnswerJob): AnswerRequests["status"] => ({ investigation_id: job.binding.investigation_id, conversation_id: job.binding.conversation_id, run_id: job.run_id, job_id: job.id });
async function request<K extends keyof EvidenceModels>(name: K, value: unknown) {
  try { return await parseEvidenceModel(name, value); } catch { throw new ResearchEvidenceClientError("invalid_request", "The answer or evidence request is invalid", 422); }
}
const answerModels = { submit: ["AnswerSubmitRequest", "AnswerResponse"], status: ["AnswerAddressRequest", "AnswerResponse"], events: ["AnswerEventsRequest", "AnswerEventsResponse"], cancel: ["AnswerCancelRequest", "AnswerResponse"], list: ["AnswerListRequest", "AnswerListResponse"] } as const;
export function createAnswerClient(options: EvidenceHttpOptions = {}): AnswerClient {
  const http = createEvidenceHttp(options);
  const call = async (method: keyof AnswerRequests, supplied: unknown, signal?: AbortSignal) => {
    abort(signal); const input = await request(answerModels[method][0], supplied); abort(signal);
    const result = await parseEvidenceModel(answerModels[method][1], await http(`answers/${method}`, input, signal)); abort(signal);
    const p = input as AnswerRequests["submit"] & AnswerRequests["events"];
    const bound = "job" in result ? result.job.binding : result.binding;
    if (bound.investigation_id !== p.investigation_id || bound.conversation_id !== p.conversation_id) return invalid();
    if (method === "list") {
      const v = result as AnswerResponses["list"];
      if (v.run_id !== p.run_id || v.items.length > (p.limit ?? 25) || new Set(v.items.map(item => item.id)).size !== v.items.length || v.next_cursor !== null && (!v.items.length || v.next_cursor === (input as AnswerRequests["list"]).cursor || v.next_cursor.length > 4096)) return invalid();
      for (const item of v.items) if (item.run_id !== p.run_id || item.input_version !== v.input_version || !sameAnswerBinding(item.binding, v.binding)) return invalid();
    } else if (method === "events") {
      const v = result as AnswerResponses["events"];
      if (v.job_id !== p.job_id || v.after_cursor !== (p.after_cursor ?? 0) || v.events.length > (p.limit ?? 100)) return invalid();
    } else {
      const v = result as AnswerResponses["status"];
      if (v.job.run_id !== p.run_id || method !== "submit" && v.job.id !== p.job_id || method === "submit" && (v.job.input_version !== p.input_version || v.job.locale !== (p.locale ?? "en"))) return invalid();
    }
    return result;
  };
  return Object.fromEntries(Object.keys(answerModels).map(method => [method, (input: unknown, signal?: AbortSignal) => call(method as keyof AnswerRequests, input, signal)])) as unknown as AnswerClient;
}
const evidenceModels = { list: ["EvidenceListRequest", "EvidenceListResponse"], open: ["EvidenceAddressRequest", "EvidenceResponse"], page: ["EvidencePageRequest", "EvidencePageResponse"], export: ["EvidenceExportRequest", "EvidenceExportResponse"] } as const;
export function createEvidenceClient(options: EvidenceHttpOptions = {}): EvidenceClient {
  const http = createEvidenceHttp(options);
  const call = async (method: keyof EvidenceRequests, supplied: unknown, signal?: AbortSignal) => {
    abort(signal); const input = await request(evidenceModels[method][0], supplied); abort(signal);
    const result = await parseEvidenceModel(evidenceModels[method][1], await http(`evidence/${method}`, input, signal)); abort(signal);
    if (method === "list") {
      const p = input as EvidenceRequests["list"], v = result as EvidenceResponses["list"];
      if (v.run_id !== p.run_id || v.input_version !== p.input_version || v.offset !== (p.offset ?? 0) || v.items.length > (p.limit ?? 100) || new Set(v.items.map(item => item.id)).size !== v.items.length
        || v.next_offset !== null && (v.next_offset <= v.offset || !v.items.length)) return invalid();
    } else {
      const p = input as EvidenceRequests["page"], v = result as EvidenceResponses["page"];
      if (v.receipt.id !== p.receipt_id || v.receipt.sha256 !== p.expected_sha256) return invalid();
      if (method !== "open" && (v.section !== (p.section ?? "rows") || v.offset !== (p.offset ?? 0) || v.next_offset !== null && v.next_offset <= v.offset)) return invalid();
      if (method === "page" && v.rows.length > (p.limit ?? 100)) return invalid();
      if (method === "export") {
        const e = result as EvidenceResponses["export"], q = input as EvidenceRequests["export"];
        if (e.format !== (q.format ?? "csv") || e.mime_type !== (e.format === "csv" ? "text/csv; charset=utf-8" : "application/json; charset=utf-8") || e.returned_count > (p.limit ?? 100)) return invalid();
        const bytes = new TextEncoder().encode(e.content_text), digest = [...new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))].map(value => value.toString(16).padStart(2, "0")).join("");
        abort(signal); if (digest !== e.content_sha256) return invalid();
      }
    }
    return result;
  };
  return Object.fromEntries(Object.keys(evidenceModels).map(method => [method, (input: unknown, signal?: AbortSignal) => call(method as keyof EvidenceRequests, input, signal)])) as unknown as EvidenceClient;
}
export function executeAnswerMutation(client: AnswerClient, intent: AnswerMutationIntent, signal?: AbortSignal) { return intent.method === "submit" ? client.submit(intent.request, signal) : client.cancel(intent.request, signal); }
