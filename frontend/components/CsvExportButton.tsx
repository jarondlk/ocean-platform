"use client";

import { Download } from "lucide-react";
import { rowsToCsv, safeCsvFilename } from "@/lib/csv";

type CsvExportButtonProps = {
  rows: Record<string, unknown>[];
  columns?: string[];
  filename: string;
  label?: string;
};

export function CsvExportButton({
  rows,
  columns,
  filename,
  label = "CSV",
}: CsvExportButtonProps) {
  function downloadCsv() {
    const csv = rowsToCsv(rows, columns);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = safeCsvFilename(filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      className="button secondary-button"
      disabled={!rows.length}
      onClick={downloadCsv}
      title="Download the currently loaded table rows as CSV."
      type="button"
    >
      <Download size={15} aria-hidden="true" />
      {label}
    </button>
  );
}
