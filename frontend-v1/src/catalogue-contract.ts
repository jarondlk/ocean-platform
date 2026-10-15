/**
 * Context Catalogue v1's only browser wire boundary.
 *
 * This module is deliberately opt-in until C15/C16 connect real transport. It
 * never imports the prototype fixtures or treats missing transport as sample
 * data. Generated wire types remain available beside the P00 view projection.
 */
import { catalogueContractSchema } from "./catalogue-contract.generated.ts";
import type {
  Availability, CatalogueCount, CatalogueFilters, CatalogueListing, CatalogueModels,
  CatalogueNode as WireNode, EDNADescriptor, ListingRequest, OperationReceipt,
  OperationRequest, QueryResult,
} from "./catalogue-contract.generated.ts";
import type { CatalogueNode as PrototypeNode, Source } from "./model.ts";

export * from "./catalogue-contract.generated.ts";

type JsonSchema = {
  $ref?: string; $defs?: Record<string, JsonSchema>; const?: unknown; enum?: readonly unknown[];
  type?: string | readonly string[]; anyOf?: readonly JsonSchema[]; oneOf?: readonly JsonSchema[];
  allOf?: readonly JsonSchema[]; properties?: Record<string, JsonSchema>; required?: readonly string[];
  additionalProperties?: boolean | JsonSchema; items?: JsonSchema | boolean; prefixItems?: readonly JsonSchema[];
  minLength?: number; maxLength?: number; pattern?: string; minimum?: number; maximum?: number;
  exclusiveMinimum?: number; exclusiveMaximum?: number; minItems?: number; maxItems?: number;
  uniqueItems?: boolean; minProperties?: number; maxProperties?: number; default?: unknown;
};
const schema = catalogueContractSchema as unknown as JsonSchema;

export class CatalogueContractError extends Error {
  readonly path: string;
  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "CatalogueContractError";
    this.path = path;
  }
}

function fail(path: string, message: string): never { throw new CatalogueContractError(path, message); }
function own(value: object, key: string): boolean { return Object.prototype.hasOwnProperty.call(value, key); }
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value));
}

/** Reject values that cannot arrive in an unambiguous JSON wire message. */
function jsonCopy(value: unknown, path = "$", stack = new Set<object>(), depth = 0): unknown {
  if (depth > 128) return fail(path, "payload nesting exceeds the wire limit");
  if (value === null || typeof value === "string" || typeof value === "boolean") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : fail(path, "number must be finite");
  if (!Array.isArray(value) && !object(value)) return fail(path, "expected a JSON value");
  if (stack.has(value)) return fail(path, "cyclic payload is not JSON");
  stack.add(value);
  const copy: unknown = Array.isArray(value)
    ? Array.from(value, (item, index) => jsonCopy(item, `${path}[${index}]`, stack, depth + 1))
    : Object.fromEntries(Object.entries(value).map(([key, item]) => [key, jsonCopy(item, `${path}.${key}`, stack, depth + 1)]));
  stack.delete(value);
  return copy;
}

