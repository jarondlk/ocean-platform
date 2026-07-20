type DataTableProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  emptyText?: string;
  rowKeyColumn?: string;
  selectedKey?: string;
  onRowSelect?: (row: Record<string, unknown>, index: number, rowKey: string) => void;
};

export function DataTable({
  columns,
  rows,
  emptyText = "No rows.",
  rowKeyColumn = "sample_id",
  selectedKey,
  onRowSelect,
}: DataTableProps) {
  if (!rows.length) {
    return <p className="empty-state">{emptyText}</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const rowKey = String(row[rowKeyColumn] ?? row.event_id ?? row.id ?? index);
            return (
              <tr
                className={onRowSelect ? "selectable-row" : undefined}
                key={rowKey}
                onClick={onRowSelect ? () => onRowSelect(row, index, rowKey) : undefined}
                onKeyDown={
                  onRowSelect
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowSelect(row, index, rowKey);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowSelect ? 0 : undefined}
                aria-selected={selectedKey === rowKey}
              >
                {columns.map((column) => (
                  <td key={column}>{formatCell(row[column])}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "NA";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
