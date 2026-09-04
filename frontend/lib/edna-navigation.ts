import type { EdnaFilters } from "./api.ts";
import { safeIsoDate } from "./citation-navigation.ts";

export const EDNA_METHODS = ["qcauto_target", "qcauto_95pct_3nn_target"];
const sampleKinds = new Set([
  "environmental", "negative_control", "positive_control", "mock_community", "unknown",
]);

export type EdnaUrlState = {
  filters: EdnaFilters;
  detectionId?: string;
  sampleOffset: number;
  detectionOffset: number;
};

export function parseEdnaState(query: string): EdnaUrlState {
  const params = new URLSearchParams(query);
  const filters: EdnaFilters = {};
  const fail = (key: string): never => { throw new Error(`Invalid eDNA ${key}.`); };
  for (const key of ["sample_id", "assay_id"] as const) {
    const value = params.get(key);
    if (value !== null) {
      if (!/^[a-f0-9]{64}$/.test(value)) fail(key);
      filters[key] = value;
    }
  }
  const detectionId = params.get("detection_id") || undefined;
  if (detectionId && !/^[a-f0-9]{64}$/.test(detectionId)) fail("detection_id");
  for (const [key, max] of [
    ["provider", 64], ["provider_project_id", 128], ["provider_run_id", 128],
    ["taxon", 200], ["assignment_method", 64], ["sample_kind", 32],
  ] as const) {
    const value = params.get(key);
    if (value !== null) {
      if (!value.trim() || value.length > max) fail(key);
      filters[key] = value;
    }
  }
  if (filters.assignment_method && !EDNA_METHODS.includes(filters.assignment_method)) fail("assignment_method");
  if (filters.sample_kind && !sampleKinds.has(filters.sample_kind)) fail("sample_kind");
  const control = params.get("is_control");
  if (control !== null) {
    if (!["true", "false"].includes(control)) fail("is_control");
    filters.is_control = control === "true";
  }
  for (const key of ["time_from", "time_to"] as const) {
    const value = params.get(key);
    if (value !== null) {
      const date = safeIsoDate(value);
      if (!date) fail(key);
      filters[key] = date || undefined;
    }
  }
  if (filters.time_from && filters.time_to && filters.time_from > filters.time_to) fail("date range");
  for (const [key, max] of [["lat_min", 90], ["lat_max", 90], ["lon_min", 180], ["lon_max", 180]] as const) {
    const value = params.get(key);
    if (value !== null) {
      const number = Number(value);
      if (!value.trim() || !Number.isFinite(number) || Math.abs(number) > max) fail(key);
      filters[key] = number;
    }
  }
  if (filters.lat_min !== undefined && filters.lat_max !== undefined && filters.lat_min > filters.lat_max) fail("latitude range");
  if (filters.lon_min !== undefined && filters.lon_max !== undefined && filters.lon_min > filters.lon_max) fail("longitude range");
  function offset(key: string): number {
    const value = params.get(key) || "0";
    if (!/^\d+$/.test(value) || Number(value) > 10_000_000) fail(key);
    return Number(value);
  }
  return { filters, detectionId, sampleOffset: offset("sample_offset"), detectionOffset: offset("detection_offset") };
}

export function ednaHref(filters: EdnaFilters, state: Partial<Omit<EdnaUrlState, "filters">> = {}): string {
  const params = new URLSearchParams({ view: "edna" });
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  if (state.detectionId) params.set("detection_id", state.detectionId);
  if (state.sampleOffset) params.set("sample_offset", String(state.sampleOffset));
  if (state.detectionOffset) params.set("detection_offset", String(state.detectionOffset));
  return `/data?${params}`;
}
