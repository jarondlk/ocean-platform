import type { EvidenceScope } from "./generated/chat-scope";

export type SourceFamily = keyof EvidenceScope["sources"];
export type FilterChoices = {values: string[]; truncated: boolean};
export type ChatFilterOptions = {
  backend: "local" | "postgres";
  sources: Partial<Record<SourceFamily, {available: boolean; fields: Record<string, FilterChoices>}>>;
};
export type ChatFilterOptionsRequest = {evidence_scope: EvidenceScope; family?: SourceFamily; field?: string; search?: string};

export function selectionChoices(choices: FilterChoices | undefined, current: string, allowed?: readonly string[]) {
  const values = (choices?.values || []).filter(value => !allowed || allowed.includes(value));
  // A saved or pinned value must remain visible even when its cohort is unavailable.
  return [...new Set(current ? [current, ...values] : values)].map(value => ({
    value, unavailable: value === current && !values.includes(value),
  }));
}
