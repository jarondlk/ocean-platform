"use client";

import { useEffect, useMemo, useState } from "react";
import { getOverviewCoverage } from "@/lib/api";
import { useAppPreferences } from "@/lib/preferences";
import { coverageMonths, coverageRange, sharedMonths, type OverviewCoverage } from "@/lib/temporal-coverage";

const sourceIds = ["ctd", "metagenome", "edna_metabarcoding", "remote_sensing"];

export function OverviewTemporalCoverage() {
  const [coverage, setCoverage] = useState<OverviewCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    getOverviewCoverage().then(data => { if (active) setCoverage(data); })
      .catch(() => { if (active) { setCoverage(null); setError("Unable to load source coverage."); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  return <TemporalCoverageTimeline coverage={coverage} loading={loading} error={error} onRefresh={() => setRevision(value => value + 1)} />;
}

type Props = { coverage: OverviewCoverage | null; loading?: boolean; error?: string; onRefresh: () => void };

export function TemporalCoverageTimeline({ coverage, loading = false, error = "", onRefresh }: Props) {
  const { ui } = useAppPreferences();
  const [selected, setSelected] = useState(sourceIds);
  const [focused, setFocused] = useState<{ source: string; month: string } | null>(null);
  const sources = coverage?.sources || [];
  const months = useMemo(() => coverageMonths(sources), [sources]);
  const overlap = sharedMonths(sources, selected);
  const common = new Set(overlap.months);
  const activeSource = sources.find(source => source.id === focused?.source);
  const activeBin = activeSource?.bins.find(bin => bin.month === focused?.month);
  const activeGaps = activeSource?.missing_dates_within_extent.filter(day => day.slice(0, 7) === focused?.month) || [];
  const status = overlap.state === "choose" ? ui("Select at least two sources to compare months.")
    : overlap.state === "unknown" ? ui("Shared months are unknown while a selected source is unavailable.")
    : overlap.months.length ? `${ui("Months with records in all selected sources")}: ${overlap.months.length}`
    : ui("No months have records in all selected sources.");
  const gridStyle = { gridTemplateColumns: `repeat(${Math.max(months.length, 1)}, minmax(8px, 1fr))` };

  return <section className="data-section overview-temporal" aria-label={ui("Data coverage over time")} aria-busy={loading}>
    <div className="temporal-heading">
      <h3 className="section-title">{ui("Data coverage over time")}</h3>
      <button type="button" className="button secondary-button" onClick={onRefresh} disabled={loading}>{ui("Refresh")}</button>
    </div>
    <p className="empty-state">{ui("Shared months describe time coverage; locations and samples may differ.")}</p>
    {loading ? <p role="status">{ui("Loading source coverage.")}</p> : null}
    {error ? <p role="alert" className="error-text">{ui(error)}</p> : null}
    {coverage ? <>
      <fieldset className="temporal-selection">
        <legend>{ui("Sources to compare")}</legend>
        {sources.map(source => <label key={source.id}>
          <input type="checkbox" checked={selected.includes(source.id)} onChange={event => setSelected(value => event.target.checked ? [...value, source.id] : value.filter(id => id !== source.id))} />
          {ui(source.label)}
        </label>)}
      </fieldset>
      <p role="status" className="temporal-overlap-summary">{status}</p>
      <p className="empty-state">{ui("Filled cells indicate months with records, not continuous coverage.")} {ui("Underlined SST months contain missing days.")} {ui("Calendar")}: {coverage.calendar}</p>
      {months.length ? <div className="temporal-scroll" role="region" aria-label={ui("Monthly source timeline")} tabIndex={0}>
        <div className="temporal-chart" style={{ minWidth: Math.max(620, months.length * 9 + 210) }}>
          <div className="temporal-axis"><span>{ui("Source")}</span><div className="temporal-months" style={gridStyle}>
            {months.map((month, index) => <span className="temporal-year" key={month}>{index === 0 || month.endsWith("-01") ? month.slice(0, 4) : ""}</span>)}
          </div></div>
          {sources.map(source => {
            const bins = new Map(source.bins.map(bin => [bin.month, bin]));
            return <div className="temporal-row" key={source.id}>
              <div className="temporal-label"><strong>{ui(source.label)}</strong><span>{source.total_count === null ? ui("Unavailable") : `${source.total_count.toLocaleString()} ${ui(source.count_unit)}`}</span><span>{coverageRange(source)}</span>{source.missing_day_count ? <span>{ui("Missing days within range")}: {source.missing_day_count}</span> : null}</div>
              <div className="temporal-months" style={gridStyle}>
                {months.map((month, index) => {
                  const bin = bins.get(month);
                  const occupied = source.status === "available" && Boolean(bin?.count);
                  const inExtent = source.observed_start && source.observed_end && month >= source.observed_start.slice(0, 7) && month <= source.observed_end.slice(0, 7);
                  const description = `${ui(source.label)} · ${month}: ${source.status === "unavailable" ? ui("Unavailable") : `${bin?.count || 0} ${ui(source.count_unit)}`}${bin?.missing_days ? ` · ${ui("Missing days within range")}: ${bin.missing_days}` : ""}`;
                  return <button type="button" key={month} className="temporal-cell" data-present={occupied} data-extent={Boolean(inExtent)} data-shared={occupied && common.has(month)} data-unavailable={source.status === "unavailable"}
                    data-incomplete={Boolean(bin?.missing_days)}
                    tabIndex={(focused?.source === source.id ? focused.month === month : index === 0) ? 0 : -1}
                    onKeyDown={event => {
                      const target = event.key === "ArrowRight" ? Math.min(index + 1, months.length - 1)
                        : event.key === "ArrowLeft" ? Math.max(index - 1, 0)
                        : event.key === "Home" ? 0 : event.key === "End" ? months.length - 1 : null;
                      if (target !== null) { event.preventDefault(); (event.currentTarget.parentElement?.children[target] as HTMLElement | undefined)?.focus(); }
                    }}
                    aria-label={description} title={description} onFocus={() => setFocused({ source: source.id, month })} onMouseEnter={() => setFocused({ source: source.id, month })} onClick={() => setFocused({ source: source.id, month })} />;
                })}
              </div>
            </div>;
          })}
          <div className="temporal-axis temporal-shared-row"><span>{ui("Shared months")}</span><div className="temporal-months" style={gridStyle} aria-hidden="true">
            {months.map(month => <span key={month} className="temporal-cell" data-shared={common.has(month)} />)}
          </div></div>
        </div>
      </div> : <p className="empty-state">{ui("No dated source records are available.")}</p>}
      <div className="temporal-detail" aria-live="polite">
        {activeSource && focused ? <>
          <strong>{ui(activeSource.label)} · {focused.month}</strong>
          <span>{activeSource.status === "unavailable" ? ui("Source coverage is unavailable.") : `${activeBin?.count || 0} ${ui(activeSource.count_unit)}`}</span>
          <span>{ui("Date precision")}: {ui(activeSource.temporal_precision)}</span>
          {activeBin?.observed_days != null ? <span>{ui("Observed days")}: {activeBin.observed_days}{activeBin.expected_days != null ? ` / ${activeBin.expected_days} ${ui("Days within observed range")}` : ""}</span> : null}
          {activeBin?.missing_days ? <span>{ui("Missing days within range")}: {activeBin.missing_days}</span> : null}
          {activeGaps.length ? <span>{ui("Missing SST dates within observed range")}: {activeGaps.join(", ")}</span> : null}
        </> : <span>{ui("Hover, focus, or select a month for details.")}</span>}
      </div>
      <details className="temporal-table"><summary>{ui("Coverage ranges and source details")}</summary>
        <div className="table-wrap"><table><thead><tr>{["Source", "Observed range", "Records", "Source details"].map(label => <th key={label}>{ui(label)}</th>)}</tr></thead>
          <tbody>{sources.map(source => <tr key={source.id}>
            <td>{ui(source.label)}</td><td>{coverageRange(source) || ui(source.status === "unavailable" ? "Unavailable" : "No dated records")}</td>
            <td>{source.total_count === null ? "—" : `${source.total_count.toLocaleString()} ${ui(source.count_unit)}`}</td>
            <td>
              <p>{ui(source.scope)}</p>
              {source.reason ? <p>{ui(source.reason)}</p> : null}
              {source.undated_count ? <p>{ui("Undated records")}: {source.undated_count}</p> : null}
              {source.excluded_count ? <p>{ui("Excluded unusable records")}: {source.excluded_count}</p> : null}
              {Object.keys(source.categories).length ? <p>{ui("Controls")}: {source.categories.controls || 0} · {ui("Environmental occurrences")}: {source.categories.environmental || 0} · {ui("Unknown or other classifications")}: {source.categories.unknown_or_other || 0}</p> : null}
              {source.missing_day_count !== null ? <p>{ui("Missing SST dates within observed range")}: {source.missing_day_count}{source.missing_dates_within_extent.length ? ` (${source.missing_dates_within_extent.join(", ")})` : ""}{source.missing_dates_truncated ? ` · ${ui("Date list truncated")}` : ""}</p> : null}
              {source.id === "edna_metabarcoding" ? <p>{ui("Counts are provider occurrences; physical sample identity and analysis eligibility are separate.")}</p> : null}
            </td>
          </tr>)}</tbody></table></div>
      </details>
      <p className="empty-state">{ui("Coverage refreshed at")}: {coverage.generated_at.replace("T", " ").slice(0, 19)} UTC</p>
    </> : null}
  </section>;
}
