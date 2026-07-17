import type { SourceDocument } from "@/types";

const sourceLabels: Record<string, string> = {
  ctd: "CTD",
  metagenome: "Metagenome",
  remote_sensing: "SST",
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
            <th>Source</th>
            <th>Time</th>
            <th>Bay</th>
            <th>Score</th>
            <th>Text</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((source) => (
            <tr key={source.doc_id}>
              <td>
                <strong>{source.doc_id}</strong>
                <span>{source.title}</span>
              </td>
              <td>{sourceLabels[source.source_type] || source.source_type}</td>
              <td>{source.time || "NA"}</td>
              <td>{source.bay || "regional"}</td>
              <td>{source.score ? source.score.toFixed(4) : "NA"}</td>
              <td>{source.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
