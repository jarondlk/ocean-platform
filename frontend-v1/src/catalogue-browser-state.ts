/** Pure standalone navigation. Scientific scope and current identity are supplied externally. */
import type { CatalogueFilters, EvidenceScope } from "./catalogue-service.ts";
export const DATASET_SECTIONS = ["overview", "tables", "coverage", "methods", "provenance", "related"] as const;
export type DatasetSection = typeof DATASET_SECTIONS[number];
export type CatalogueLocation = {
  snapshotId: string | null; nodeId: string | null; parentId: string | null;
  filters: CatalogueFilters; cursor: string | null; section: DatasetSection; limit: number;
};
/** Emitted only by an explicit selection action; this event does not attach or pin anything. */
export type CatalogueSelectionEvent = { type: "catalogue.selection"; object_id: string; snapshot_id: string; scope: EvidenceScope };
export class CatalogueLocationError extends Error { constructor() { super("Catalogue location is invalid"); this.name = "CatalogueLocationError"; } }
const roots = ["data", "analyses", "statistics", "metadata", "relationships"] as const;
const sources = ["ctd", "metagenome", "remote_sensing", "edna_metabarcoding"] as const;
const kinds = ["root", "directory", "dataset", "table", "analysis", "statistic", "metadata", "relationship", "reference", "workflow"] as const;
const authorities = ["descriptive", "published", "experimental"] as const;
const keys = ["snapshot", "node", "parent", "search", "roots", "sources", "kinds", "authorities", "cursor", "section", "limit"] as const;
const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/;
function fail(): never { throw new CatalogueLocationError(); }
function id(value: unknown): string | null { if (value === null) return null; if (typeof value !== "string" || !identifier.test(value)) return fail(); return value; }
function selection<T extends string>(value: unknown, allowed: readonly T[]): T[] {
  if (!Array.isArray(value) || value.some((v) => typeof v !== "string" || !allowed.includes(v as T)) || new Set(value).size !== value.length) return fail();
  return allowed.filter((v) => value.includes(v));
}
function filters(value: CatalogueFilters): CatalogueFilters {
  if (value === null || typeof value !== "object" || Array.isArray(value) || Object.keys(value).some((v) => !["roots", "source_families", "kinds", "authorities", "search"].includes(v))) return fail();
  const search = value.search ?? null;
  if (search !== null && (typeof search !== "string" || Array.from(search).length > 4000 || !search.trim())) return fail();
  return { roots: selection(value.roots ?? [], roots), source_families: selection(value.source_families ?? [], sources), kinds: selection(value.kinds ?? [], kinds), authorities: selection(value.authorities ?? [], authorities), search };
}
function normalize(value: CatalogueLocation): CatalogueLocation {
  if (!DATASET_SECTIONS.includes(value.section) || !Number.isSafeInteger(value.limit) || value.limit < 1 || value.limit > 500 || (value.cursor !== null && (typeof value.cursor !== "string" || !value.cursor || value.cursor.length > 2048))) return fail();
  return { snapshotId: id(value.snapshotId), nodeId: id(value.nodeId), parentId: id(value.parentId), filters: filters(value.filters), cursor: value.cursor, section: value.section, limit: value.limit };
}
export function parseCatalogueLocation(search: string): CatalogueLocation {
  if (typeof search !== "string" || search.length > 64 * 1024) return fail();
  const query = new URLSearchParams(search);
  for (const key of keys) if (query.getAll(key).length > 1) return fail();
  const get = (key: typeof keys[number]) => query.get(key);
  const multi = <T extends string>(key: typeof keys[number], allowed: readonly T[]) => { const value = get(key); return selection(value === null ? [] : value.split(","), allowed); };
  const rawLimit = get("limit"); if (rawLimit !== null && !/^[1-9]\d{0,2}$/.test(rawLimit)) return fail();
  return normalize({ snapshotId: get("snapshot"), nodeId: get("node"), parentId: get("parent"),
    filters: { roots: multi("roots", roots), source_families: multi("sources", sources), kinds: multi("kinds", kinds), authorities: multi("authorities", authorities), search: get("search") },
    cursor: get("cursor"), section: (get("section") ?? "overview") as DatasetSection, limit: rawLimit === null ? 100 : Number(rawLimit),
  });
}
export function catalogueLocationUrl(input: CatalogueLocation): string {
  const value = normalize(input), query = new URLSearchParams({ view: "catalogue" });
  for (const [key, item] of [["snapshot", value.snapshotId], ["node", value.nodeId], ["parent", value.parentId], ["search", value.filters.search], ["roots", value.filters.roots?.join(",")], ["sources", value.filters.source_families?.join(",")], ["kinds", value.filters.kinds?.join(",")], ["authorities", value.filters.authorities?.join(",")], ["cursor", value.cursor]] as const) if (item) query.set(key, item);
  if (value.section !== "overview") query.set("section", value.section);
  if (value.limit !== 100) query.set("limit", String(value.limit));
  return `/?${query.toString()}`;
}
export function updateCatalogueLocation(current: CatalogueLocation, patch: Partial<CatalogueLocation>): CatalogueLocation {
  if (patch === null || typeof patch !== "object" || Array.isArray(patch) || Object.keys(patch).some((key) => !["snapshotId", "nodeId", "parentId", "filters", "cursor", "section", "limit"].includes(key))) return fail();
  const before = normalize(current), merged = normalize({ ...before, ...patch });
  const changedSnapshot = before.snapshotId !== merged.snapshotId;
  const changedMembers = changedSnapshot || before.parentId !== merged.parentId || before.limit !== merged.limit || JSON.stringify(before.filters) !== JSON.stringify(merged.filters);
  if (changedMembers) merged.cursor = null;
  if (changedSnapshot) { if (!Object.hasOwn(patch, "nodeId")) merged.nodeId = null; if (!Object.hasOwn(patch, "parentId")) merged.parentId = null; if (!Object.hasOwn(patch, "section")) merged.section = "overview"; }
  if (before.nodeId !== merged.nodeId && !Object.hasOwn(patch, "section")) merged.section = "overview";
  return merged;
}
