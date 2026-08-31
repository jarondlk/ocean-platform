"use client";

import type { SourceDocument } from "@/types";
import { useAppPreferences } from "@/lib/preferences";

const sourceLabels: Record<string, string> = {
  ctd: "CTD",
  metagenome: "Metagenome",
  remote_sensing: "SST",
};

const roleLabels: Record<string, string> = {
  primary: "Primary",
  linked: "Linked",
};

export function SourceTable({
  sources,
  onSourceSelect,
  onDocumentSelect,
}: {
  sources: SourceDocument[];
  onSourceSelect?: (source: SourceDocument) => void;
  onDocumentSelect?: (docId: string) => void;
}) {
  const { ui } = useAppPreferences();
  if (!sources.length) {
    return <p className="empty-state">{ui("No matching evidence records.")}</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{ui("Document")}</th>
            <th>{ui("Role")}</th>
            <th>{ui("Source")}</th>
            <th>{ui("Time")}</th>
            <th>{ui("Bay")}</th>
            <th>{ui("Link")}</th>
            <th>{ui("Score")}</th>
            <th>{ui("Vector")}</th>
            <th>{ui("FTS")}</th>
            <th>{ui("Text")}</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={`${source.retrieval_role || "primary"}:${source.doc_id}`}>
              <td>
                {onSourceSelect ? (
                  <button
                    className="document-link-button"
                    onClick={() => onSourceSelect(source)}
                    type="button"
                  >
                    {source.doc_id}
                  </button>
                ) : (
                  <strong>{source.doc_id}</strong>
                )}
                <span>{source.title}</span>
              </td>
              <td>{ui(roleLabels[source.retrieval_role || "primary"] || source.retrieval_role || "Primary")}</td>
              <td>{sourceLabels[source.source_type] || source.source_type}</td>
              <td>{source.time || "NA"}</td>
              <td>{source.bay || "regional"}</td>
              <td>
                {source.retrieval_role === "linked" ? (
                  <>
                    <strong>{source.link_type || "cross_source"}</strong>
                    {source.linked_from_doc_id && onDocumentSelect ? (
                      <button
                        className="document-link-button secondary-document-link"
                        onClick={() => onDocumentSelect(source.linked_from_doc_id || "")}
                        type="button"
                      >
                        {source.linked_from_doc_id}
                      </button>
                    ) : (
                      <span>{source.linked_from_doc_id || source.linked_from_event_id || "primary evidence"}</span>
                    )}
                  </>
                ) : (
                  "NA"
                )}
              </td>
              <td>{source.score !== null && source.score !== undefined ? source.score.toFixed(4) : "NA"}</td>
              <td>{source.rank_sources?.vector ?? "NA"}</td>
              <td>{source.rank_sources?.fts ?? "NA"}</td>
              <td>{source.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