function parseSchema(rule: JsonSchema | boolean, value: unknown, path: string, depth = 0): unknown {
  if (depth > 128) return fail(path, "schema nesting exceeds the wire limit");
  if (rule === true) return value;
  if (rule === false) return fail(path, "value is not allowed");
  if (rule.$ref) {
    const name = rule.$ref.startsWith("#/$defs/") ? rule.$ref.slice(8) : "";
    const target = schema.$defs?.[name];
    if (!target) return fail(path, "unsupported schema reference");
    // C08 rejects surrounding whitespace before the older scope model can
    // normalize it; cursor hashes therefore retain the exact wire meaning.
    if (["SampleFilters", "SatelliteFilters", "EdnaFilters"].includes(name) && object(value)) {
      for (const [key, item] of Object.entries(value)) {
        if ((key === "time_from" || key === "time_to") && typeof item === "string") isoMicroseconds(item, `${path}.${key}`);
        if (typeof item === "string" && /^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]$/u.test(item)) fail(`${path}.${key}`, "scope text must not contain surrounding whitespace");
      }
    }
    return parseSchema(target, value, path, depth + 1);
  }
  if (own(rule, "const") && value !== rule.const) return fail(path, `expected ${JSON.stringify(rule.const)}`);
  if (rule.enum && !rule.enum.includes(value)) return fail(path, "value is outside the permitted vocabulary");
  const choices = rule.anyOf ?? rule.oneOf;
  if (choices) {
    const valid: unknown[] = [];
    for (const choice of choices) {
      try { valid.push(parseSchema(choice, value, path, depth + 1)); } catch (error) {
        if (!(error instanceof CatalogueContractError)) throw error;
      }
    }
    if (!valid.length || (rule.oneOf && valid.length !== 1)) return fail(path, "value does not match its declared type");
    return valid[0];
  }
  if (rule.allOf) return rule.allOf.reduce((current, item) => parseSchema(item, current, path, depth + 1), value);
  if (Array.isArray(rule.type)) {
    return parseSchema({ anyOf: rule.type.map((type) => ({ ...rule, type })) }, value, path, depth + 1);
  }
  switch (rule.type) {
    case "null": if (value !== null) return fail(path, "expected null"); break;
    case "boolean": if (typeof value !== "boolean") return fail(path, "expected boolean"); break;
    case "integer":
    case "number": {
      if (typeof value !== "number" || !Number.isFinite(value)
        || (rule.type === "integer" && !Number.isInteger(value))) return fail(path, `expected finite ${rule.type}`);
      if (rule.minimum !== undefined && value < rule.minimum) return fail(path, "number is below its minimum");
      if (rule.maximum !== undefined && value > rule.maximum) return fail(path, "number exceeds its maximum");
      if (rule.exclusiveMinimum !== undefined && value <= rule.exclusiveMinimum) return fail(path, "number must exceed its minimum");
      if (rule.exclusiveMaximum !== undefined && value >= rule.exclusiveMaximum) return fail(path, "number must be below its maximum");
      break;
    }
    case "string": {
      if (typeof value !== "string") return fail(path, "expected string");
      const length = [...value].length;
      if (rule.minLength !== undefined && length < rule.minLength) return fail(path, "string is too short");
      if (rule.maxLength !== undefined && length > rule.maxLength) return fail(path, "string is too long");
      const pattern = rule.pattern === "\\S"
        ? /[^\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u
        : rule.pattern ? new RegExp(rule.pattern.replace(/\$$/, "(?![\\s\\S])"), "u") : null;
      if (pattern && !pattern.test(value)) return fail(path, "string does not match its declared pattern");
      break;
    }
    case "array": {
      if (!Array.isArray(value)) return fail(path, "expected array");
      if (rule.minItems !== undefined && value.length < rule.minItems) return fail(path, "array has too few entries");
      if (rule.maxItems !== undefined && value.length > rule.maxItems) return fail(path, "array has too many entries");
      if (rule.uniqueItems && new Set(value.map((item) => JSON.stringify(item))).size !== value.length) return fail(path, "array entries must be unique");
      return value.map((item, index) => parseSchema(rule.prefixItems?.[index] ?? rule.items ?? true, item, `${path}[${index}]`, depth + 1));
    }
    case "object": {
      if (!object(value)) return fail(path, "expected object");
      const keys = Object.keys(value);
      if (rule.minProperties !== undefined && keys.length < rule.minProperties) return fail(path, "object has too few fields");
      if (rule.maxProperties !== undefined && keys.length > rule.maxProperties) return fail(path, "object has too many fields");
      for (const key of rule.required ?? []) if (!own(value, key)) return fail(`${path}.${key}`, "required field is missing");
      const result: Record<string, unknown> = {};
      for (const [key, field] of Object.entries(rule.properties ?? {})) {
        if (own(value, key)) Object.defineProperty(result, key, { value: parseSchema(field, value[key], `${path}.${key}`, depth + 1), enumerable: true, writable: true, configurable: true });
        else if (own(field, "default")) Object.defineProperty(result, key, { value: jsonCopy(field.default), enumerable: true, writable: true, configurable: true });
      }
      for (const key of keys) {
        if (own(rule.properties ?? {}, key)) continue;
        Object.defineProperty(result, key, { value: parseSchema(rule.additionalProperties ?? true, value[key], `${path}.${key}`, depth + 1), enumerable: true, writable: true, configurable: true });
      }
      return result;
    }
  }
  return value;
}

