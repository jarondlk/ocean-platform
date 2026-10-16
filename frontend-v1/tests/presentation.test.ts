import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_PRESENTATION, PRESENTATION_STORAGE_KEY, defaultPresentation, parsePresentation, restorePresentation, serializePresentation } from "../src/presentation.ts";

test("new storage namespace cannot load P00 or legacy state implicitly", () => {
  assert.equal(PRESENTATION_STORAGE_KEY, "ocean-v1-presentation-v1");
  assert.notEqual(PRESENTATION_STORAGE_KEY, "ocean-p00-synthetic-v1");
  assert.deepEqual(restorePresentation(null), DEFAULT_PRESENTATION);
});
test("valid display preferences round trip and defaults never alias callers", () => {
  const value = { locale: "ja", theme: "dark", workspaceWidth: 620, workspaceOpen: false, mobilePane: "workspace" };
  assert.deepEqual(restorePresentation(serializePresentation(value)), value);
  const one = defaultPresentation(); one.theme = "dark";
  assert.equal(defaultPresentation().theme, "light");
});
for (const width of [NaN, Infinity, -Infinity, -1, 0, 319, 621, 2 ** 54, 390.5, "390", true]) test(`invalid panel width ${String(width)} restores bounded default`, () => {
  assert.equal(parsePresentation({ workspaceWidth: width }).workspaceWidth, 390);
});
test("presentation restoration cannot accept role, account, permission, snapshot or scope", () => {
  const scientific = { snapshot_id: "retained-snapshot", scope: { only: "original" } };
  const before = structuredClone(scientific);
  const value = parsePresentation({ locale: "ja", theme: "dark", role: "admin", account_type: "internal", permissions: ["users:manage"], scope: scientific.scope, snapshot_id: scientific.snapshot_id, investigations: [{ fake: true }] });
  assert.deepEqual(Object.keys(value).sort(), ["locale", "theme", "workspaceWidth", "workspaceOpen", "mobilePane"].sort());
  assert.equal(value.locale, "ja"); assert.deepEqual(scientific, before);
  assert.equal(serializePresentation({ ...value, role: "admin", scope: scientific.scope }).includes("admin"), false);
});
test("invalid or oversized storage remains presentational defaults", () => {
  for (const raw of ["broken JSON", "null", "[]", '"admin"', "x".repeat(8193)]) assert.deepEqual(restorePresentation(raw), DEFAULT_PRESENTATION);
  assert.deepEqual(parsePresentation({ locale: "de", theme: "admin", workspaceOpen: "true", mobilePane: "experiments" }), DEFAULT_PRESENTATION);
});
test("legacy nested preferences cannot migrate authority into v1", () => {
  assert.deepEqual(parsePresentation({ preferences: { locale: "ja", role: "admin", accountType: "internal" } }), DEFAULT_PRESENTATION);
});
