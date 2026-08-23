"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { RefreshCw, Search } from "lucide-react";
import { CsvExportButton } from "@/components/CsvExportButton";
import { DataTable, formatCell } from "@/components/DataTable";
import { RecordInspector } from "@/components/RecordInspector";
import { getDatabaseSchema, getDatabaseTable, retrieveSources } from "@/lib/api";
import { useAppPreferences } from "@/lib/preferences";
import type { DatabaseSchemaResponse, DatabaseTableResponse, RetrieveResponse } from "@/types";

type Direction = "asc" | "desc";

export default function DatabasePage() {
  const { ui } = useAppPreferences();
  const [schema, setSchema] = useState<DatabaseSchemaResponse | null>(null);
  const [selectedTable, setSelectedTable] = useState("");
  const [tableData, setTableData] = useState<DatabaseTableResponse | null>(null);
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [orderBy, setOrderBy] = useState("");
  const [direction, setDirection] = useState<Direction>("asc");
  const [includeHeavy, setIncludeHeavy] = useState(false);
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null);
  const [selectedRowKey, setSelectedRowKey] = useState("");
  const [probeQuery, setProbeQuery] = useState("");
  const [probeK, setProbeK] = useState(10);
  const [probeSourceType, setProbeSourceType] = useState("");
  const [probeBay, setProbeBay] = useState("");
  const [probeVectorWeight, setProbeVectorWeight] = useState(0.6);
  const [probeFtsWeight, setProbeFtsWeight] = useState(0.4);
  const [probeRrfK, setProbeRrfK] = useState(60);
  const [probeResult, setProbeResult] = useState<RetrieveResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [probeLoading, setProbeLoading] = useState(false);
  const [error, setError] = useState("");
  const [probeError, setProbeError] = useState("");

  const tables = schema?.tables || [];
  const activeTable = useMemo(() => {
    return tables.find((table) => table.name === selectedTable) || null;
  }, [selectedTable, tables]);
  const activeColumns = useMemo(() => {
    const columns = activeTable?.columns;
    return Array.isArray(columns)
      ? columns.map((column) => asRecord(column).name).filter((name): name is string => typeof name === "string")
      : [];
  }, [activeTable]);

  async function loadSchema() {
    setLoading(true);
    setError("");
    try {
      const payload = await getDatabaseSchema();
      setSchema(payload);
      const currentStillExists = payload.tables.some((table) => table.name === selectedTable);
      const preferredTable =
        payload.tables.find((table) => table.name === "retrieval_document") ||
        [...payload.tables].sort((a, b) => Number(b.row_count || 0) - Number(a.row_count || 0))[0];
      const nextTable = currentStillExists ? selectedTable : String(preferredTable?.name || "");
      if (nextTable) {
        setSelectedTable(nextTable);
        await loadTable({ table: nextTable, nextOffset: 0 });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Database schema request failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadTable({
    table = selectedTable,
    nextOffset = offset,
    nextLimit = limit,
    nextOrderBy = orderBy,
    nextDirection = direction,
    nextIncludeHeavy = includeHeavy,
  }: {
    table?: string;
    nextOffset?: number;
    nextLimit?: number;
    nextOrderBy?: string;
    nextDirection?: Direction;
    nextIncludeHeavy?: boolean;
  } = {}) {
    if (!table) return;
    setLoading(true);
    setError("");
    try {
      const payload = await getDatabaseTable({
        table,
        limit: nextLimit,
        offset: nextOffset,
        order_by: nextOrderBy || undefined,
        direction: nextDirection,
        include_heavy: nextIncludeHeavy,
      });
      setTableData(payload);
      setOffset(nextOffset);
      setSelectedRow(null);
      setSelectedRowKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Database table request failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSchema();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submitProbe(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!probeQuery.trim()) return;
    setProbeLoading(true);
    setProbeError("");
    try {
      setProbeResult(await retrieveSources({
        query: probeQuery,
        k: probeK,
        source_type: probeSourceType || undefined,
        bay: probeBay || undefined,
        vector_weight: probeVectorWeight,
        fts_weight: probeFtsWeight,
        rrf_k: probeRrfK,
      }));
    } catch (err) {
      setProbeError(err instanceof Error ? err.message : "Similarity probe failed");
    } finally {
      setProbeLoading(false);
    }
  }

  const canPrevious = offset > 0;
  const canNext = Boolean(tableData && offset + limit < tableData.total);
  const probeRows = (probeResult?.sources || []).map((source, index) => ({
    rank: index + 1,
    doc_id: source.doc_id,
    source_type: source.source_type,
    score: source.score,
    vector_rank: source.rank_sources?.vector,
    fts_rank: source.rank_sources?.fts,
    bay: source.bay,
    time: source.time,
    title: source.title,
  }));

  return (
    <section>
      <header className="page-header">
        <h2>{ui("Database")}</h2>
      </header>

      <div className="section-toolbar">
        <span className="empty-state">
          {schema?.available ? `${tables.length} ${ui("tables")}` : schema?.error || ui("Loading database schema.")}
        </span>
        <button className="button secondary-button" onClick={() => void loadSchema()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          {ui("Refresh")}
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label={ui("Tables")} value={tables.length || "..."} />
        <Metric label={ui("Rows in table")} value={formatCell(activeTable?.row_count)} />
        <Metric label={ui("Visible rows")} value={tableData?.rows.length ?? "..."} />
        <Metric label={ui("Columns")} value={activeColumns.length || "..."} />
      </div>

      <section className="database-layout">
        <aside className="database-sidebar">
          <h3 className="section-title">{ui("Tables")}</h3>
          <div className="table-list">
            {tables.map((table) => {
              const name = String(table.name);
              return (
                <button
                  className={selectedTable === name ? "active" : ""}
                  key={name}
                  onClick={() => {
                    setSelectedTable(name);
                    setOrderBy("");
                    setOffset(0);
                    void loadTable({ table: name, nextOffset: 0, nextOrderBy: "" });
                  }}
                  type="button"
                >
                  <span>{name}</span>
                  <strong>{formatCell(table.row_count)}</strong>
                </button>
              );
            })}
          </div>
        </aside>

        <main className="database-main">
          <section className="data-section">
            <h3 className="section-title">{ui("Table Browser")}</h3>
            <div className="database-controls">
              <label className="settings-field" htmlFor="db-limit" title="Rows per page.">
                <span>{ui("Limit")}</span>
                <select
                  id="db-limit"
                  className="field"
                  value={limit}
                  onChange={(event) => {
                    const next = Number(event.target.value);
                    setLimit(next);
                    void loadTable({ nextLimit: next, nextOffset: 0 });
                  }}
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={250}>250</option>
                  <option value={500}>500</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="db-order" title="Validated order-by column.">
                <span>{ui("Order by")}</span>
                <select
                  id="db-order"
                  className="field"
                  value={orderBy}
                  onChange={(event) => {
                    setOrderBy(event.target.value);
                    void loadTable({ nextOrderBy: event.target.value, nextOffset: 0 });
                  }}
                >
                  <option value="">{ui("none")}</option>
                  {activeColumns.map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
              </label>
              <label className="settings-field" htmlFor="db-direction" title="Sort direction.">
                <span>{ui("Direction")}</span>
                <select
                  id="db-direction"
                  className="field"
                  value={direction}
                  onChange={(event) => {
                    const next = event.target.value as Direction;
                    setDirection(next);
                    void loadTable({ nextDirection: next, nextOffset: 0 });
                  }}
                >
                  <option value="asc">{ui("Ascending")}</option>
                  <option value="desc">{ui("Descending")}</option>
                </select>
              </label>
              <label className="checkbox-row" title="Include heavy vector/search columns such as embedding and text_tsv.">
                <input
                  checked={includeHeavy}
                  onChange={(event) => {
                    setIncludeHeavy(event.target.checked);
                    void loadTable({ nextIncludeHeavy: event.target.checked, nextOffset: 0 });
                  }}
                  type="checkbox"
                />
                <span>{ui("Heavy columns")}</span>
              </label>
            </div>
            <div className="section-toolbar">
              <span className="empty-state">
                {tableData
                  ? tableData.total > 0
                    ? `${offset + 1}-${Math.min(offset + limit, tableData.total)} of ${tableData.total}`
                    : `0 ${ui("of")} 0`
                  : ui("No table loaded.")}
              </span>
              <div className="pager">
                <CsvExportButton
                  columns={tableData?.columns || []}
                  filename={`database_${selectedTable}_rows`}
                  rows={tableData?.rows || []}
                />
                <button className="button secondary-button" disabled={!canPrevious || loading} onClick={() => void loadTable({ nextOffset: Math.max(0, offset - limit) })} type="button">{ui("Previous")}</button>
                <button className="button secondary-button" disabled={!canNext || loading} onClick={() => void loadTable({ nextOffset: offset + limit })} type="button">{ui("Next")}</button>
              </div>
            </div>
            <DataTable
              columns={tableData?.columns || []}
              rows={tableData?.rows || []}
              rowKeyColumn={tableData?.columns[0] || "id"}
              selectedKey={selectedRowKey}
              onRowSelect={(row, _index, key) => {
                setSelectedRow(row);
                setSelectedRowKey(key);
              }}
            />
          </section>

          <section className="data-section">
            <h3 className="section-title">{ui("Row Inspector")}</h3>
            <RecordInspector row={selectedRow} emptyText="Select a table row." />
          </section>

          <section className="data-section">
            <h3 className="section-title">{ui("Similarity Probe")}</h3>
            <form className="probe-form" onSubmit={submitProbe}>
              <label className="settings-field probe-query" htmlFor="db-probe-query" title="Hybrid retrieval query executed through the same retrieve API as chat.">
                <span>{ui("Query")}</span>
                <input
                  id="db-probe-query"
                  className="field"
                  onChange={(event) => setProbeQuery(event.target.value)}
                  placeholder="chlorophyll bloom summer"
                  value={probeQuery}
                />
              </label>
              <label className="settings-field" htmlFor="db-probe-k" title="Number of fused retrieval results to return.">
                <span>K</span>
                <select id="db-probe-k" className="field" onChange={(event) => setProbeK(Number(event.target.value))} value={probeK}>
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={15}>15</option>
                  <option value={20}>20</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="db-probe-source" title="Restrict probe retrieval by source type.">
                <span>{ui("Source")}</span>
                <select id="db-probe-source" className="field" onChange={(event) => setProbeSourceType(event.target.value)} value={probeSourceType}>
                  <option value="">{ui("All")}</option>
                  <option value="ctd">CTD</option>
                  <option value="metagenome">Metagenome</option>
                  <option value="remote_sensing">SST</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="db-probe-bay" title="Restrict probe retrieval by bay metadata.">
                <span>{ui("Bay")}</span>
                <select id="db-probe-bay" className="field" onChange={(event) => setProbeBay(event.target.value)} value={probeBay}>
                  <option value="">{ui("All")}</option>
                  <option value="O">O</option>
                  <option value="I">I</option>
                  <option value="M">M</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="db-probe-vector" title="RRF weight for vector ranking.">
                <span>Vector</span>
                <input id="db-probe-vector" className="field" max={1} min={0} onChange={(event) => setProbeVectorWeight(Number(event.target.value))} step={0.05} type="number" value={probeVectorWeight} />
              </label>
              <label className="settings-field" htmlFor="db-probe-fts" title="RRF weight for full-text ranking.">
                <span>FTS</span>
                <input id="db-probe-fts" className="field" max={1} min={0} onChange={(event) => setProbeFtsWeight(Number(event.target.value))} step={0.05} type="number" value={probeFtsWeight} />
              </label>
              <label className="settings-field" htmlFor="db-probe-rrf" title="RRF smoothing constant used when fusing vector and FTS ranks.">
                <span>RRF-k</span>
                <input id="db-probe-rrf" className="field" max={200} min={1} onChange={(event) => setProbeRrfK(Number(event.target.value))} step={1} type="number" value={probeRrfK} />
              </label>
              <button className="button" disabled={probeLoading || !probeQuery.trim()}>
                <Search size={15} aria-hidden="true" />
                {probeLoading ? ui("Probing") : ui("Probe")}
              </button>
            </form>
            {probeError ? <p className="error-text">{probeError}</p> : null}
            {probeResult ? (
              <>
                <div className="section-toolbar">
                  <p className="empty-state">{probeRows.length} {ui("fused results for")} `{probeResult.query}`</p>
                  <CsvExportButton
                    columns={["rank", "doc_id", "source_type", "score", "vector_rank", "fts_rank", "bay", "time", "title"]}
                    filename="database_similarity_probe"
                    rows={probeRows}
                  />
                </div>
                <DataTable
                  columns={["rank", "doc_id", "source_type", "score", "vector_rank", "fts_rank", "bay", "time", "title"]}
                  rows={probeRows}
                  rowKeyColumn="doc_id"
                />
              </>
            ) : null}
          </section>

          <section className="data-section">
            <h3 className="section-title">{ui("Schema")}</h3>
            {activeTable ? <SchemaTable table={activeTable} /> : <p className="empty-state">{ui("Select a table.")}</p>}
          </section>
        </main>
      </section>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <article className="card">
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </article>
  );
}

function SchemaTable({ table }: { table: Record<string, unknown> }) {
  const columns = Array.isArray(table.columns)
    ? table.columns.map((column) => asRecord(column))
    : [];
  const rows = columns.map((column) => ({
    column: column.name,
    type: column.type,
    nullable: column.nullable,
    default: column.default,
  }));
  return <DataTable columns={["column", "type", "nullable", "default"]} rows={rows} rowKeyColumn="column" />;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