const VERSION = catalogueContractSchema["x-schema-version"];
const SECTIONS = catalogueContractSchema["x-dataset-sections"];
function distinct(values: readonly unknown[]): boolean { return new Set(values).size === values.length; }
function compareCodepoints(left: string, right: string): number {
  const a = Array.from(left, (character) => character.codePointAt(0)!), b = Array.from(right, (character) => character.codePointAt(0)!);
  for (let index = 0; index < Math.min(a.length, b.length); index++) if (a[index] !== b[index]) return a[index] < b[index] ? -1 : 1;
  return a.length === b.length ? 0 : a.length < b.length ? -1 : 1;
}
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (object(value)) return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
}

/** The C08 wire subset is explicit; legacy date parsers keep their own API. */
function isoMicroseconds(value: string, path: string): bigint {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(?:(Z)|([+-])(\d{2}):(\d{2}))?)?$/.exec(value);
  if (!match) return fail(path, "expected an ISO date or timestamp with seconds");
  const [, y, mo, d, h = "0", mi = "0", s = "0", fraction = "", , sign, oh = "0", om = "0"] = match;
  const [year, month, day, hour, minute, second, offsetHour, offsetMinute] = [y, mo, d, h, mi, s, oh, om].map(Number);
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59 || second > 59 || offsetHour > 23 || offsetMinute > 59) return fail(path, "invalid ISO calendar or time");
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  date.setUTCHours(hour, minute, second, 0);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return fail(path, "invalid ISO calendar date");
  const offset = (offsetHour * 60 + offsetMinute) * (sign === "-" ? -1 : 1);
  const instant = BigInt(date.getTime() - offset * 60_000) * 1000n + BigInt(fraction.padEnd(6, "0"));
  if (instant < -62135596800000000n || instant > 253402300799999999n) return fail(path, "UTC instant exceeds the supported calendar");
  return instant;
}

async function cursorOffset(request: ListingRequest, token: string | null | undefined, path: string): Promise<number> {
  if (token == null) return 0;
  try {
    if (typeof token !== "string" || token.length > 2048) return fail(path, "invalid catalogue cursor");
    const base64 = token.replaceAll("-", "+").replaceAll("_", "/");
    const binary = atob(base64 + "=".repeat((4 - base64.length % 4) % 4));
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const payload: unknown = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
    if (!object(payload) || Object.keys(payload).sort().join(",") !== "context_sha256,offset,version"
      || payload.version !== VERSION || typeof payload.offset !== "number" || !Number.isSafeInteger(payload.offset) || payload.offset <= 0) return fail(path, "invalid catalogue cursor envelope");
    const context = jsonCopy(request) as Record<string, unknown>;
    delete context.cursor;
    const sources = (context.scope as { sources: Record<string, { filters: Record<string, unknown> }> }).sources;
    for (const selection of Object.values(sources)) {
      for (const key of ["lat_min", "lat_max", "lon_min", "lon_max"]) {
        const coordinate = selection.filters[key];
        if (typeof coordinate !== "number") continue;
        const buffer = new ArrayBuffer(8);
        new DataView(buffer).setFloat64(0, coordinate, false);
        selection.filters[key] = "float64:" + Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");
      }
    }
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonicalJson(context)));
    const expected = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
    if (payload.context_sha256 !== expected) return fail(path, "cursor belongs to a different snapshot, scope, filter, ordering or access context");
    return payload.offset;
  } catch (error) {
    if (error instanceof CatalogueContractError) throw error;
    return fail(path, "invalid or stale catalogue cursor");
  }
}

function exactJsonNumbers(value: unknown, path: string): void {
  if (typeof value === "number" && Number.isInteger(value) && !Number.isSafeInteger(value)) fail(path, "integral JSON values must fit the exact browser integer range; encode larger exact values as text");
  if (Array.isArray(value)) value.forEach((child, index) => exactJsonNumbers(child, `${path}[${index}]`));
  else if (object(value)) for (const [key, child] of Object.entries(value)) exactJsonNumbers(child, `${path}.${key}`);
}

