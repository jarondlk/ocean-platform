"use client";

import { coverageNotice, sourceCoverageRows } from "@/lib/source-coverage";
import { useAppPreferences } from "@/lib/preferences";

export function SourceCoverage({diagnostics}: {diagnostics: unknown}) {
  const { ui } = useAppPreferences();
  const rows = sourceCoverageRows(diagnostics);
  const notice = coverageNotice(diagnostics);
  if (!rows.length && !notice) return null;
  return <section aria-label={ui("Source evidence coverage")} className="source-coverage">
    {notice ? <p role="status" className="warning-text">{ui(notice)}</p> : null}
    <ul>
      {rows.map(row => <li key={row.family}>
        <strong>{ui(row.label)}</strong>: {ui(row.text)}
        {row.limited || row.supplied === null ? <> — {ui(row.state)}</> : null}
        {row.degraded ? <>. {ui("Search completed with a degraded retrieval branch.")}</> : null}
      </li>)}
    </ul>
    <p className="empty-state">{ui("Counts describe retrieved or supplied evidence, not complete database coverage or verified scientific matches.")}</p>
  </section>;
}
