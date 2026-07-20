"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Play, RefreshCw, Search } from "lucide-react";
import { CsvExportButton } from "@/components/CsvExportButton";
import { DataTable, formatCell } from "@/components/DataTable";
import { RecordInspector } from "@/components/RecordInspector";
import { getDatabaseSchema, getDatabaseTable, retrieveSources, runDatabaseQuery } from "@/lib/api";
import type { DatabaseQueryResponse, DatabaseSchemaResponse, DatabaseTableResponse, RetrieveResponse } from "@/types";

type Direction = "asc" | "desc";

const defaultSql = `SELECT source_type, count(*) AS n_docs,
       round(avg(length(text))) AS avg_text_len
FROM retrieval_document
GROUP BY source_type
ORDER BY n_docs DESC`;

export default function DatabasePage() {
  const [schema, setSchema] = useState<DatabaseSchemaResponse | null>(null);
  const [selectedTable, setSelectedTable] = useState("");
  const [tableData, setTableData] = useState<DatabaseTableResponse | null>(null);
  const [limit, setLimit] = useState(100);
  const [offset, setOffset] = useState(0);
  const [orderBy, setOrderBy] = useState("");
  const [direction, setDirection] = useState<Direction>("asc");
  const [includeHeavy, setIncludeHeavy] = useState(false);
  const [sql, setSql] = useState(defaultSql);
  const [sqlLimit, setSqlLimit] = useState(100);
  const [queryResult, setQueryResult] = useState<DatabaseQueryResponse | null>(null);
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
  const [queryLoading, setQueryLoading] = useState(false);
  const [probeLoading, setProbeLoading] = useState(false);
  const [error, setError] = useState("");
  const [queryError, setQueryError] = useState("");
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

  async function submitSql(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQueryLoading(true);
    setQueryError("");
    try {
      setQueryResult(await runDatabaseQuery({ sql, limit: sqlLimit }));
    } catch (err) {
      setQueryError(err instanceof Error ? err.message : "SQL request failed");
    } finally {
      setQueryLoading(false);
    }
  }

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
        <h2>Database</h2>
      </header>

      <div className="section-toolbar">
        <span className="empty-state">
          {schema?.available ? `${tables.length} tables` : schema?.error || "Loading database schema."}
        </span>
        <button className="button secondary-button" onClick={() => void loadSchema()} type="button">
          <RefreshCw size={15} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="grid metrics-grid system-metrics">
        <Metric label="Tables" value={tables.length || "..."} />
        <Metric label="Rows in table" value={formatCell(activeTable?.row_count)} />
        <Metric label="Visible rows" value={tableData?.rows.length ?? "..."} />
        <Metric label="Columns" value={activeColumns.length || "..."} />
      </div>

      <section className="database-layout">
        <aside className="database-sidebar">
          <h3 className="section-title">Tables</h3>
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
            <h3 className="section-title">Table Browser</h3>
            <div className="database-controls">
              <label className="settings-field" htmlFor="db-limit" title="Rows per page.">
                <span>Limit</span>
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
                <span>Order by</span>
                <select
                  id="db-order"
                  className="field"
                  value={orderBy}
                  onChange={(event) => {
                    setOrderBy(event.target.value);
                    void loadTable({ nextOrderBy: event.target.value, nextOffset: 0 });
                  }}
                >
                  <option value="">none</option>
                  {activeColumns.map((column) => <option key={column} value={column}>{column}</option>)}
                </select>
              </label>
              <label className="settings-field" htmlFor="db-direction" title="Sort direction.">
                <span>Direction</span>
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
                  <option value="asc">Ascending</option>
                  <option value="desc">Descending</option>
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
                <span>Heavy columns</span>
              </label>
            </div>
            <div className="section-toolbar">
              <span className="empty-state">
                {tableData
                  ? tableData.total > 0
                    ? `${offset + 1}-${Math.min(offset + limit, tableData.total)} of ${tableData.total}`
                    : "0 of 0"
                  : "No table loaded."}
              </span>
              <div className="pager">
                <CsvExportButton
                  columns={tableData?.columns || []}
                  filename={`database_${selectedTable}_rows`}
                  rows={tableData?.rows || []}
                />
                <button className="button secondary-button" disabled={!canPrevious || loading} onClick={() => void loadTable({ nextOffset: Math.max(0, offset - limit) })} type="button">Previous</button>
                <button className="button secondary-button" disabled={!canNext || loading} onClick={() => void loadTable({ nextOffset: offset + limit })} type="button">Next</button>
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
            <h3 className="section-title">Row Inspector</h3>
            <RecordInspector row={selectedRow} emptyText="Select a table row." />
          </section>

          <section className="data-section">
            <h3 className="section-title">SQL Console</h3>
            <form onSubmit={submitSql}>
              <textarea className="textarea sql-editor" value={sql} onChange={(event) => setSql(event.target.value)} aria-label="SQL query" />
              <div className="section-toolbar">
                <label className="settings-field" htmlFor="sql-limit" title="Maximum rows returned by the API wrapper.">
                  <span>Limit</span>
                  <select id="sql-limit" className="field" value={sqlLimit} onChange={(event) => setSqlLimit(Number(event.target.value))}>
                    <option value={25}>25</option>
                    <option value={100}>100</option>
                    <option value={250}>250</option>
                    <option value={500}>500</option>
                    <option value={1000}>1000</option>
                  </select>
                </label>
                <button className="button" disabled={queryLoading || !sql.trim()}>
                  <Play size={15} aria-hidden="true" />
                  {queryLoading ? "Running" : "Run"}
                </button>
              </div>
            </form>
            {queryError ? <p className="error-text">{queryError}</p> : null}
            {queryResult ? (
              <>
                <div className="section-toolbar">
                  <p className="empty-state">{queryResult.row_count} rows in {queryResult.elapsed_ms.toFixed(1)} ms</p>
                  <CsvExportButton
                    columns={queryResult.columns}
                    filename="database_sql_result"
                    rows={queryResult.rows}
                  />
                </div>
                <DataTable columns={queryResult.columns} rows={queryResult.rows} rowKeyColumn={queryResult.columns[0] || "id"} />
              </>
            ) : null}
          </section>

          <section className="data-section">
            <h3 className="section-title">Similarity Probe</h3>
            <form className="probe-form" onSubmit={submitProbe}>
              <label className="settings-field probe-query" htmlFor="db-probe-query" title="Hybrid retrieval query executed through the same retrieve API as chat.">
                <span>Query</span>
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
                <span>Source</span>
                <select id="db-probe-source" className="field" onChange={(event) => setProbeSourceType(event.target.value)} value={probeSourceType}>
                  <option value="">All</option>
                  <option value="ctd">CTD</option>
                  <option value="metagenome">Metagenome</option>
                  <option value="remote_sensing">SST</option>
                </select>
              </label>
              <label className="settings-field" htmlFor="db-probe-bay" title="Restrict probe retrieval by bay metadata.">
                <span>Bay</span>
                <select id="db-probe-bay" className="field" onChange={(event) => setProbeBay(event.target.value)} value={probeBay}>
                  <option value="">All</option>
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
                {probeLoading ? "Probing" : "Probe"}
              </button>
            </form>
            {probeError ? <p className="error-text">{probeError}</p> : null}
            {probeResult ? (
              <>
                <div className="section-toolbar">
                  <p className="empty-state">{probeRows.length} fused results for `{probeResult.query}`</p>
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
            <h3 className="section-title">Schema</h3>
            {activeTable ? <SchemaTable table={activeTable} /> : <p className="empty-state">Select a table.</p>}
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