async function modelSemantics(name: string, raw: unknown, path: string): Promise<void> {
  if (name === "JsonValue") exactJsonNumbers(raw, path);
  if (["SampleFilters", "SatelliteFilters", "EdnaFilters"].includes(name)) {
    const filters = raw as Record<string, unknown>;
    const lower = typeof filters.time_from === "string" ? isoMicroseconds(filters.time_from, `${path}.time_from`) : null;
    const end = typeof filters.time_to === "string" ? filters.time_to : null;
    const upper = end === null ? null : isoMicroseconds(end, `${path}.time_to`) + (end.length === 10 ? 86_400_000_000n : 0n);
    if (upper !== null && upper > 253402300799999999n) fail(path, "exclusive end exceeds the supported UTC calendar");
    if (lower !== null && upper !== null && (end?.length === 10 ? lower >= upper : lower > upper)) fail(path, "time_from must not exceed time_to");
    for (const axis of ["lat", "lon"]) {
      const min = filters[`${axis}_min`], max = filters[`${axis}_max`];
      if (typeof min === "number" && typeof max === "number" && min > max) fail(path, `${axis}_min must not exceed ${axis}_max`);
    }
    if (name === "EdnaFilters" && ((filters.sample_kind === "environmental" && filters.is_control === true)
      || (["negative_control", "positive_control", "mock_community"].includes(String(filters.sample_kind)) && filters.is_control === false))) fail(path, "sample kind and control status conflict");
  }
  if (name === "Availability") {
    const value = raw as Availability;
    if (value.status !== "available" && value.reason == null) fail(path, "unknown or unavailable availability requires a reason");
  }
  if (name === "EDNADescriptor") {
    const value = raw as EDNADescriptor;
    if ((value.sample_kind === "environmental" && value.is_control !== false)
      || (["negative_control", "positive_control", "mock_community"].includes(value.sample_kind) && value.is_control !== true)) fail(path, "sample kind requires explicit control status");
  }
  if (name === "CatalogueNode") {
    const value = raw as WireNode;
    if (value.kind === "root" && (value.parent_id !== null || value.id !== `root:${value.root}`)) fail(path, "root identity and parent disagree");
    if (value.kind !== "root" && value.parent_id === null) fail(path, "non-root objects require a parent identity");
    if (value.parent_id === value.id || (value.related_ids ?? []).includes(value.id)) fail(path, "self links are not canonical descendants");
    if (!distinct(value.related_ids ?? [])) fail(path, "related links must be distinct canonical identities");
    if (value.kind === "dataset" && (value.root !== "data" || !value.source_family || !value.descriptor || canonicalJson(value.sections) !== canonicalJson(SECTIONS))) fail(path, "dataset requires Data root, source descriptor and all six ordered sections");
    if (value.descriptor && value.descriptor.family !== value.source_family) fail(path, "descriptor and source family disagree");
    if (value.source_family && !value.scope.sources[value.source_family].enabled) fail(path, "source-owned node must enable that source in scope");
    if ((value.membership === "private" && value.owner_id == null) || (value.membership === "global" && value.owner_id != null)) fail(path, "membership and private owner disagree");
    if (value.root === "analyses" && value.authority === "experimental" && value.membership !== "private") fail(path, "experimental analyses require private membership");
    if (value.authority === "published" && value.lifecycle.publication !== "published") fail(path, "published authority requires published lifecycle");
    if (!distinct((value.operations ?? []).map((operation) => operation.id))) fail(path, "supported operation identities must be unique");
  }
  if (name === "CatalogueCount") {
    const value = raw as CatalogueCount;
    if (value.state === "known" && value.value == null) fail(path, "known count requires an exact integer, including zero");
    if (value.state === "unknown" && (value.value != null || value.reason == null)) fail(path, "unknown count requires a reason and no numeric value");
  }
  if (name === "CatalogueFilters") {
    const value = raw as CatalogueFilters;
    if ([value.roots, value.source_families, value.kinds, value.authorities].some((items) => !distinct(items ?? []))) fail(path, "filter sets cannot contain duplicates");
  }
  if (name === "ListingRequest") {
    const value = raw as ListingRequest, ordering = value.ordering ?? [];
    if (ordering.at(-1)?.field !== "id" || !distinct(ordering.map((item) => item.field))) fail(path, "ordering requires a final canonical ID tie-breaker");
    await cursorOffset(value, value.cursor, `${path}.cursor`);
  }
  if (name === "CatalogueListing") {
    const value = raw as CatalogueListing;
    const offset = await cursorOffset(value.request, value.request.cursor, `${path}.request.cursor`);
    if (value.returned_count !== value.items.length || value.returned_count > (value.request.limit ?? 100)) fail(path, "returned count must describe this bounded page");
    if (!distinct(value.items.map((item) => item.id))) fail(path, "page duplicates canonical identities");
    if (value.items.some((item) => item.snapshot_id !== value.request.snapshot_id)) fail(path, "page items belong to a different snapshot");
    if (value.items.some((item) => item.membership === "private")) fail(path, "private workspace objects cannot join global catalogue listings");
    for (let index = 1; index < value.items.length; index++) {
      for (const ordering of value.request.ordering ?? []) {
        const left = ordering.field === "id" ? value.items[index - 1].id : value.items[index - 1].title.en;
        const right = ordering.field === "id" ? value.items[index].id : value.items[index].title.en;
        const comparison = compareCodepoints(left, right) * (ordering.direction === "desc" ? -1 : 1);
        if (comparison > 0) fail(path, "items do not obey their declared stable ordering");
        if (comparison < 0) break;
      }
    }
    if (value.total.entity !== "canonical_objects") fail(path, "listing totals count distinct canonical objects");
    if (value.total.value != null && offset + value.returned_count > value.total.value) fail(path, "page exceeds complete-scope total");
    if (value.next_cursor != null) {
      if (!value.items.length || await cursorOffset(value.request, value.next_cursor, `${path}.next_cursor`) !== offset + value.returned_count) fail(path, "next cursor must continue after this page");
      if (value.total.value != null && offset + value.returned_count >= value.total.value) fail(path, "terminal known page cannot advertise another page");
    }
    if (value.preview_truncated !== (value.next_cursor != null)) fail(path, "preview truncation must identify remaining pages");
    if (value.query_completion === "complete" && value.total.value != null && ((offset + value.returned_count < value.total.value) !== value.preview_truncated)) fail(path, "complete listing loses remaining inventory membership");
    if (value.availability.status !== "available" && (value.items.length || value.total.value != null)) fail(path, "unavailable listing cannot claim known empty inventory");
  }
  if (name === "OperationRequest" && !distinct((raw as OperationRequest).input_ids)) fail(path, "operation input identities must be unique");
  if (name === "OperationReceipt") {
    const value = raw as OperationReceipt;
    if (!distinct(value.inputs.map((item) => item.object_id))) fail(path, "input content identities must be unique");
    if (value.total_rows.value != null && value.returned_count > value.total_rows.value) fail(path, "returned rows exceed complete-scope count");
    if (value.query_completion === "complete" && value.total_rows.value != null && ((value.returned_count < value.total_rows.value) !== value.preview_truncated)) fail(path, "complete result must declare truncation precisely");
    if (value.scope_compatibility && value.scope_compatibility.outcome !== "compatible" && value.query_completion === "complete") fail(path, "query readiness cannot override C01 scientific scope");
    if (value.availability.status !== "available" && (value.returned_count || value.total_rows.value != null)) fail(path, "unavailable result cannot claim known empty data");
  }
  if (name === "QueryResult") {
    const value = raw as QueryResult, keys = value.columns.map((column) => column.key);
    if (value.receipt.snapshot_id !== value.snapshot_id || canonicalJson(value.receipt.scope) !== canonicalJson(value.scope)) fail(path, "result and receipt must retain snapshot and source scope");
    if (!distinct(keys) || value.rows.some((row) => canonicalJson(Object.keys(row).sort()) !== canonicalJson([...keys].sort()))) fail(path, "rows must match unique column identities");
    if (value.receipt.returned_count !== value.rows.length) fail(path, "receipt count must match result rows");
  }
}

