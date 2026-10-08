import { evidenceScopeSchema, type EvidenceScope } from "./generated/chat-scope.ts";

export type SourceFamily = keyof EvidenceScope["sources"];
export const sourceLabels: Record<SourceFamily, string> = {
  ctd: "CTD", metagenome: "Metagenome", remote_sensing: "Satellite SST", edna_metabarcoding: "ANEMONE eDNA",
};
export function defaultScope(): EvidenceScope {
  return { version: 1, sources: {
    ctd: { enabled: true, filters: {} }, metagenome: { enabled: true, filters: {} },
    remote_sensing: { enabled: true, filters: {} }, edna_metabarcoding: { enabled: true, filters: {} },
  }};
}
export type ChatSettings = {
  model: string; k: number; vectorWeight: number; ftsWeight: number; rrfK: number;
  expandEvidence: boolean; maxLinkedSources: number; injectAnalysis: boolean;
  injectReliability: boolean; runAnswerAudit: boolean; temperature: number; topP: number;
  repeatPenalty: number; numCtx: number; numPredict: string; samplingTopK: string; seed: string;
};
export const defaultSettings: ChatSettings = {
  model: "", k: 8, vectorWeight: 0.6, ftsWeight: 0.4, rrfK: 60, expandEvidence: true,
  maxLinkedSources: 5, injectAnalysis: true, injectReliability: true, runAnswerAudit: true,
  temperature: 0, topP: 0.9, repeatPenalty: 1.1, numCtx: 8192, numPredict: "", samplingTopK: "", seed: "",
};

type Schema = { $ref?: string; anyOf?: readonly Schema[]; const?: unknown; enum?: readonly unknown[];
  type?: string; required?: readonly string[]; properties?: Record<string, Schema>;
  additionalProperties?: boolean; minLength?: number; maxLength?: number; pattern?: string; minimum?: number; maximum?: number };
