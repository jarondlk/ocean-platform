export type CoverageBin = { month: string; count: number; observed_days: number | null; expected_days?: number | null; missing_days?: number | null };
export type CoverageSource = {
  id: string;
  label: string;
  count_unit: string;
  temporal_precision: string;
  date_basis: string;
  scope: string;
  status: "available" | "empty" | "unavailable";
  reason: string | null;
  observed_start: string | null;
  observed_end: string | null;
  total_count: number | null;
  undated_count: number | null;
  excluded_count: number | null;
  source_binding: Record<string, string>;
  categories: Record<string, number>;
  bins: CoverageBin[];
  missing_dates_within_extent: string[];
  missing_day_count: number | null;
  missing_dates_truncated: boolean;
};
export type OverviewCoverage = {
  calendar: string;
  resolution: string;
  generated_at: string;
  sources: CoverageSource[];
};

function monthIndex(month: string): number | null {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return null;
  const [year, number] = month.split("-").map(Number);
  return year >= 1900 && year <= 2100 ? year * 12 + number - 1 : null;
}

export function coverageMonths(sources: CoverageSource[]): string[] {
  const indexes = sources.filter(source => source.status !== "unavailable")
    .flatMap(source => source.bins.filter(bin => bin.count > 0).map(bin => monthIndex(bin.month)))
    .filter((value): value is number => value !== null);
  if (!indexes.length) return [];
  const first = Math.min(...indexes), last = Math.max(...indexes);
  return Array.from({ length: last - first + 1 }, (_, offset) => {
    const value = first + offset;
    return `${Math.floor(value / 12)}-${String(value % 12 + 1).padStart(2, "0")}`;
  });
}

export function sharedMonths(sources: CoverageSource[], selected: string[]): {
  state: "choose" | "unknown" | "known"; months: string[];
} {
  const identities = [...new Set(selected)];
  if (identities.length < 2) return { state: "choose", months: [] };
  const rows = identities.map(id => sources.find(source => source.id === id));
  if (rows.some(row => !row || row.status === "unavailable")) return { state: "unknown", months: [] };
  const sets = rows.map(row => new Set(row!.bins.filter(bin => bin.count > 0 && monthIndex(bin.month) !== null).map(bin => bin.month)));
  return { state: "known", months: [...sets[0]].filter(month => sets.every(set => set.has(month))).sort() };
}

export function coverageRange(source: CoverageSource): string | null {
  return source.observed_start && source.observed_end
    ? `${source.observed_start} – ${source.observed_end}` : null;
}
