import type { SourceDocument } from "@/types";

const sourceLabels: Record<string, string> = {
  ctd: "CTD",
  metagenome: "Metagenome",
  remote_sensing: "SST",
};

const roleLabels: Record<string, string> = {
  primary: "Primary",
  linked: "Linked",
};

export function SourceTable({ sources }: { sources: SourceDocument[] }) {
  if (!sources.length) {
    return <p className="empty-state">No matching evidence records.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Role</th>
            <th>Source</th>
            <th>Time</th>
            <th>Bay</th>
            <th>Link</th>
            <th>Score</th>
            <th>Vector</th>
            <th>FTS</th>
            <th>Text</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={`${source.retrieval_role || "primary"}:${source.doc_id}`}>
              <td>
                <strong>{source.doc_id}</strong>
                <span>{source.title}</span>
              </td>
              <td>{roleLabels[source.retrieval_role || "primary"] || source.retrieval_role || "Primary"}</td>
              <td>{sourceLabels[source.source_type] || source.source_type}</td>
              <td>{source.time || "NA"}</td>
              <td>{source.bay || "regional"}</td>
              <td>
                {source.retrieval_role === "linked" ? (
                  <>
                    <strong>{source.link_type || "cross_source"}</strong>
                    <span>{source.linked_from_doc_id || source.linked_from_event_id || "primary evidence"}</span>
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