const definitions: Record<string, Schema> = evidenceScopeSchema.$defs;
export function scopeErrors(value: unknown): string[] {
  function validate(node: Schema, data: unknown, path: string): string[] {
    if (node.$ref) return validate(definitions[node.$ref.split("/").pop()!], data, path);
    if (node.anyOf) return node.anyOf.some(child => !validate(child, data, path).length) ? [] : [`${path}: invalid value`];
    if (node.const !== undefined && data !== node.const) return [`${path}: unsupported version`];
    if (node.enum && !node.enum.includes(data)) return [`${path}: unsupported choice`];
    if (node.type === "null") return data === null ? [] : [`${path}: invalid value`];
    if (node.type === "object") {
      if (!data || typeof data !== "object" || Array.isArray(data)) return [`${path}: expected settings`];
      const record = data as Record<string, unknown>, fields = node.properties || {};
      const errors = (node.required || []).filter(key => !(key in record)).map(key => `${path}.${key}: required`);
      for (const [key, item] of Object.entries(record)) {
        if (!(key in fields)) { if (node.additionalProperties === false) errors.push(`${path}.${key}: unsupported setting`); }
        else errors.push(...validate(fields[key], item, `${path}.${key}`));
      }
      const start = record.time_from, end = record.time_to;
      const date = (v: unknown) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}(?:[T ].+)?$/.test(v) && Number.isFinite(Date.parse(v)) && (new Date(v.slice(0, 10)).toISOString().slice(0, 10) === v.slice(0, 10));
      for (const key of ["time_from", "time_to"]) if (record[key] != null && !date(record[key])) errors.push(`${path}.${key}: use a valid date`);
      if (date(start) && date(end) && Date.parse(start as string) > Date.parse(end as string) + ((end as string).length === 10 ? 86400000 - 1 : 0)) errors.push(`${path}: From must precede To`);
      for (const axis of ["lat", "lon"]) if (typeof record[axis + "_min"] === "number" && typeof record[axis + "_max"] === "number" && Number(record[axis + "_min"]) > Number(record[axis + "_max"])) errors.push(`${path}: minimum exceeds maximum`);
      if (record.sample_kind === "environmental" && record.is_control === true || ["negative_control", "positive_control", "mock_community"].includes(String(record.sample_kind)) && record.is_control === false) errors.push(`${path}: sample kind and control status conflict`);
      return errors;
    }
    if (node.type === "string") {
      if (typeof data !== "string") return [`${path}: expected text`];
      if (node.minLength !== undefined && data.trim().length < node.minLength || node.maxLength !== undefined && data.length > node.maxLength || node.pattern && !new RegExp(node.pattern).test(data)) return [`${path}: invalid text`];
    }
    if (node.type === "boolean" && typeof data !== "boolean") return [`${path}: expected checkbox`];
    if (node.type === "number" || node.type === "integer") {
      if (typeof data !== "number" || !Number.isFinite(data) || node.type === "integer" && !Number.isInteger(data) || node.minimum !== undefined && data < node.minimum || node.maximum !== undefined && data > node.maximum) return [`${path}: out of range`];
    }
    return [];
  }
  return validate(evidenceScopeSchema, value, "sources");
}
export function settingsErrors(settings: ChatSettings, maxTokens = 8192): string[] {
  const ranges: Partial<Record<keyof ChatSettings, [number, number, boolean?]>> = {
    k: [1, 25, true], vectorWeight: [0, 1], ftsWeight: [0, 1], rrfK: [1, 200, true],
    maxLinkedSources: [0, 25, true], temperature: [0, 2], topP: [0, 1], repeatPenalty: [0.5, 2], numCtx: [512, 32768, true],
  };
  const errors = Object.entries(ranges).flatMap(([key, [min, max, integer]]) => {
    const value = settings[key as keyof ChatSettings];
    return typeof value !== "number" || !Number.isFinite(value) || value < min || value > max || integer && !Number.isInteger(value) ? [`${key}: out of range`] : [];
  });
  if (typeof settings.model !== "string" || settings.model.length > 255) errors.push("model: invalid text");
  if (settings.vectorWeight + settings.ftsWeight <= 0) errors.push("Choose a positive retrieval weight");
  for (const [key, max] of [["numPredict", maxTokens], ["samplingTopK", 200], ["seed", Number.MAX_SAFE_INTEGER]] as const) {
    const value = settings[key];
    if (typeof value !== "string" || value !== "" && (!/^\d+$/.test(value) || Number(value) < (key === "seed" ? 0 : 1) || Number(value) > max)) errors.push(`${key}: invalid integer`);
  }
  return errors;
}
// Analysis selection is transient UI state, never an inherited source filter.
export function scopeForAnalysis(scope: EvidenceScope, analysisId: string): EvidenceScope {
  const edna = {...scope.sources.edna_metabarcoding};
  delete edna.analysis_id;
  if (edna.enabled && analysisId.trim()) edna.analysis_id = analysisId.trim();
  return {...scope, sources: {...scope.sources, edna_metabarcoding: edna}};
}
export function settingsStorageKey(accountId: string): string { return `ocean-chat-settings:v1:${accountId}`; }
export function decodeSettings(raw: string | null): {settings: ChatSettings; scope: EvidenceScope} {
  if (raw === null) return {settings: {...defaultSettings}, scope: defaultScope()};
  const value = JSON.parse(raw);
  if (value?.version !== 1 || scopeErrors(value.scope).length) throw new Error("Saved source settings need review. Reset settings to continue.");
  delete value.scope.sources.edna_metabarcoding.analysis_id;
  // Recover non-scientific preferences independently; never repair scope silently.
  const settings = {...defaultSettings};
  for (const key of Object.keys(defaultSettings) as (keyof ChatSettings)[]) {
    if (typeof value.settings?.[key] === typeof defaultSettings[key]) Object.assign(settings, {[key]: value.settings[key]});
  }
  if (settingsErrors(settings).length) return {settings: {...defaultSettings}, scope: value.scope};
  return {settings, scope: value.scope};
}
export function encodeSettings(settings: ChatSettings, scope: EvidenceScope): string {
  const sources = structuredClone(scope.sources);
  delete sources.edna_metabarcoding.analysis_id;
  const safeSettings = Object.fromEntries(Object.keys(defaultSettings).map(key => [key, settings[key as keyof ChatSettings]]));
  return JSON.stringify({version: 1, settings: safeSettings, scope: {...scope, sources}});
}
