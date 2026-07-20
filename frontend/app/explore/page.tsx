"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  getExploreCatalog,
  getExploreSummary,
  getExploreTable,
  getExploreTimeseries,
  getSampleDetail,
} from "@/lib/api";
import type {
  DatasetCatalogItem,
  ExploreSummaryResponse,
  ExploreTableResponse,
  SampleDetailResponse,
  TimeSeriesResponse,
} from "@/types";
import { CsvExportButton } from "@/components/CsvExportButton";
import { DataTable } from "@/components/DataTable";
import { EvidenceWorkbench } from "@/components/EvidenceWorkbench";
import { SampleDetail } from "@/components/SampleDetail";
import { SimpleTimeSeries } from "@/components/SimpleTimeSeries";

type ExploreView = "tables" | "evidence";

type ExploreFilters = {
  bay: string;
  station: string;
  source: string;
  time_from: string;
  time_to: string;
  search: string;
};

const defaultFilters: ExploreFilters = {
  bay: "",
  station: "",
  source: "",
  time_from: "",
  time_to: "",
  search: "",
};

export default function ExplorePage() {
  return (
    <Suspense fallback={<ExplorePageFallback />}>
      <ExplorePageContent />
    </Suspense>
  );
}

function ExplorePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedView = searchParams.get("view");
  const initialView = isExploreView(requestedView) ? requestedView : "tables";
  const [view, setView] = useState<ExploreView>(initialView);
  const [catalog, setCatalog] = useState<DatasetCatalogItem[]>([]);
  const [dataset, setDataset] = useState("ctd_summary");
  const [filters, setFilters] = useState<ExploreFilters>(defaultFilters);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [sortColumn, setSortColumn] = useState("");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
  const [seriesLimit, setSeriesLimit] = useState(500);
  const [xColumn, setXColumn] = useState("");
  const [yColumn, setYColumn] = useState("");
  const [table, setTable] = useState<ExploreTableResponse | null>(null);
  const [summary, setSummary] = useState<ExploreSummaryResponse | null>(null);
  const [series, setSeries] = useState<TimeSeriesResponse | null>(null);
  const [detail, setDetail] = useState<SampleDetailResponse | null>(null);
  const [selectedSample, setSelectedSample] = useState("");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const activeDataset = useMemo(
    () => catalog.find((item) => item.id === dataset),
    [catalog, dataset],
  );

  useEffect(() => {
    setView(isExploreView(requestedView) ? requestedView : "tables");
  }, [requestedView]);

  useEffect(() => {
    if (view !== "tables" || catalog.length) return;
    getExploreCatalog()
      .then((items) => {
        setCatalog(items);
        const initial = items.find((item) => item.id === "ctd_summary") || items[0];
        if (initial) {
          const initialSort = initial.default_x || initial.default_columns[0] || initial.columns[0] || "";
          setDataset(initial.id);
          setSortColumn(initialSort);
          setXColumn(initial.default_x || initial.date_columns[0] || "");
          setYColumn(initial.default_y || initial.numeric_columns[0] || "");
          void loadData({
            datasetId: initial.id,
            nextOffset: 0,
            nextFilters: defaultFilters,
            nextSort: initialSort,
            nextX: initial.default_x || initial.date_columns[0] || "",
            nextY: initial.default_y || initial.numeric_columns[0] || "",
            nextLimit: limit,
          });
        }
      })
      .catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, catalog.length]);

  async function loadData({
    datasetId = dataset,
    nextOffset = offset,
    nextFilters = filters,
    nextX = xColumn,
    nextY = yColumn,
    nextLimit = limit,
    nextSort = sortColumn,
    nextDirection = sortDirection,
    nextSeriesLimit = seriesLimit,
  }: {
    datasetId?: string;
    nextOffset?: number;
    nextFilters?: ExploreFilters;
    nextX?: string;
    nextY?: string;
    nextLimit?: number;
    nextSort?: string;
    nextDirection?: "asc" | "desc";
    nextSeriesLimit?: number;
  } = {}) {
    setLoading(true);
    setError("");
    try {
      const params = {
        dataset: datasetId,
        bay: nextFilters.bay || undefined,
        station: nextFilters.station || undefined,
        source: nextFilters.source || undefined,
        time_from: nextFilters.time_from || undefined,
        time_to: nextFilters.time_to || undefined,
        search: nextFilters.search || undefined,
      };
      const [tableData, summaryData] = await Promise.all([
        getExploreTable({
          ...params,
          limit: nextLimit,
          offset: nextOffset,
          sort: nextSort || undefined,
          direction: nextDirection,
        }),
        getExploreSummary(params),
      ]);

      setTable(tableData);
      setSummary(summaryData);
      setOffset(nextOffset);

      const item = catalog.find((entry) => entry.id === datasetId);
      const chosenX = nextX || item?.default_x || summaryData.date_columns[0] || "";
      const chosenY = nextY || item?.default_y || summaryData.numeric_columns[0] || "";
      const chosenSort = nextSort || item?.default_x || item?.default_columns[0] || tableData.columns[0] || "";
      setXColumn(chosenX);
      setYColumn(chosenY);
      setSortColumn(chosenSort);
      setSortDirection(nextDirection);

      if (chosenX && chosenY) {
        try {
          const seriesData = await getExploreTimeseries({
            ...params,
            x_column: chosenX,
            y_column: chosenY,
            limit: nextSeriesLimit,
          });
          setSeries(seriesData);
        } catch {
          setSeries(null);
        }
      } else {
        setSeries(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(key: keyof ExploreFilters, value: string) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadData({ nextOffset: 0 });
  }

  function changeView(nextView: ExploreView) {
    setView(nextView);
    router.replace(nextView === "tables" ? "/explore" : `/explore?view=${nextView}`, { scroll: false });
  }

  function changeDataset(value: string) {
    const item = catalog.find((entry) => entry.id === value);
    const nextFilters = defaultFilters;
    const nextX = item?.default_x || item?.date_columns[0] || "";
    const nextY = item?.default_y || item?.numeric_columns[0] || "";
    const nextSort = item?.default_x || item?.default_columns[0] || item?.columns[0] || "";
    setDataset(value);
    setFilters(nextFilters);
    setDetail(null);
    setSelectedSample("");
    setSortColumn(nextSort);
    setSortDirection("asc");
    setXColumn(nextX);
    setYColumn(nextY);
    void loadData({
      datasetId: value,
      nextOffset: 0,
      nextFilters,
      nextX,
      nextY,
      nextSort,
      nextDirection: "asc",
    });
  }

  async function selectRow(row: Record<string, unknown>) {
    const sampleId = row.sample_id;
    if (typeof sampleId !== "string" || !sampleId) return;
    setSelectedSample(sampleId);
    setDetailLoading(true);
    try {
      const sample = await getSampleDetail(sampleId);
      setDetail(sample);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sample detail failed");
    } finally {
      setDetailLoading(false);
    }
  }

  const canPrevious = Boolean(table && offset > 0);
  const canNext = Boolean(table && offset + limit < table.filtered);

  return (
    <section>
      <header className="page-header">
        <h2>Explore</h2>
      </header>

      <div className="data-tabs" role="tablist" aria-label="Explore views">
        <button className={view === "tables" ? "active" : ""} onClick={() => changeView("tables")} type="button">
          Tables
        </button>
        <button className={view === "evidence" ? "active" : ""} onClick={() => changeView("evidence")} type="button">
          Evidence
        </button>
      </div>

      {view === "tables" ? (
        <>
      <form className="explore-controls" onSubmit={submit}>
        <label>
          Dataset
          <select className="field" value={dataset} onChange={(event) => changeDataset(event.target.value)}>
            {catalog.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input
            className="field"
            value={filters.search}
            onChange={(event) => updateFilter("search", event.target.value)}
            placeholder="Text filter"
          />
        </label>
        <label>
          Bay
          <select
            className="field"
            value={filters.bay}
            onChange={(event) => updateFilter("bay", event.target.value)}
            disabled={!activeDataset?.filters.bay}
          >
            <option value="">All</option>
            <option value="O">O</option>
            <option value="I">I</option>
            <option value="M">M</option>
          </select>
        </label>
        <label>
          Station
          <input
            className="field"
            value={filters.station}
            onChange={(event) => updateFilter("station", event.target.value)}
            disabled={!activeDataset?.filters.station}
            placeholder="s1"
          />
        </label>
        <label>
          Source
          <input
            className="field"
            value={filters.source}
            onChange={(event) => updateFilter("source", event.target.value)}
            disabled={!activeDataset?.filters.source}
            placeholder="kraken"
          />
        </label>
        <label>
          From
          <input
            className="field"
            type="date"
            value={filters.time_from}
            onChange={(event) => updateFilter("time_from", event.target.value)}
            disabled={!activeDataset?.date_columns.length}
          />
        </label>
        <label>
          To
          <input
            className="field"
            type="date"
            value={filters.time_to}
            onChange={(event) => updateFilter("time_to", event.target.value)}
            disabled={!activeDataset?.date_columns.length}
          />
        </label>
        <label>
          Limit
          <select
            className="field"
            value={limit}
            onChange={(event) => {
              const nextLimit = Number(event.target.value);
              setLimit(nextLimit);
              void loadData({ nextOffset: 0, nextLimit });
            }}
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </label>
        <label title="Column used to sort the displayed table page.">
          Sort by
          <select
            className="field"
            value={sortColumn}
            onChange={(event) => {
              setSortColumn(event.target.value);
              void loadData({ nextOffset: 0, nextSort: event.target.value });
            }}
          >
            {(activeDataset?.columns || table?.columns || []).map((column) => (
              <option key={column} value={column}>
                {column}
              </option>
            ))}
          </select>
        </label>
        <label title="Direction for table sorting.">
          Direction
          <select
            className="field"
            value={sortDirection}
            onChange={(event) => {
              const nextDirection = event.target.value as "asc" | "desc";
              setSortDirection(nextDirection);
              void loadData({ nextOffset: 0, nextDirection });
            }}
          >
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </label>
        <button className="button" disabled={loading}>
          {loading ? "Loading" : "Apply"}
        </button>
      </form>

      {error ? <p className="error-text">{error}</p> : null}

      <div className="explore-layout">
        <main className="explore-main">
          <section className="explore-section">
            <h3 className="section-title">Summary</h3>
            <div className="summary-strip">
              <SummaryCell label="Rows" value={summary?.filtered_rows ?? "..."} />
              <SummaryCell label="Total" value={summary?.total_rows ?? "..."} />
              <SummaryCell label="Columns" value={summary?.columns.length ?? "..."} />
              <SummaryCell label="Numeric" value={summary?.numeric_columns.length ?? "..."} />
            </div>
          </section>

          <section className="explore-section">
            <div className="section-toolbar">
              <h3 className="section-title">Time series</h3>
              <div className="inline-controls">
                <label title="Maximum points requested for the chart.">
                  Points
                  <select
                    className="field"
                    value={seriesLimit}
                    onChange={(event) => {
                      const nextSeriesLimit = Number(event.target.value);
                      setSeriesLimit(nextSeriesLimit);
                      void loadData({ nextSeriesLimit });
                    }}
                  >
                    <option value={100}>100</option>
                    <option value={250}>250</option>
                    <option value={500}>500</option>
                    <option value={1000}>1000</option>
                    <option value={2000}>2000</option>
                  </select>
                </label>
                <select
                  className="field"
                  value={xColumn}
                  onChange={(event) => {
                    setXColumn(event.target.value);
                    void loadData({ nextX: event.target.value });
                  }}
                  disabled={!summary?.date_columns.length}
                >
                  {(summary?.date_columns || []).map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
                <select
                  className="field"
                  value={yColumn}
                  onChange={(event) => {
                    setYColumn(event.target.value);
                    void loadData({ nextY: event.target.value });
                  }}
                  disabled={!summary?.numeric_columns.length}
                >
                  {(summary?.numeric_columns || []).map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {series ? (
              <SimpleTimeSeries points={series.points} xColumn={series.x_column} yColumn={series.y_column} />
            ) : (
              <p className="empty-state">No time-series view for this dataset.</p>
            )}
          </section>

          <section className="explore-section">
            <div className="section-toolbar">
              <h3 className="section-title">
                Table {table ? `(${table.filtered.toLocaleString()} rows)` : ""}
              </h3>
              <div className="pager">
                <CsvExportButton
                  columns={table?.columns || []}
                  filename={`explore_${dataset}_rows`}
                  rows={table?.rows || []}
                />
                <button
                  className="button secondary-button"
                  disabled={!canPrevious || loading}
                  onClick={() => void loadData({ nextOffset: Math.max(0, offset - limit) })}
                  type="button"
                >
                  Previous
                </button>
                <span>
                  {table ? `${offset + 1}-${Math.min(offset + limit, table.filtered)}` : "0-0"}
                </span>
                <button
                  className="button secondary-button"
                  disabled={!canNext || loading}
                  onClick={() => void loadData({ nextOffset: offset + limit })}
                  type="button"
                >
                  Next
                </button>
              </div>
            </div>
            <DataTable
              columns={table?.columns || []}
              rows={table?.rows || []}
              onRowSelect={selectRow}
              selectedKey={selectedSample}
            />
          </section>
        </main>

        <aside className="explore-side">
          <h3 className="section-title">Sample detail</h3>
          {detailLoading ? <p className="empty-state">Loading sample.</p> : <SampleDetail detail={detail} />}
        </aside>
      </div>
        </>
      ) : (
        <EvidenceWorkbench />
      )}
    </section>
  );
}

function ExplorePageFallback() {
  return (
    <section>
      <header className="page-header">
        <h2>Explore</h2>
      </header>
      <p className="empty-state">Loading corpus workspace.</p>
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function isExploreView(value: string | null): value is ExploreView {
  return value === "tables" || value === "evidence";
}
