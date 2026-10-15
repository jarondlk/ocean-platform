export function rowsToCsv(rows: Record<string, unknown>[], columns?: string[]): string {
  const selectedColumns = columns?.length ? columns : inferColumns(rows);
  const header = selectedColumns.map((column) => escapeCsvCell(column)).join(",");
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

// Explicit Python/ECMAScript whitespace union, shared with the Python fixture
// contract. Native \s differs between the two runtimes for U+001C–001F/U+0085.
const UNSAFE_CSV_TEXT = /^(?:[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]*[=+@-]|[\t\r\n])/u;

/**
 * Escape only at the CSV boundary: original string values/headers that could
 * execute as spreadsheet formulas receive a leading apostrophe. Numbers retain
 * their sign; null/undefined are empty; objects/arrays use compact JSON.
 * alwaysQuote preserves the v1 export dialect without changing the policy.
 */
export function escapeCsvCell(value: unknown, alwaysQuote = false): string {
  const text = value === null || value === undefined
    ? ""
    : typeof value === "object" ? JSON.stringify(value) : String(value);
  const protectedText = typeof value === "string" && UNSAFE_CSV_TEXT.test(value) ? `'${text}` : text;
  const escaped = protectedText.replace(/"/g, '""');
  return alwaysQuote || /[",\n\r]/.test(protectedText) ? `"${escaped}"` : escaped;
}
