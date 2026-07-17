import type { SampleDetailResponse } from "@/types";
import { DataTable, formatCell } from "@/components/DataTable";

export function SampleDetail({ detail }: { detail: SampleDetailResponse | null }) {
  if (!detail) {
    return <p className="empty-state">Select a row with a sample_id.</p>;
  }

  return (
    <div className="detail-stack">
      <h3 className="section-title">{detail.sample_id}</h3>
      <DetailRecord title="Registry" record={detail.registry || undefined} />
      <DetailRows title="CTD" rows={detail.ctd} />
      <DetailRows title="Diversity" rows={detail.diversity} />
      <DetailRows title="Reliability" rows={detail.reliability} />
      <DetailRows
        title="Evidence documents"
        rows={detail.documents.map((doc) => ({
          doc_id: doc.doc_id,
          source_type: doc.source_type,
          title: doc.title,
          time: doc.time,
        }))}
      />
    </div>
  );
}

function DetailRecord({
  title,
  record,
}: {
  title: string;
  record?: Record<string, unknown>;
}) {
  if (!record) {
    return (
      <section className="detail-section">
        <h4>{title}</h4>
        <p className="empty-state">No record.</p>
      </section>
    );
  }

  return (
    <section className="detail-section">
      <h4>{title}</h4>
      <table className="detail-table">
        <tbody>
          {Object.entries(record).map(([key, value]) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              <td>{formatCell(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function DetailRows({ title, rows }: { title: string; rows: Record<string, unknown>[] }) {
  const columns = rows.length ? Object.keys(rows[0]).slice(0, 10) : [];
  return (
    <section className="detail-section">
      <h4>{title}</h4>
      {rows.length ? (
        <DataTable columns={columns} rows={rows} />
      ) : (
        <p className="empty-state">No rows.</p>
      )}
    </section>
  );
}
