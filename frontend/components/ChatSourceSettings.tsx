"use client";
import { useEffect, useState } from "react";
import { ChatFilterSelect } from "@/components/ChatFilterSelect";
import { getChatFilterOptions } from "@/lib/api";
import type { ChatFilterOptions } from "@/lib/chat-filter-options";
import { useAppPreferences } from "@/lib/preferences";
import { sourceLabels, scopeErrors, type SourceFamily } from "@/lib/chat-settings";
import { evidenceScopeSchema, type EvidenceScope } from "@/lib/generated/chat-scope";

export const filterLabels: Record<string, string> = {
  time_from: "From", time_to: "To", bay: "Bay", station: "Station", sample_id: "Sample ID",
  provider: "Provider", provider_project_id: "Project ID", provider_run_id: "Run ID",
  assignment_method: "Assignment method", taxon: "Taxon", sample_kind: "Sample kind", is_control: "Control status",
  lat_min: "Minimum latitude", lat_max: "Maximum latitude", lon_min: "Minimum longitude", lon_max: "Maximum longitude",
};
const filterSchemas = {
  ctd: evidenceScopeSchema.$defs.SampleFilters, metagenome: evidenceScopeSchema.$defs.SampleFilters,
  remote_sensing: evidenceScopeSchema.$defs.Coordinates, edna_metabarcoding: evidenceScopeSchema.$defs.EdnaFilters,
};
type Field = {type?: string; enum?: readonly string[]; minimum?: number; maximum?: number; maxLength?: number; anyOf?: readonly Field[]};
export function ChatSourceSettings({ scope, onChange, analysisId, onAnalysisChange, disabled }: {
  disabled?: boolean; scope: EvidenceScope; onChange: (value: EvidenceScope) => void; analysisId: string; onAnalysisChange: (value: string) => void;
}) {
  const {ui} = useAppPreferences();
  const [catalog, setCatalog] = useState<ChatFilterOptions | null>(null);
  const [loadingChoices, setLoadingChoices] = useState(true);
  const [choicesFailed, setChoicesFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const scopeJson = JSON.stringify(scope);
  const invalid = scopeErrors(scope).length > 0;
  useEffect(() => {
    if (disabled || invalid) { setLoadingChoices(false); return; }
    const controller = new AbortController();
    setLoadingChoices(true); setChoicesFailed(false);
    const timer = setTimeout(() => {
      getChatFilterOptions({evidence_scope: JSON.parse(scopeJson)}, controller.signal)
        .then(result => { if (!controller.signal.aborted) setCatalog(result); })
        .catch(() => { if (!controller.signal.aborted) { setCatalog(null); setChoicesFailed(true); } })
        .finally(() => { if (!controller.signal.aborted) setLoadingChoices(false); });
    }, 150);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [scopeJson, disabled, invalid, retry]);
  function setFilter(family: SourceFamily, key: string, value: string, kind: string) {
    const filters = {...scope.sources[family].filters} as Record<string, unknown>;
    if (value === "") delete filters[key];
    else filters[key] = kind === "number" ? Number(value) : kind === "boolean" ? value === "true" : value;
    onChange({...scope, sources: {...scope.sources, [family]: {...scope.sources[family], filters}}});
  }
  return <fieldset className="settings-section" disabled={disabled}><legend>{ui("Evidence sources")}</legend>
    <div className="settings-pair">
      <button type="button" className="button secondary-button" onClick={() => onChange({...scope, sources: Object.fromEntries(Object.entries(scope.sources).map(([key, source]) => [key, {...source, enabled: true}])) as typeof scope.sources})}>{ui("Select all")}</button>
      <button type="button" className="button secondary-button" onClick={() => onChange({...scope, sources: Object.fromEntries(Object.entries(scope.sources).map(([key, source]) => [key, {...source, enabled: false}])) as typeof scope.sources})}>{ui("Clear selection")}</button>
    </div>
    <p className="empty-state">{ui("Select the sources to use. Filters apply only to their own source.")}</p>
    {invalid ? <p className="empty-state" role="status">{ui("Fix invalid filters to load choices.")}</p> : null}
    {choicesFailed ? <button className="button secondary-button" type="button" onClick={() => setRetry(value => value + 1)}>{ui("Retry loading choices")}</button> : null}
    {(Object.keys(sourceLabels) as SourceFamily[]).map(family => {
      const selection = scope.sources[family];
      const filters = selection.filters as Record<string, unknown>;
      return <section className="chat-source-panel" key={family}>
        <label className="checkbox-row">
          <input type="checkbox" checked={selection.enabled} onChange={event => onChange({...scope, sources: {...scope.sources, [family]: {...selection, enabled: event.target.checked}}})} />
          <span>{ui(sourceLabels[family])}</span>
        </label>
        <p className="empty-state">{Object.entries(filters).filter(([, value]) => value != null).map(([key, value]) => `${ui(filterLabels[key] || key)}: ${String(value)}`).join(" · ")}</p>
        <details><summary>{ui("Source filters")} ({Object.values(filters).filter(value => value != null).length})</summary>
          <fieldset disabled={!selection.enabled} className="chat-source-filters">
            <button className="button secondary-button" type="button" onClick={() => {
              if (family === "edna_metabarcoding") onAnalysisChange("");
              onChange({...scope, sources: {...scope.sources, [family]: {enabled: selection.enabled, filters: {}}}});
            }}>{ui("Reset source filters")}</button>
            {Object.entries(filterSchemas[family].properties).map(([key, raw]) => {
              const field = raw as Field, definition = field.anyOf?.find(item => item.type !== "null") || field;
              const kind = definition.type || "string", id = `scope-${family}-${key}`;
              const options = key === "is_control" ? ["true", "false"] : definition.enum;
              if (kind !== "number" && !key.startsWith("time_")) return <ChatFilterSelect key={key} id={id} family={family} field={key}
                label={ui(filterLabels[key] || key)} value={filters[key] == null ? "" : String(filters[key])} allowed={options}
                choices={catalog?.sources[family]?.fields[key]} scopeJson={scopeJson}
                available={catalog?.sources[family]?.available} loading={loadingChoices} failed={choicesFailed} invalidScope={invalid}
                disabled={disabled || !selection.enabled} onChange={value => setFilter(family, key, value, kind)} />;
              return <label className="settings-field" htmlFor={id} key={key}><span>{ui(filterLabels[key] || key)}</span>
                <input id={id} className="field" type={key.startsWith("time_") ? String(filters[key] || "").length > 10 ? "text" : "date" : kind === "number" ? "number" : "text"} step={kind === "number" ? "any" : undefined}
                  min={definition.minimum} max={definition.maximum} maxLength={definition.maxLength} value={filters[key] == null ? "" : String(filters[key])}
                  onChange={event => setFilter(family, key, event.target.value, kind)} />
              </label>;
            })}
            {family === "edna_metabarcoding" ? <label className="settings-field" htmlFor="chat-analysis-id"><span>{ui("eDNA analysis ID")}</span><input id="chat-analysis-id" className="field" value={analysisId} onChange={event => onAnalysisChange(event.target.value)} /><small>{ui("Analysis links apply to this chat and are not saved as defaults.")}</small></label> : null}
          </fieldset>
        </details>
      </section>;
    })}
  </fieldset>;
}