async function walkSemantics(rule: JsonSchema | boolean, value: unknown, path: string): Promise<void> {
  if (typeof rule === "boolean") return;
  if (rule.$ref) {
    const name = rule.$ref.slice(8), target = schema.$defs?.[name];
    if (!target) return fail(path, "unsupported schema reference");
    await walkSemantics(target, value, path);
    await modelSemantics(name, value, path);
    return;
  }
  if (rule.anyOf || rule.oneOf) {
    for (const branch of rule.anyOf ?? rule.oneOf ?? []) {
      try { parseSchema(branch, value, path); } catch (error) {
        if (error instanceof CatalogueContractError) continue;
        throw error;
      }
      await walkSemantics(branch, value, path);
      break;
    }
  } else if (rule.allOf) {
    for (const branch of rule.allOf) await walkSemantics(branch, value, path);
  } else if (Array.isArray(value)) {
    for (const [index, item] of value.entries()) await walkSemantics(rule.prefixItems?.[index] ?? rule.items ?? true, item, `${path}[${index}]`);
  } else if (object(value)) {
    for (const [key, item] of Object.entries(value)) await walkSemantics(rule.properties?.[key] ?? rule.additionalProperties ?? true, item, `${path}.${key}`);
  }
}

/** Validate unknown wire input and detach/default it before any UI projection. */
export async function parseCatalogueContractModel<K extends keyof CatalogueModels>(name: K, payload: unknown): Promise<CatalogueModels[K]> {
  const definition: JsonSchema = name === "CatalogueContract" ? schema : { $ref: `#/$defs/${name}` };
  const parsed = parseSchema(definition, jsonCopy(payload), "$");
  await walkSemantics(definition, parsed, "$");
  return parsed as CatalogueModels[K];
}

