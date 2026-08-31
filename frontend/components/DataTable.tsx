"use client";

import { useAppPreferences } from "@/lib/preferences";

type DataTableProps = {
  columns: string[];
  rows: Record<string, unknown>[];
  emptyText?: string;
  rowKeyColumn?: string;
  selectedKey?: string;
  onRowSelect?: (row: Record<string, unknown>, index: number, rowKey: string) => void;
  isRowSelectable?: (row: Record<string, unknown>, index: number) => boolean;
};

export function DataTable({
  columns,
  rows,
  emptyText = "No rows.",
  rowKeyColumn = "sample_id",
  selectedKey,
  onRowSelect,
  isRowSelectable,
}: DataTableProps) {
  const { ui } = useAppPreferences();
  if (!rows.length) {
    return <p className="empty-state">{ui(emptyText)}</p>;
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
            const selectable = Boolean(
              onRowSelect && (!isRowSelectable || isRowSelectable(row, index)),
            );
            return (
              <tr
                className={selectable ? "selectable-row" : undefined}
                key={rowKey}
                onClick={selectable ? () => onRowSelect?.(row, index, rowKey) : undefined}
                onKeyDown={
                  selectable
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowSelect?.(row, index, rowKey);
                        }
                      }
                    : undefined
                }
                tabIndex={selectable ? 0 : undefined}
                aria-selected={selectable ? selectedKey === rowKey : undefined}
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
