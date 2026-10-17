import assert from "node:assert/strict";
import test from "node:test";
import { CatalogueLocationError, DATASET_SECTIONS, catalogueLocationUrl, parseCatalogueLocation, updateCatalogueLocation } from "../src/catalogue-browser-state.ts";
import type { CatalogueSelectionEvent } from "../src/catalogue-browser-state.ts";
import { defaultCatalogueScope } from "../src/catalogue-service.ts";

test("empty location defaults to latest discovery with complete unfiltered navigation", () => {
  assert.deepEqual(parseCatalogueLocation(""), { snapshotId: null, nodeId: null, parentId: null, cursor: null, section: "overview", limit: 100, filters: { roots: [], source_families: [], kinds: [], authorities: [], search: null } });
  assert.equal(catalogueLocationUrl(parseCatalogueLocation("")), "/?view=catalogue");
});
for (const section of DATASET_SECTIONS) test(`deep-link round trip preserves snapshot, deep object, filters, paging and ${section}`, () => {
  const value = parseCatalogueLocation(`?snapshot=${"a".repeat(64)}&node=c13%3Ametadata%3Aleaf&parent=dir%3Actd&search=Data+%2F+CTD+%2F+Leaf&roots=metadata,data&sources=edna_metabarcoding,ctd&kinds=dataset,metadata&authorities=published,descriptive&cursor=opaque%2Btoken%3D&section=${section}&limit=500`);
  assert.deepEqual(parseCatalogueLocation(new URL(catalogueLocationUrl(value), "https://v1.invalid").search), value);
  assert.equal(value.filters.search, "Data / CTD / Leaf"); assert.deepEqual(value.filters.roots, ["data", "metadata"]);
  assert.deepEqual(value.filters.source_families, ["ctd", "edna_metabarcoding"]); assert.equal(value.cursor, "opaque+token=");
});
for (const query of ["?snapshot=../private", "?node=/etc/passwd", "?parent=", "?cursor=", "?limit=0", "?limit=501", "?limit=1.5", "?limit=true", "?limit=01", "?limit=1e2", "?section=execute", "?roots=private", "?sources=edna", "?kinds=experiment", "?authorities=admin", "?kinds=dataset,dataset", "?search=", "?node=one&node=two", "?limit=100&limit=200", "?section=tables&section=coverage", "?sources=ctd&sources=metagenome", "?cursor=" + "x".repeat(2049), "?search=" + "x".repeat(4001), "?snapshot=" + "a".repeat(257)]) test(`rejects malformed catalogue query ${query.slice(0, 75)}`, () => {
  assert.throws(() => parseCatalogueLocation(query), CatalogueLocationError);
});
test("forged authorization, attach, investigation, scope and preview state cannot enter navigation", () => {
  const plain = parseCatalogueLocation("?node=synthetic%3Adataset");
  assert.deepEqual(parseCatalogueLocation("?node=synthetic%3Adataset&role=admin&access_binding=forged&access_revision=forged&account_type=internal&attach=true&pin=true&scope=all&investigation=other&mode=synthetic-preview&preview=1"), plain);
  const url = catalogueLocationUrl(plain); assert.doesNotMatch(url, /role|access_|scope|attach|pin|investigation|preview/);
});
test("known navigation duplicates fail even among otherwise ignored query fields", () => {
  assert.throws(() => parseCatalogueLocation("?role=viewer&snapshot=one&role=admin&snapshot=two"), CatalogueLocationError);
});
test("navigation state remains detached from input and external scientific scope", () => {
  const current = parseCatalogueLocation("?node=dataset%3Aa&sources=ctd"), before = structuredClone(current), scope = defaultCatalogueScope(), scopeBefore = structuredClone(scope);
  const next = updateCatalogueLocation(current, { filters: { source_families: ["metagenome"], search: "leaf" } });
  next.filters.source_families?.push("remote_sensing"); assert.deepEqual(current, before); assert.deepEqual(scope, scopeBefore);
});
for (const patch of [{ snapshotId: "new-snapshot" }, { parentId: "new-parent" }, { filters: { search: "new" } }, { limit: 500 }]) test(`membership change resets stale cursor ${JSON.stringify(patch)}`, () => {
  const current = parseCatalogueLocation("?snapshot=old&node=leaf&parent=dir&cursor=opaque&section=tables"), next = updateCatalogueLocation(current, patch);
  assert.equal(next.cursor, null); assert.equal(current.cursor, "opaque");
});
test("snapshot switching clears old selected object, parent and inspector unless explicit", () => {
  const current = parseCatalogueLocation("?snapshot=old&node=old-leaf&parent=old-dir&cursor=opaque&section=coverage");
  const changed = updateCatalogueLocation(current, { snapshotId: "new" }); assert.equal(changed.nodeId, null); assert.equal(changed.parentId, null); assert.equal(changed.section, "overview");
  const explicit = updateCatalogueLocation(current, { snapshotId: "new", nodeId: "new-leaf", parentId: "new-dir", section: "methods" }); assert.equal(explicit.nodeId, "new-leaf"); assert.equal(explicit.parentId, "new-dir"); assert.equal(explicit.section, "methods");
});
test("inspector section updates preserve current page and object; new object defaults overview", () => {
  const current = parseCatalogueLocation("?node=leaf&cursor=opaque&section=tables");
  const next = updateCatalogueLocation(current, { section: "provenance" }); assert.equal(next.cursor, "opaque"); assert.equal(next.nodeId, "leaf");
  assert.equal(updateCatalogueLocation(current, { nodeId: "another" }).section, "overview");
});
test("restored URL remains sufficient across Back, Forward and reload", () => {
  const first = parseCatalogueLocation("?snapshot=old&node=leaf&sources=ctd&section=tables"), second = updateCatalogueLocation(first, { filters: { search: "Data / CTD / Deep" } }), third = updateCatalogueLocation(second, { cursor: "page-2" });
  const history = [first, second, third].map(catalogueLocationUrl);
  for (const [index, expected] of [first, second, third, second, first, second, third].entries()) {
    const pos = [0, 1, 2, 1, 0, 1, 2][index]; assert.deepEqual(parseCatalogueLocation(new URL(history[pos], "https://v1.invalid").search), expected);
  }
});
test("selection is an explicit event contract without attach or pin mutation", () => {
  const event: CatalogueSelectionEvent = { type: "catalogue.selection", object_id: "dataset:one", snapshot_id: "snapshot:one", scope: defaultCatalogueScope() };
  assert.deepEqual(Object.keys(event), ["type", "object_id", "snapshot_id", "scope"]);
});
test("state patch rejects authority fields rather than persisting them", () => {
  assert.throws(() => updateCatalogueLocation(parseCatalogueLocation(""), { role: "admin" } as never), CatalogueLocationError);
});
