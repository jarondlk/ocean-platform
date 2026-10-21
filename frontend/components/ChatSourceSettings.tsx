"use client";
import { useEffect, useState } from "react";
import { ChatFilterSelect } from "@/components/ChatFilterSelect";
import { getChatFilterOptions, request } from "@/lib/api";
import type { ResearchIntent } from "@/types";
import type { ChatFilterOptions } from "@/lib/chat-filter-options";
import { useAppPreferences } from "@/lib/preferences";
import { cop17Demo, defaultScope, demoSetups, preferredDemoSetup, sourceLabels, scopeErrors, visibleSourceFamilies, type PublishedDemoOption, type SourceFamily } from "@/lib/chat-settings";
import { evidenceScopeSchema, type EvidenceScope } from "@/lib/generated/chat-scope";

export const filterLabels: Record<string, string> = {
  dataset_id: "SST dataset", time_from: "From", time_to: "To", bay: "Bay", station: "Station", sample_id: "Sample ID",
  provider: "Provider", provider_project_id: "Project ID", provider_run_id: "Run ID",
  assignment_method: "Assignment method", taxon: "Taxon", sample_kind: "Sample kind", is_control: "Control status",
  lat_min: "Minimum latitude", lat_max: "Maximum latitude", lon_min: "Minimum longitude", lon_max: "Maximum longitude",
};
const filterSchemas = {
  ctd: evidenceScopeSchema.$defs.SampleFilters, metagenome: evidenceScopeSchema.$defs.SampleFilters,
  remote_sensing: evidenceScopeSchema.$defs.SatelliteFilters, edna_metabarcoding: evidenceScopeSchema.$defs.EdnaFilters,
};
type Field = {type?: string; enum?: readonly string[]; minimum?: number; maximum?: number; maxLength?: number; anyOf?: readonly Field[]};
type PublishedOption = PublishedDemoOption & { analysis_id: string; status: string; analysis_kind: string; label: string; time_from?: string; time_to?: string; protocol_ids: string[]; protocol_labels?: Record<string, string>; workflows: {kind: ResearchIntent["kind"]; question: string}[] };
export function ChatSourceSettings({ scope, onChange, analysisId, onAnalysisChange, disabled, researchIntent, onResearchChange, autoEnabled = false, autoAvailable = false, onAutoChange, onPresetChange }: {
  disabled?: boolean; scope: EvidenceScope; onChange: (value: EvidenceScope) => void; analysisId: string; onAnalysisChange: (value: string) => void;
  researchIntent?: ResearchIntent; onResearchChange?: (intent: ResearchIntent | undefined, question?: string) => void;
  onPresetChange?: (setup: {scope: EvidenceScope; analysisId: string; intent?: ResearchIntent; question?: string}) => void;
  autoEnabled?: boolean; autoAvailable?: boolean; onAutoChange?: (enabled: boolean) => void;
}) {
  const {ui} = useAppPreferences();
  const [catalog, setCatalog] = useState<ChatFilterOptions | null>(null);
  const [loadingChoices, setLoadingChoices] = useState(true);
  const [choicesFailed, setChoicesFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [analysisOptions, setAnalysisOptions] = useState<PublishedOption[]>([]);
  const [analysisError, setAnalysisError] = useState("");
  const [setupKey, setSetupKey] = useState("");
  const setups = demoSetups(analysisOptions);
  const selectedSetupKey = setupKey || preferredDemoSetup(setups);
  const setup = setups.find(item => item.key === selectedSetupKey);
  const selectedAnalysis = analysisOptions.find(option => option.analysis_id === analysisId);
  useEffect(() => {
    if (disabled) return;
    let active = true;
    setAnalysisError("");
    request<{options: PublishedOption[]}>("/chat/analysis-options")
      .then(value => { if (active) setAnalysisOptions(value.options); })
      .catch(() => { if (active) setAnalysisError("Published analysis choices are unavailable. Your selection was retained."); });
    return () => { active = false; };
  }, [disabled, retry]);
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
  function applyPreset(kind: "fish_frequency" | "temperature_comparison") {
    if (!setup || !onPresetChange) return;
    const workflow = setup.option.workflows.find(workflow => workflow.kind === kind);
    if (!workflow || kind === "temperature_comparison" && !setup.option.sst_available) return;
    const next = defaultScope();
    next.sources.remote_sensing.enabled = kind === "temperature_comparison";
    if (kind === "temperature_comparison" && setup.option.sst_dataset_id) next.sources.remote_sensing.filters = {dataset_id: setup.option.sst_dataset_id};
    onPresetChange({scope: next, analysisId: setup.option.analysis_id,
      intent: {kind, protocol_id: setup.protocolId}, question: ui(workflow.question)});
  }
  return <fieldset className="settings-section" disabled={disabled}><legend>{ui("Evidence sources")}</legend>
    {cop17Demo ? <section className="cop17-presets" aria-label={ui("Published analysis presets")}>
      <h4>{ui("Published analysis presets")}</h4>
      <p className="empty-state">{ui("Choose a complete setup, then select an analysis. You can edit the question before asking.")}</p>
      <label className="settings-field" htmlFor="chat-demo-setup"><span>{ui("Dataset and assay")}</span>
        <select id="chat-demo-setup" className="field" value={selectedSetupKey} onChange={event => setSetupKey(event.target.value)}>
          <option value="">{ui("Choose a dataset and assay")}</option>
          {setupKey && !setup ? <option value={setupKey}>{ui("Selected setup is unavailable")}</option> : null}
          {setups.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
        </select>
      </label>
      <div className="cop17-preset-buttons">
        <button className="button secondary-button" type="button" disabled={!setup?.option.workflows.some(w => w.kind === "fish_frequency")} onClick={() => applyPreset("fish_frequency")}>{ui("Fish detection frequency")}</button>
        <button className="button secondary-button" type="button" disabled={!setup?.option.sst_available || !setup.option.workflows.some(w => w.kind === "temperature_comparison")} onClick={() => applyPreset("temperature_comparison")}>{ui("Fish and sea surface temperature")}</button>
        <button className="button secondary-button" type="button" onClick={() => onPresetChange?.({scope: defaultScope(), analysisId: ""})}>{ui("Free-text search")}</button>
      </div>
      <p className="empty-state">{ui("Presets replace source filters with the published setup. Published datasets are fixed; detection frequency is not abundance.")}</p>
      {selectedAnalysis ? <p role="status">{ui("Selected analysis")}: {selectedAnalysis.label} · {ui(researchIntent?.kind === "temperature_comparison" ? "Fish and sea surface temperature" : "Fish detection frequency")}</p> : null}
      {analysisError ? <p role="status">{ui(analysisError)}</p> : null}
    </section> : null}
    <div className={`settings-pair${onAutoChange ? ' auto-settings-toolbar' : ''}`}>
      <button type="button" className="button secondary-button" onClick={() => onChange({...scope, sources: Object.fromEntries(Object.entries(scope.sources).map(([key, source]) => [key, {...source, enabled: visibleSourceFamilies.includes(key as SourceFamily)}])) as typeof scope.sources})}>{ui("Select all")}</button>
      <button type="button" className="button secondary-button" onClick={() => onChange({...scope, sources: Object.fromEntries(Object.entries(scope.sources).map(([key, source]) => [key, {...source, enabled: false}])) as typeof scope.sources})}>{ui("Clear selection")}</button>
      {onAutoChange && !cop17Demo ? <button type="button" className={`button secondary-button auto-settings-toggle${autoEnabled ? ' active' : ''}`}
        aria-pressed={autoEnabled} disabled={!autoAvailable && !autoEnabled}
        onClick={() => onAutoChange(!autoEnabled)}>{ui("AUTO")}</button> : null}
    </div>
    {autoEnabled ? <p className="empty-state" role="status">{ui("AUTO selects sources and filters when you ask. Editing settings switches to manual.")}</p> : null}
    <p className="empty-state">{ui("Select the sources to use. Filters apply only to their own source.")}</p>
    {invalid ? <p className="empty-state" role="status">{ui("Fix invalid filters to load choices.")}</p> : null}
    {choicesFailed || analysisError ? <button className="button secondary-button" type="button" onClick={() => setRetry(value => value + 1)}>{ui("Retry loading choices")}</button> : null}
    {visibleSourceFamilies.map(family => {
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
            {family === "edna_metabarcoding" && !cop17Demo ? <>
              <label className="settings-field" htmlFor="chat-analysis-id"><span>{ui("Published eDNA analysis")}</span>
                <select id="chat-analysis-id" className="field" value={analysisId} onChange={event => { onAnalysisChange(event.target.value); onResearchChange?.(undefined); }}>
                  <option value="">No analysis selected</option>
                  {analysisId && !selectedAnalysis ? <option value={analysisId}>Selected analysis · {analysisId.slice(0, 12)} · unavailable</option> : null}
                  {analysisOptions.map(option => <option key={option.analysis_id} value={option.analysis_id} disabled={option.status !== "current"}>{option.label} · {option.time_from || ""}–{option.time_to || ""} · {option.status.replaceAll("_", " ")} · {option.analysis_id.slice(0, 12)}</option>)}
                </select>
                <small>{ui("Analysis links apply to this chat and are not saved as defaults.")}</small>
              </label>
              {analysisError ? <p role="status">{analysisError}</p> : null}
              {selectedAnalysis && ["detection_frequency", "provisional_demo", "regional_frequency"].includes(selectedAnalysis.analysis_kind) ? <>
                <label className="settings-field">Research workflow<select className="field" value={researchIntent?.kind || ""} onChange={event => { const workflow = selectedAnalysis.workflows.find(value => value.kind === event.target.value); onResearchChange?.(workflow ? {kind: workflow.kind, protocol_id: researchIntent?.protocol_id} : undefined, workflow?.question); }}><option value="">Recognize a supported question</option>{selectedAnalysis.workflows.map(workflow => <option key={workflow.kind} value={workflow.kind}>{workflow.question}</option>)}</select></label>
                {researchIntent && selectedAnalysis.protocol_ids.length > 1 ? <label className="settings-field">Assay protocol<select className="field" value={researchIntent.protocol_id || ""} onChange={event => onResearchChange?.({...researchIntent, protocol_id: event.target.value || undefined})}><option value="">Select a comparable protocol</option>{selectedAnalysis.protocol_ids.map(id => <option key={id} value={id}>{selectedAnalysis.protocol_labels?.[id] || id.slice(0, 12)}</option>)}</select></label> : null}
                <small>Published cohorts and product panels are fixed. Conflicting source filters require clarification; check SST explicitly for temperature workflows.</small>
              </> : null}
            </> : null}
          </fieldset>
        </details>
      </section>;
    })}
  </fieldset>;
}
