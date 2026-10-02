"use client";

import { useEffect, useState } from "react";
import { getChatFilterOptions } from "@/lib/api";
import { selectionChoices, type FilterChoices, type SourceFamily } from "@/lib/chat-filter-options";
import { useAppPreferences } from "@/lib/preferences";

export function ChatFilterSelect({id, family, field, label, value, choices, scopeJson, disabled, loading, available, failed, invalidScope, allowed, onChange}: {
  id: string; family: SourceFamily; field: string; label: string; value: string;
  choices?: FilterChoices; scopeJson: string; disabled?: boolean; loading: boolean;
  available?: boolean; failed: boolean; invalidScope: boolean; allowed?: readonly string[]; onChange: (value: string) => void;
}) {
  const {ui} = useAppPreferences();
  const [search, setSearch] = useState("");
  const [searched, setSearched] = useState<FilterChoices>();
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  useEffect(() => {
    setSearched(undefined); setSearchFailed(false);
    if (!search.trim() || disabled || loading || failed || invalidScope) { setSearchLoading(false); return; }
    const controller = new AbortController();
    setSearchLoading(true);
    const timer = setTimeout(() => {
      getChatFilterOptions({evidence_scope: JSON.parse(scopeJson), family, field, search}, controller.signal)
        .then(result => { if (!controller.signal.aborted) setSearched(result.sources[family]?.fields[field]); })
        .catch(() => { if (!controller.signal.aborted) setSearchFailed(true); })
        .finally(() => { if (!controller.signal.aborted) setSearchLoading(false); });
    }, 250);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [scopeJson, family, field, search, disabled, loading, failed, invalidScope]);

  const effective = search.trim() ? searched : choices;
  const busy = loading || searchLoading;
  const error = failed || searchFailed;
  const options = selectionChoices(effective, value, allowed);
  const searchVisible = !!search || !!choices?.truncated || (choices?.values.length || 0) > 20;
  function display(option: string) {
    if (field === "bay") return ui(({O: "Onagawa", I: "Ishinomaki", M: "Mutsu"} as Record<string, string>)[option] || option);
    if (field === "is_control") return ui(option === "true" ? "Control" : "Non-control");
    return allowed ? ui(option.replaceAll("_", " ")) : option;
  }
  return <div className="settings-field">
    <label htmlFor={id}>{label}</label>
    {searchVisible ? <input className="field" type="search" aria-label={`${ui("Search choices")} — ${label}`}
      placeholder={ui("Search choices")} value={search} maxLength={200} disabled={disabled || failed || invalidScope}
      onChange={event => setSearch(event.target.value)} /> : null}
    <select className="field" id={id} value={value} disabled={disabled || busy} aria-describedby={`${id}-choices`}
      onChange={event => onChange(event.target.value)}>
      <option value="">{ui("Any")}</option>
      {options.map(option => <option key={option.value} value={option.value}>
        {display(option.value)}{option.unavailable && !busy && !error && !effective?.truncated && !search.trim() ? ` (${ui("Not available with these filters")})` : ""}
      </option>)}
    </select>
    <small id={`${id}-choices`} role="status">{ui(invalidScope ? "Fix invalid filters to load choices." : busy ? "Loading choices…" : error ? "Filter choices are unavailable. Try again."
      : available === false ? "No data available for this source." : effective?.truncated ? "More choices available. Search to narrow the list."
      : !effective?.values.length ? "No matching choices. Adjust the other source filters." : "Choices match the other filters for this source.")}</small>
  </div>;
}
