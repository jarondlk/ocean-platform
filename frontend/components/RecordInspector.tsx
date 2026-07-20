import { formatCell } from "@/components/DataTable";

type RecordInspectorProps = {
  row: Record<string, unknown> | null;
  emptyText?: string;
};

export function RecordInspector({ row, emptyText = "Select a row." }: RecordInspectorProps) {
  if (!row) {
    return <p className="empty-state">{emptyText}</p>;
  }

  return (
    <div className="record-inspector">
      {Object.entries(row).map(([key, value]) => (
        <div className="record-field" key={key}>
          <span>{key}</span>
          <strong>{valueType(value)}</strong>
          {isLongValue(value) ? (
            <pre className="code-block">{formatInspectorValue(value)}</pre>
          ) : (
            <em>{formatCell(value)}</em>
          )}
        </div>
      ))}
    </div>
  );
}

function valueType(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

function isLongValue(value: unknown): boolean {
  if (Array.isArray(value) || (value && typeof value === "object")) return true;
  return typeof value === "string" && value.length > 160;
}

function formatInspectorValue(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}
