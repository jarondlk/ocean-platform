import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { escapeCsvCell, inferColumns, rowsToCsv, safeCsvFilename } from "./csv.ts";

type CsvCase = { id: string; kind: string; value?: unknown; expected_text: string; expected_cell: string };
const fixture = JSON.parse(readFileSync(new URL("../../schema/csv_serialization_cases.json", import.meta.url), "utf8")) as { cases: CsvCase[] };

for (const example of fixture.cases) {
  test(`shared CSV fixture: ${example.id}`, () => {
    const value = example.kind === "undefined" ? undefined : example.value;
    assert.equal(escapeCsvCell(value), example.expected_cell);
    assert.equal(escapeCsvCell(value, true), `"${example.expected_text.replaceAll('"', '""')}"`);
    assert.equal(rowsToCsv([{ value }]), `value\n${example.expected_cell}`);
    if (typeof value === "string") assert.equal(rowsToCsv([], [value]), example.expected_cell);
  });
}

test("CSV protects formula text and headers while preserving signed numeric measurements", () => {
  const rows = [{ "=sample": " =1+1", temperature: -2.5, textual: "-2.5", ordinary: "日本の海" }];
  assert.equal(rowsToCsv(rows), "'=sample,temperature,textual,ordinary\n' =1+1,-2.5,'-2.5,日本の海");
  assert.deepEqual(rows, [{ "=sample": " =1+1", temperature: -2.5, textual: "-2.5", ordinary: "日本の海" }]);
});

test("CSV protects leading control strings and the complete shared whitespace set", () => {
  for (const whitespace of ["\t", "\n", "\r", "\v", "\f", "\u001c", "\u001d", "\u001e", "\u001f", " ", "\u0085", "\u00a0", "\u1680", "\u2000", "\u2001", "\u2002", "\u2003", "\u2004", "\u2005", "\u2006", "\u2007", "\u2008", "\u2009", "\u200a", "\u2028", "\u2029", "\u202f", "\u205f", "\u3000", "\ufeff"]) {
    const raw = `${whitespace}=1`;
    const expected = /[\n\r]/.test(raw) ? `"'${raw}"` : `'${raw}`;
    assert.equal(rowsToCsv([{ value: raw }]), `value\n${expected}`, `U+${whitespace.charCodeAt(0).toString(16)}`);
  }
  assert.equal(rowsToCsv([{ value: "\tordinary" }]), "value\n'\tordinary");
});

test("CSV preserves column order, minimal quoting, empty cells and compact JSON", () => {
  const rows = [{ b: 'A,"B"\nC', a: { sample: "日本", value: -2.5 }, c: null }, { d: true, b: "ordinary" }];
  assert.deepEqual(inferColumns(rows), ["b", "a", "c", "d"]);
  assert.equal(rowsToCsv(rows, ["d", "b", "c"]), 'd,b,c\n,"A,""B""\nC",\ntrue,ordinary,');
  assert.equal(rowsToCsv([{ value: { sample: "日本", value: -2.5 } }]), 'value\n"{""sample"":""日本"",""value"":-2.5}"');
  assert.equal(rowsToCsv([]), "");
  assert.equal(rowsToCsv([], ["=header", "ordinary"]), "'=header,ordinary");
});

test("CSV filename behavior remains stable", () => {
  assert.equal(safeCsvFilename(" sample data_2026 "), "sample_data_2026.csv");
  assert.equal(safeCsvFilename("温度"), "export.csv");
});
