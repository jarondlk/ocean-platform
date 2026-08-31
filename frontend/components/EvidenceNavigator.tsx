"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileSearch, X } from "lucide-react";
import { DataTable, formatCell } from "@/components/DataTable";
import { SampleDetail } from "@/components/SampleDetail";
import { getProvenanceTrace, getSampleDetail } from "@/lib/api";
import { evidenceDeepLinks, type CitationTarget } from "@/lib/citation-navigation";
import type { ProvenanceTraceResponse, SampleDetailResponse } from "@/types";
import { useAppPreferences } from "@/lib/preferences";

export function EvidenceNavigator({
  target,
  onClose,
}: {
  target: CitationTarget | null;
  onClose: () => void;
}) {
  const { ui } = useAppPreferences();
  const closeButton = useRef<HTMLButtonElement>(null);
  const [trace, setTrace] = useState<ProvenanceTraceResponse | null>(null);
  const [sample, setSample] = useState<SampleDetailResponse | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [traceError, setTraceError] = useState("");
  const [sampleError, setSampleError] = useState("");

  useEffect(() => {
    if (!target) return;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    closeButton.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus && document.contains(previousFocus)) previousFocus.focus();
    };
  }, [onClose, target]);

  useEffect(() => {
    let active = true;
    setTrace(null);
    setSample(null);
    setTraceError("");
    setSampleError("");
    setTraceLoading(false);
    setSampleLoading(false);
    if (!target?.valid || target.kind !== "source" || !target.source) {
      return () => {
        active = false;
      };
    }

    setTraceLoading(true);
    getProvenanceTrace(target.source.doc_id)
      .then((payload) => {
        if (active) setTrace(payload);
      })
      .catch((error: Error) => {
        if (active) setTraceError(error.message);
      })
      .finally(() => {
        if (active) setTraceLoading(false);
      });

    if (target.source.sample_id) {
      setSampleLoading(true);
      getSampleDetail(target.source.sample_id)
        .then((payload) => {
          if (active) setSample(payload);
        })
        .catch((error: Error) => {
          if (active) setSampleError(error.message);
        })
        .finally(() => {
          if (active) setSampleLoading(false);
        });
    }

    return () => {
      active = false;
    };
  }, [target]);

  const tracePayload = asRecord(trace?.trace);
  const traceDocument = asRecord(tracePayload.document);
  const traceEmbedding = asRecord(tracePayload.embedding);
  const tracePathRows = useMemo(
    () => asRecords(tracePayload.trace_path).map((row, index) => ({ step: index + 1, ...row })),
    [tracePayload.trace_path],
  );
  const deepLinks = useMemo(() => target ? evidenceDeepLinks(target) : [], [target]);

  if (!target) return null;

  return (
    <aside
      aria-label={`${ui("Evidence")}: ${target.citationId}`}
      className="evidence-navigator"
      role="region"
    >
      <header className="evidence-navigator-header">
        <h3>{target.title}</h3>
        <button
          aria-label={ui("Close evidence")}
          className="button secondary-button icon-button"
          onClick={onClose}
          ref={closeButton}
          type="button"
        >
          <X aria-hidden="true" size={16} />
        </button>
      </header>

      <div className="evidence-navigator-body">
        <div className="citation-target-badges">
          {target.contextType ? <span>{target.contextType}</span> : null}
          {target.sourceType ? <span>{target.sourceType}</span> : null}
          {target.kind === "source" ? <span>{target.evidenceRole}</span> : null}
        </div>

        {deepLinks.length ? (
          <nav aria-label={ui("Full evidence pages")} className="navigator-actions">
            {deepLinks.map((link) => (
              <a
                className="button secondary-button"
                href={link.href}
                key={`${link.kind}-${link.href}`}
                rel="noopener noreferrer"
                target="_blank"
              >
                <ExternalLink aria-hidden="true" size={14} />
                {ui(link.label)}
              </a>
            ))}
          </nav>
        ) : null}

        {!target.valid ? (
          <section className="navigator-section navigator-warning">
            <h4>{ui("Unresolved citation")}</h4>
            <p>{target.detail}</p>
          </section>
        ) : null}

        {target.source ? (
          <>
            <section className="navigator-section">
              <h4>{ui("Source")}</h4>
              <MetadataGrid
                rows={[
                  ["Document", target.source.doc_id],
                  ["Role", target.evidenceRole],
                  ["Source", target.source.source_type],
                  ["Sample", target.source.sample_id],
                  ["Event", target.source.event_id],
                  ["Time", target.source.time],
                  ["Bay", target.source.bay],
                  ["Station", target.source.station],
                  ["Link", target.source.link_type],
                  ["Linked from", target.source.linked_from_doc_id || target.source.linked_from_event_id],
                ]}
              />
              <p className="navigator-evidence-text">{target.source.text}</p>
            </section>

            <section className="navigator-section">
              <h4>
                <FileSearch aria-hidden="true" size={15} />
                {ui("Provenance")}
              </h4>
              {traceLoading ? <p className="empty-state">{ui("Loading provenance trace.")}</p> : null}
              {traceError ? <p className="error-text">{traceError}</p> : null}
              {trace ? (
                <>
                  <MetadataGrid
                    rows={[
                      ["Found", trace.found],
                      ["Source", traceDocument.source_type],
                      ["Sample", traceDocument.sample_id],
                      ["Embedding", traceEmbedding.embedding_status],
                      ["Model", traceEmbedding.embedding_model],
                    ]}
                  />
                  <DataTable
                    columns={["step", "level", "key", "keys"]}
                    emptyText="No trace path was recorded."
                    rowKeyColumn="step"
                    rows={tracePathRows}
                  />
                </>
              ) : null}
            </section>

            <section className="navigator-section">
              <h4>{ui(target.source.sample_id ? "Sample" : "Source record")}</h4>
              {sampleLoading ? <p className="empty-state">{ui("Loading sample.")}</p> : null}
              {sampleError ? <p className="error-text">{sampleError}</p> : null}
              {sample ? <SampleDetail detail={sample} /> : null}
              {!target.source.sample_id && !sampleLoading ? (
                <MetadataGrid
                  rows={[
                    ["Document", target.source.doc_id],
                    ["Source", target.source.source_type],
                    ["Time", target.source.time],
                    ["Bay", target.source.bay],
                  ]}
                />
              ) : null}
            </section>
          </>
        ) : null}

        {target.context ? (
          <section className="navigator-section">
            <h4>{ui("Context")}</h4>
            <MetadataGrid
              rows={[
                ["Context", target.context.context_type],
                ["Analysis", target.context.analysis_type],
                ["Document", target.context.doc_id],
              ]}
            />
            <p className="navigator-evidence-text">{target.context.text}</p>
          </section>
        ) : null}
      </div>
    </aside>
  );
}

function MetadataGrid({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <dl className="navigator-metadata">
      {rows
        .filter(([, value]) => value !== null && value !== undefined && value !== "")
        .map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{formatCell(value)}</dd>
          </div>
        ))}
    </dl>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object" && !Array.isArray(row))
    : [];
}