export type CurrentCatalogueAccess = {
  snapshotId: string;
  accessRevision: string;
  accessBinding: string;
  /** Current authenticated authorization result, not a permission cached in the snapshot. */
  allowedIds: ReadonlySet<string>;
};
export type CatalogueBoundaryResult =
  | { status: "ready"; contract: CatalogueListing; items: PrototypeNode[]; total: number | null; returned: number; complete: boolean }
  | { status: "unavailable" | "revoked"; items: []; total: null; returned: 0; complete: false; reason: string };

const SOURCE_LABELS: Record<NonNullable<WireNode["source_family"]>, Source> = {
  ctd: "CTD", remote_sensing: "SST", metagenome: "Metagenome", edna_metabarcoding: "eDNA",
};
/** Legacy/P00 labels enter through the Python-owned positive alias registry. */
export function canonicalSourceFamily(value: unknown): NonNullable<WireNode["source_family"]> {
  if (typeof value !== "string") return fail("$.source_family", "unknown source family");
  const key = value.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu, "").toLowerCase();
  const aliases = catalogueContractSchema["x-source-aliases"] as Record<string, NonNullable<WireNode["source_family"]>>;
  if (!own(aliases, key)) return fail("$.source_family", "unknown source family");
  return aliases[key];
}
function projectNode(node: WireNode): PrototypeNode {
  const kind = ["root", "directory"].includes(node.kind) ? "directory"
    : ["dataset", "analysis", "workflow"].includes(node.kind) ? node.kind as PrototypeNode["kind"] : "reference";
  const qualification = node.availability.reason ?? `${node.authority}; scientific approval: ${node.lifecycle.scientific_approval}.`;
  return {
    id: node.id, parentId: node.parent_id, title: { ...node.title }, root: node.root, kind,
    ...(node.source_family ? { source: SOURCE_LABELS[node.source_family] } : {}),
    purpose: { ...node.purpose }, limitation: { en: qualification, ja: qualification }, relatedIds: [...(node.related_ids ?? [])],
  };
}

/** C15/C16 adopt this seam; existing P00 fixture transport remains visibly local. */
export const catalogueAdapterV1 = {
  version: VERSION,
  async list(payload: unknown, access: CurrentCatalogueAccess): Promise<CatalogueBoundaryResult> {
    const unavailable = (reason: string): CatalogueBoundaryResult => ({ status: "unavailable", items: [], total: null, returned: 0, complete: false, reason });
    if (payload == null) return unavailable("Catalogue transport is unavailable.");
    let contract: CatalogueListing;
    try { contract = await parseCatalogueContractModel("CatalogueListing", payload); } catch (error) {
      return unavailable(error instanceof CatalogueContractError ? error.message : "Catalogue payload could not be validated.");
    }
    if (contract.request.snapshot_id !== access.snapshotId) return unavailable("Catalogue snapshot does not match the selected snapshot.");
    if (contract.request.access_revision !== access.accessRevision || contract.request.access_binding !== access.accessBinding
      || contract.items.some((node) => [node.id, ...(node.related_ids ?? []), ...(node.parent_id ? [node.parent_id] : [])].some((id) => !access.allowedIds.has(id)))) {
      return { status: "revoked", items: [], total: null, returned: 0, complete: false, reason: "Current permission no longer authorizes this catalogue membership." };
    }
    if (contract.availability.status !== "available") return unavailable(contract.availability.reason ?? "Catalogue availability is unknown.");
    return {
      status: "ready", contract, items: contract.items.map(projectNode),
      total: contract.total.value ?? null, returned: contract.returned_count,
      complete: contract.query_completion === "complete",
    };
  },
};
