export function rowsToCsv(rows: Record<string, unknown>[], columns?: string[]): string {
  const selectedColumns = columns?.length ? columns : inferColumns(rows);
  const header = selectedColumns.map(escapeCsvCell).join(",");
  const body = rows.map((row) => selectedColumns.map((column) => escapeCsvCell(row[column])).join(","));
  return [header, ...body].join("\n");
}

export function inferColumns(rows: Record<string, unknown>[]): string[] {
  const seen = new Set<string>();
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => seen.add(key));
  });
  return Array.from(seen);
}

export function safeCsvFilename(name: string): string {
  const cleaned = name
    .trim()
    .replace(/[^a-zA-Z0-9_.-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned ? `${cleaned}.csv` : "export.csv";
}

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  const escaped = text.replace(/"/g, '""');
  return /[",\n\r]/.test(escaped) ? `"${escaped}"` : escaped;
}
