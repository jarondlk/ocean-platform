/** C22 review protocol only; the separate execution projection has its own version. */
import { experimentContractSchema, type ExperimentModels } from "./generated/experiment-review.generated.ts";
import { ExperimentClientError, experimentJson, experimentRecord, experimentCanonical, experimentSha256, freezeExperimentValue } from "./experiment-http.ts";
export { ExperimentClientError, freezeExperimentValue, experimentCanonical, experimentSha256 } from "./experiment-http.ts";
export type { ExperimentModels } from "./generated/experiment-review.generated.ts";
type Complete<T> = T extends (infer U)[] ? Complete<U>[] : T extends object ? { [K in keyof T]-?: Complete<T[K]> } : T;
export type ExperimentSnapshot = Complete<ExperimentModels["ExperimentSnapshot"]>;
export type ExperimentProposal = Complete<ExperimentModels["ExperimentProposal"]>;
export type ExperimentContextBinding = Complete<ExperimentModels["ExperimentContextBinding"]>;
export type ExperimentHashes = Complete<ExperimentModels["ExperimentHashes"]>;
export type ExperimentResponse = Complete<ExperimentModels["ExperimentResponse"]>;
export type ExperimentListResponse = Complete<ExperimentModels["ExperimentListResponse"]>;
export type ExperimentEventsResponse = Complete<ExperimentModels["ExperimentEventsResponse"]>;
export type ExperimentEvent = Complete<ExperimentModels["ExperimentEvent"]>;
export type ExperimentRule = { $ref?: string; type?: string; const?: unknown; enum?: readonly unknown[]; anyOf?: readonly ExperimentRule[]; properties?: Record<string, ExperimentRule>; propertyNames?: ExperimentRule; required?: readonly string[]; additionalProperties?: boolean | ExperimentRule; items?: ExperimentRule; minItems?: number; maxItems?: number; minLength?: number; maxLength?: number; pattern?: string; minimum?: number; maximum?: number; exclusiveMinimum?: number; exclusiveMaximum?: number };
const definitions = experimentContractSchema.$defs as unknown as Record<string, ExperimentRule>;
const fail = (): never => { throw new ExperimentClientError("invalid_response", "The experiment response could not be verified"); };
const unique = (items: unknown[]) => new Set(items.map(item => experimentCanonical(item))).size === items.length;
const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]*$(?![\s\S])/u;
// Equivalent to packaging.version's bounded PEP 440 grammar. This is a syntax
// check, never a package resolver or an assertion that packages were executed.
const packageVersion = /^v?(?:[0-9]+!)?[0-9]+(?:\.[0-9]+)*(?:[._-]?(?:alpha|a|beta|b|preview|pre|c|rc)[._-]?[0-9]*)?(?:-[0-9]+|[._-]?(?:post|rev|r)[._-]?[0-9]*)?(?:[._-]?dev[._-]?[0-9]*)?(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?$(?![\s\S])/iu;
const pythonWhitespace = /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu;
export function normalizeExperimentProposal(value: ExperimentModels["ExperimentProposal"]): ExperimentModels["ExperimentProposal"] {
  return {
    ...value,
    cohort: { ...value.cohort, version: value.cohort.version ?? "c22-cohort-v1", selections: value.cohort.selections.map(item => ({ ...item, kind: item.kind ?? "dataset" })),
      pairing: { mode: value.cohort.pairing?.mode ?? "independent", relationship_ids: value.cohort.pairing?.relationship_ids ?? [] }, exclusions: value.cohort.exclusions ?? [] },
    seeds: value.seeds ?? {}, resources: { cpus: value.resources?.cpus ?? 2, memory_bytes: value.resources?.memory_bytes ?? 4 * 1024 ** 3,
      wall_seconds: value.resources?.wall_seconds ?? 600, max_input_bytes: value.resources?.max_input_bytes ?? 256 * 1024 ** 2, max_output_bytes: value.resources?.max_output_bytes ?? 50 * 1024 ** 2 },
  };
}
/** Reusable strict generated-schema validator; unknown protocol fields never become UI state. */
export function validateExperimentSchema(defs: Record<string, ExperimentRule>, rule: ExperimentRule, value: unknown, full = false, depth = 0, visit?: (name: string, value: any) => void): void {
  if (depth > 128) return fail();
  if (rule.$ref) { const name = rule.$ref.split("/").at(-1)!; if (!defs[name]) return fail(); validateExperimentSchema(defs, defs[name], value, full, depth + 1, visit); visit?.(name, value); return; }
  if (Object.hasOwn(rule, "const") && value !== rule.const || rule.enum && !rule.enum.includes(value)) return fail();
  if (rule.anyOf) { for (const choice of rule.anyOf) { try { validateExperimentSchema(defs, choice, value, full, depth + 1, visit); return; } catch { /* Declared alternatives only. */ } } return fail(); }
  if (rule.type === "null") { if (value !== null) return fail(); }
  else if (rule.type === "boolean") { if (typeof value !== "boolean") return fail(); }
  else if (rule.type === "integer" || rule.type === "number") {
    if (typeof value !== "number" || !Number.isFinite(value) || rule.type === "integer" && !Number.isSafeInteger(value)
      || rule.minimum !== undefined && value < rule.minimum || rule.maximum !== undefined && value > rule.maximum
      || rule.exclusiveMinimum !== undefined && value <= rule.exclusiveMinimum || rule.exclusiveMaximum !== undefined && value >= rule.exclusiveMaximum) return fail();
  } else if (rule.type === "string") {
    if (typeof value !== "string" || !value.isWellFormed() || rule.minLength !== undefined && [...value].length < rule.minLength || rule.maxLength !== undefined && [...value].length > rule.maxLength
      || rule.pattern && !new RegExp(rule.pattern.endsWith("$") ? rule.pattern + "(?![\\s\\S])" : rule.pattern, "u").test(value)) return fail();
  } else if (rule.type === "array") {
    if (!Array.isArray(value) || rule.minItems !== undefined && value.length < rule.minItems || rule.maxItems !== undefined && value.length > rule.maxItems) return fail();
    if (rule.items) for (const item of value) validateExperimentSchema(defs, rule.items, item, full, depth + 1, visit);
  } else if (rule.type === "object") {
    if (!experimentRecord(value) || (full ? Object.keys(rule.properties ?? {}) : rule.required ?? []).some(key => !Object.hasOwn(value, key))) return fail();
    for (const [key, item] of Object.entries(value)) {
      if (rule.propertyNames) validateExperimentSchema(defs, { type: "string", ...rule.propertyNames }, key, false, depth + 1, visit);
      const child = rule.properties && Object.hasOwn(rule.properties, key) ? rule.properties[key] : undefined;
      if (child) validateExperimentSchema(defs, child, item, full, depth + 1, visit);
      else if (rule.additionalProperties === false) return fail();
      else if (typeof rule.additionalProperties === "object") validateExperimentSchema(defs, rule.additionalProperties, item, full, depth + 1, visit);
    }
  }
}
function semantics(name: string, value: any): void {
  if (name === "ExportSelection" && !unique(value.columns)) return fail();
  if (name === "PairingSpec") {
    const mode = value.mode ?? "independent", ids = value.relationship_ids ?? [];
    if (!unique(ids) || (mode === "independent") !== !ids.length) return fail();
  }
  if (name === "ExplicitExclusion" && !unique(value.ids)) return fail();
  if (name === "FrozenCohortSpec") {
    if (!unique(value.selections.map((v: any) => [v.kind ?? "dataset", v.target_id, v.table]))) return fail();
    if (!unique((value.exclusions ?? []).flatMap((v: any) => v.ids.map((id: string) => [v.dataset_id, v.entity, id])))) return fail();
  }
  if (name === "EnvironmentDescriptor") {
    const packages = value.packages ?? {};
    if (Object.keys(packages).length > 256 || Object.entries(packages).some(([key, version]) => !identifier.test(key) || !packageVersion.test((version as string).replace(pythonWhitespace, "")))) return fail();
    if (value.kind === "c22-fake" ? !value.test_only || value.python_version !== "not-executed" || value.image_digest != null || value.lockfile_sha256 != null || Object.keys(packages).length
      : value.test_only || !value.image_digest || !value.lockfile_sha256 || !/^3\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$/.test(value.python_version) || ["numpy", "pandas", "pyarrow", "scipy", "statsmodels", "matplotlib"].some(key => !Object.hasOwn(packages, key))) return fail();
  }
  if (name === "ExperimentProposal") {
    if (new TextEncoder().encode(value.python_code).byteLength > 32768 || !unique(value.expected_outputs.map((item: any) => item.name))
      || Object.keys(value.seeds ?? {}).length > 32 || Object.keys(value.seeds ?? {}).some(key => !identifier.test(key))
      || new TextEncoder().encode(experimentCanonical(normalizeExperimentProposal(value))).byteLength > 60000) return fail();
  }
  if (name === "ExperimentApprovalSnapshot") {
    if (value.status === "none" ? value.proposal_revision_id !== null || value.approved_at !== null : value.proposal_revision_id === null || value.approved_at === null) return fail();
  }
  if (name === "ExperimentDispatchSnapshot") {
    if (value.status === "ready" ? !value.eligible || value.reservation_id !== null || value.reason !== null : value.eligible) return fail();
    if (value.status === "unavailable" ? value.reason === null || value.reservation_id !== null : value.status !== "ready" && value.reservation_id === null) return fail();
  }
  if (name === "ExperimentSnapshot") {
    if (value.authority !== "experimental" || value.scientific_approval !== "not_independently_verified" || value.execution_performed !== false || value.event_cursor > value.latest_event_cursor
      || value.approval?.status === "current" && value.approval.proposal_revision_id !== value.proposal_revision_id
      || value.dispatch?.eligible && value.approval?.status !== "current") return fail();
    if (!experimentRecord(value.manifest) || value.manifest.authority !== "experimental" || value.manifest.independent_scientific_approval !== false || value.manifest.execution_performed !== false
      || value.manifest.proposal_sha256 !== value.hashes.proposal_sha256 || value.manifest.question !== value.proposal.question
      || !experimentRecord(value.manifest.binding) || value.manifest.binding.investigation_id !== value.binding.investigation_id
      || value.manifest.binding.conversation_id !== value.binding.conversation_id || value.manifest.binding.revision_id !== value.binding.context_revision_id
      || value.manifest.binding.snapshot_id !== value.binding.snapshot_id || value.manifest.binding.payload_sha256 !== value.binding.context_payload_sha256
      || experimentCanonical(value.manifest.cohort) !== experimentCanonical(value.proposal.cohort)) return fail();
  }
  if (["ExperimentResponse", "ExperimentListResponse", "ExperimentEventsResponse"].includes(name) && value.version !== "research-experiments-v1") return fail();
  if (name === "ExperimentResponse" && value.experiment === null && value.operation === null) return fail();
  if (name === "ExperimentListResponse" && !unique(value.items.map((item: any) => item.id))) return fail();
  if (name === "ExperimentEventsResponse") {
    if (value.next_cursor !== value.after_cursor + value.items.length || value.latest_event_cursor < value.next_cursor || value.has_more !== (value.next_cursor < value.latest_event_cursor)
      || value.has_more && !value.items.length || value.items.some((item: any, index: number) => item.cursor !== value.after_cursor + index + 1)) return fail();
  }
}
async function reviewHashes(snapshot: ExperimentSnapshot): Promise<void> {
  if (snapshot.proposal.environment_id !== snapshot.hashes.environment_sha256
    || await experimentSha256(snapshot.proposal.python_code) !== snapshot.hashes.code_sha256
    || await experimentSha256(experimentCanonical(snapshot.proposal)) !== snapshot.hashes.proposal_sha256
    || await experimentSha256(experimentCanonical(snapshot.proposal.resources)) !== snapshot.hashes.resources_sha256
    || await experimentSha256(experimentCanonical(snapshot.environment)) !== snapshot.hashes.environment_sha256) return fail();
  // The server verifies the opaque manifest digest from its Python canonical
  // bytes. Browser JSON cannot preserve Python 1.0 versus1 or machine int64.
}
export async function parseExperimentModel<K extends keyof ExperimentModels>(name: K, supplied: unknown): Promise<ExperimentModels[K]> {
  if (!Object.hasOwn(definitions, name)) return fail();
  const value = experimentJson(supplied), full = !name.endsWith("Request");
  validateExperimentSchema(definitions, definitions[name], value, full, 0, semantics); semantics(name, value);
  const snapshots = name === "ExperimentSnapshot" ? [value] : name === "ExperimentResponse" ? [(value as ExperimentResponse).experiment].filter(Boolean)
    : name === "ExperimentListResponse" ? (value as ExperimentListResponse).items : [];
  for (const snapshot of snapshots) await reviewHashes(snapshot as ExperimentSnapshot);
  return freezeExperimentValue(value) as ExperimentModels[K];
}
