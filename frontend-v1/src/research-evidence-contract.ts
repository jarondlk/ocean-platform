/** Authoritative generated shapes plus public semantic invariants, never source HTML. */
import { evidenceContractSchema, type EvidenceModels } from "./research-evidence.generated.ts";
import { evidenceJson, ResearchEvidenceClientError } from "./research-evidence-http.ts";
import { parseCatalogueContractModel } from "./catalogue-contract.ts";
export * from "./research-evidence.generated.ts";
type Rule = { $ref?: string; type?: string; const?: unknown; enum?: readonly unknown[]; anyOf?: readonly Rule[]; properties?: Record<string, Rule>; required?: readonly string[]; additionalProperties?: boolean | Rule; items?: Rule; minItems?: number; maxItems?: number; minLength?: number; maxLength?: number; pattern?: string; minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number };
const definitions = evidenceContractSchema.$defs as unknown as Record<string, Rule>;
const fail = (): never => { throw new ResearchEvidenceClientError("invalid_response", "The answer or evidence response could not be verified"); };
export const EVIDENCE_VERSION = "research-evidence-v1" as const, ANSWER_VERSION = "research-answers-v1" as const;
const record = (value: unknown): value is Record<string, any> => value !== null && typeof value === "object" && !Array.isArray(value);
function schema(rule: Rule, value: unknown, depth = 0): void {
  if (depth > 128) return fail();
  if (rule.$ref) { const name = rule.$ref.split("/").at(-1)!; if (!definitions[name]) return fail(); schema(definitions[name], value, depth + 1); semantics(name, value); return; }
  if (Object.hasOwn(rule, "const") && value !== rule.const || rule.enum && !rule.enum.includes(value)) return fail();
  if (rule.anyOf) { for (const choice of rule.anyOf) { try { schema(choice, value, depth + 1); return; } catch { /* Try declared union alternatives only. */ } } return fail(); }
  if (rule.type === "null") { if (value !== null) return fail(); }
  else if (rule.type === "boolean") { if (typeof value !== "boolean") return fail(); }
  else if (rule.type === "integer" || rule.type === "number") {
    if (typeof value !== "number" || !Number.isFinite(value) || rule.type === "integer" && !Number.isSafeInteger(value)
      || rule.minimum !== undefined && value < rule.minimum || rule.maximum !== undefined && value > rule.maximum
      || rule.exclusiveMinimum !== undefined && value <= rule.exclusiveMinimum || rule.exclusiveMaximum !== undefined && value >= rule.exclusiveMaximum) return fail();
  } else if (rule.type === "string") {
    if (typeof value !== "string" || !value.isWellFormed() || rule.minLength !== undefined && [...value].length < rule.minLength || rule.maxLength !== undefined && [...value].length > rule.maxLength || rule.pattern && !new RegExp(rule.pattern, "u").test(value)) return fail();
  } else if (rule.type === "array") {
    if (!Array.isArray(value) || rule.minItems !== undefined && value.length < rule.minItems || rule.maxItems !== undefined && value.length > rule.maxItems) return fail();
    if (rule.items) for (const item of value) schema(rule.items, item, depth + 1);
  } else if (rule.type === "object") {
    if (!record(value) || rule.required?.some(key => !Object.hasOwn(value, key))) return fail();
    for (const [key, item] of Object.entries(value)) { const child = rule.properties && Object.hasOwn(rule.properties, key) ? rule.properties[key] : undefined; if (child) schema(child, item, depth + 1); else if (rule.additionalProperties === false) return fail(); else if (typeof rule.additionalProperties === "object") schema(rule.additionalProperties, item, depth + 1); }
  }
}
function semantics(name: string, value: any): void {
  if (["EvidenceAddressRequest", "EvidencePageRequest", "EvidenceExportRequest"].includes(name) && value.receipt_id !== `c21:receipt:${value.expected_sha256}`) return fail();
  if (["EvidenceResponse", "EvidenceListResponse", "EvidencePageResponse", "EvidenceExportResponse"].includes(name) && value.version !== EVIDENCE_VERSION) return fail();
  if (["AnswerResponse", "AnswerListResponse", "AnswerEventsResponse"].includes(name) && value.version !== ANSWER_VERSION) return fail();
  if (name === "EvidenceTotal" && (value.state === "known" ? value.value === null || value.reason !== null : value.value !== null || value.reason === null)) return fail();
  if (name === "SemanticCount" && (value.state === "known" ? value.value == null : value.value != null || value.reason == null)) return fail();
  if (name === "EvidenceReceipt") {
    if (value.id !== `c21:receipt:${value.sha256}` || value.attachment_reference.kind !== "artifact" || value.attachment_reference.id !== value.id || value.attachment_reference.snapshot_id !== value.binding.snapshot_id
      || value.next_offset !== null && value.next_offset <= value.offset || value.authority === "documentary" && value.kind !== "documentary") return fail();
    if (new Set(value.columns.map((column: any) => column.key)).size !== value.columns.length) return fail();
  }
  if (name === "RenderedAnswer") {
    if (value.scientific_verification !== "not_independently_verified" || new Set(value.receipt_ids).size !== value.receipt_ids.length || new Set(value.blocks.map((block: any) => block.id)).size !== value.blocks.length || value.blocks.some((block: any) => new Set(block.receipt_ids).size !== block.receipt_ids.length || block.receipt_ids.some((id: string) => !value.receipt_ids.includes(id)))) return fail();
  }
  if (name === "AnswerJob" && (["completed", "partial"].includes(value.status) !== (value.answer !== null) || value.answer && (value.answer.locale !== value.locale || value.answer.completion !== (value.status === "completed" ? "complete" : "partial")))) return fail();
  if (name === "AnswerEventsResponse") {
    if (value.next_cursor !== value.after_cursor + value.events.length || value.latest_event_cursor < value.next_cursor || value.has_more !== (value.next_cursor < value.latest_event_cursor) || value.has_more && !value.events.length
      || value.events.some((item: any, index: number) => item.job_id !== value.job_id || item.cursor !== value.after_cursor + index + 1 || index > 0 && item.elapsed_ms < value.events[index - 1].elapsed_ms)) return fail();
  }
}
export function freezeEvidenceValue<T>(value: T): T {
  if (value !== null && typeof value === "object") { for (const item of Object.values(value)) freezeEvidenceValue(item); Object.freeze(value); } return value;
}
export async function parseEvidenceModel<K extends keyof EvidenceModels>(name: K, supplied: unknown): Promise<EvidenceModels[K]> {
  if (!Object.hasOwn(definitions, name)) return fail();
  const value = evidenceJson(supplied); schema(definitions[name], value); semantics(name, value);
  // Only typed receipt slots carry a scientific scope. Quoted rows and block
  // data may use the words "id" or "scope" without becoming protocol objects.
  const scopes: unknown[] = name === "EvidenceScope" ? [value] : name === "EvidenceReceipt" ? [(value as EvidenceModels["EvidenceReceipt"]).scope]
    : name === "EvidenceListResponse" ? (value as EvidenceModels["EvidenceListResponse"]).items.map(receipt => receipt.scope)
    : ["EvidenceResponse", "EvidencePageResponse", "EvidenceExportResponse"].includes(name) ? [(value as EvidenceModels["EvidenceResponse"]).receipt.scope] : [];
  for (const scope of scopes) { try { await parseCatalogueContractModel("EvidenceScope", scope); } catch { return fail(); } }
  return freezeEvidenceValue(value) as EvidenceModels[K];
}
