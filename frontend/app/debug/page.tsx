"use client";

import { useEffect, useMemo, useState } from "react";
import { getDebugState } from "@/lib/api";
import type { DebugState } from "@/types";
import { formatCell } from "@/components/DataTable";

type ClientDebug = {
  location: string;
  userAgent: string;
  language: string;
  timezone: string;
  viewport: string;
  timestamp: string;
};

export default function DebugPage() {
  const [debug, setDebug] = useState<DebugState | null>(null);
  const [clientDebug, setClientDebug] = useState<ClientDebug | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const payload = await getDebugState();
      setDebug(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Debug request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    setClientDebug({
      location: window.location.href,
      userAgent: navigator.userAgent,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      timestamp: new Date().toISOString(),
    });
  }, []);

  const app = asRecord(debug?.app);
  const config = asRecord(debug?.config);
  const health = asRecord(debug?.health);
  const stats = asRecord(debug?.stats);
  const artifacts = asRecord(debug?.artifacts);
  const datasets = asRecord(debug?.datasets);
  const routes = Array.isArray(debug?.routes) ? debug.routes : [];

  const summaryRows = useMemo<[string, unknown][]>(
    () => [
      ["API", health.status || "unknown"],
      ["Database", formatNested(asRecord(health.database).available)],
      ["Ollama", formatNested(asRecord(health.ollama).available)],
      ["Artifacts", Object.keys(artifacts).length],
      ["Datasets", Object.keys(datasets).length],
      ["Routes", routes.length],
      ["Project root", app.project_root],
      ["Ollama URL", config.ollama_base_url],
      ["Database URL", config.database_url],
    ],
    [app, artifacts, config, datasets, health, routes],
  );

  return (
    <section>
      <header className="page-header">
        <h2>Debug</h2>
      </header>

      <div className="section-toolbar">
        <span className="empty-state">{loading ? "Loading debug payload." : "Debug payload loaded."}</span>
        <button className="button secondary-button" onClick={() => void load()} type="button">
          Refresh
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <section className="debug-section">
        <h3 className="section-title">Summary</h3>
        <table className="debug-table">
          <tbody>
            {summaryRows.map(([key, value]) => (
              <tr key={String(key)}>
                <th scope="row">{key}</th>
                <td>{formatNested(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="debug-grid">
        <DebugBlock title="Client" value={clientDebug} open />
        <DebugBlock title="App" value={debug?.app} open />
        <DebugBlock title="Config" value={debug?.config} open />
        <DebugBlock title="Selected Environment" value={debug?.selected_environment} />
        <DebugBlock title="Health" value={debug?.health} />
        <DebugBlock title="Stats" value={stats} />
        <DebugBlock title="Artifacts" value={debug?.artifacts} />
        <DebugBlock title="Datasets" value={debug?.datasets} />
        <DebugBlock title="Routes" value={debug?.routes} />
        <DebugBlock title="Cache" value={debug?.cache} />
        <DebugBlock title="Notes" value={debug?.notes} />
        <DebugBlock title="Raw Payload" value={{ backend: debug, client: clientDebug }} />
      </section>
    </section>
  );
}

function DebugBlock({
  title,
  value,
  open = false,
}: {
  title: string;
  value: unknown;
  open?: boolean;
}) {
  return (
    <details className="debug-block" open={open}>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value ?? null, null, 2)}</pre>
    </details>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function formatNested(value: unknown): string {
  if (value === null || value === undefined) return "NA";
  if (typeof value === "object") return JSON.stringify(value);
  return formatCell(value);
}
