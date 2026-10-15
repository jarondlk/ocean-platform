import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  CatalogueContractError, canonicalSourceFamily, catalogueAdapterV1,
  catalogueContractSchema, parseCatalogueContractModel,
} from "../src/catalogue-contract.ts";
import type {
  CatalogueListing, CatalogueModels, CatalogueNode, CurrentCatalogueAccess,
  OperationRequest, QueryResult,
} from "../src/catalogue-contract.ts";

type Examples = {
  schema_version: string;
  nodes: CatalogueNode[];
  listings: CatalogueListing[];
  operations: OperationRequest[];
  results: QueryResult[];
  invalid: { model: keyof CatalogueModels; value: unknown; reason: string }[];
};
const examples = JSON.parse(readFileSync(new URL("../../schema/context_catalogue_examples.json", import.meta.url), "utf8")) as Examples;
const copy = <T>(value: T): T => structuredClone(value);
const permissions = (listing: CatalogueListing): CurrentCatalogueAccess => ({
  snapshotId: listing.request.snapshot_id,
  accessRevision: listing.request.access_revision,
  accessBinding: listing.request.access_binding,
  allowedIds: new Set(examples.nodes.map((node) => node.id)),
});
function singleNodeListing(node: CatalogueNode): CatalogueListing {
  const value = copy(examples.listings[0]);
  value.request.cursor = null;
  value.request.limit = 100;
  value.items = [copy(node)];
  value.returned_count = 1;
  value.total = { state: "known", entity: "canonical_objects", denominator: "all matching permitted canonical objects", value: 1 };
  value.next_cursor = null;
  value.preview_truncated = false;
  return value;
}

for (const [index, node] of examples.nodes.entries()) {
  test(`shared node ${index}: ${node.id}`, async () => {
    const before = copy(node);
    const parsed = await parseCatalogueContractModel("CatalogueNode", node);
    assert.deepEqual(parsed, node);
    assert.deepEqual(node, before);
    assert.notEqual(parsed, node);
  });
}
for (const [index, listing] of examples.listings.entries()) {
  test(`shared listing ${index}: ${listing.total.state}/${listing.availability.status}`, async () => {
    assert.deepEqual(await parseCatalogueContractModel("CatalogueListing", listing), listing);
  });
}
for (const operation of examples.operations) {
  test(`shared operation: ${operation.operation_id}`, async () => {
    assert.deepEqual(await parseCatalogueContractModel("OperationRequest", operation), operation);
  });
}
for (const result of examples.results) {
  test(`shared result: ${result.receipt.receipt_id}`, async () => {
    assert.deepEqual(await parseCatalogueContractModel("QueryResult", result), result);
  });
}
for (const invalid of examples.invalid) {
  test(`reject shared invalid case: ${invalid.reason}`, async () => {
    await assert.rejects(parseCatalogueContractModel(invalid.model, invalid.value), CatalogueContractError);
  });
}

test("the complete exported contract validates through one boundary", async () => {
  const contract = {
    schema_version: examples.schema_version,
    node: examples.nodes[0], listing_request: examples.listings[0].request,
    listing: examples.listings[0], operation_request: examples.operations[0],
    receipt: examples.results[0].receipt, query_result: examples.results[0],
  };
  assert.deepEqual(await parseCatalogueContractModel("CatalogueContract", contract), contract);
});

test("optional factory defaults normalize without mutating external input", async () => {
  const input = copy(examples.nodes[0]);
  delete input.operations;
  delete input.related_ids;
  delete input.sections;
  delete input.provenance.references;
  const parsed = await parseCatalogueContractModel("CatalogueNode", input);
  assert.deepEqual(parsed.operations, []);
  assert.deepEqual(parsed.related_ids, []);
  assert.deepEqual(parsed.sections, []);
  assert.deepEqual(parsed.provenance.references, []);
  assert.equal(Object.hasOwn(input, "operations"), false);
});

test("legacy aliases and P00 labels use the exported Python registry", () => {
  for (const [alias, family] of Object.entries(catalogueContractSchema["x-source-aliases"])) assert.equal(canonicalSourceFamily(alias), family);
  for (const [label, family] of [["CTD", "ctd"], [" SST ", "remote_sensing"], ["Metagenome", "metagenome"], ["eDNA", "edna_metabarcoding"]]) assert.equal(canonicalSourceFamily(label), family);
  for (const invalid of [null, true, 0, "unknown", "ctd/2026", "\uFEFFsst"]) assert.throws(() => canonicalSourceFamily(invalid), CatalogueContractError);
});

test("P00 projection preserves canonical identities and source labels", async () => {
  for (const [family, label] of [["ctd", "CTD"], ["metagenome", "Metagenome"], ["remote_sensing", "SST"], ["edna_metabarcoding", "eDNA"]]) {
    const node = examples.nodes.find((item) => item.kind === "dataset" && item.source_family === family)!;
    const payload = singleNodeListing(node), before = copy(payload);
    const result = await catalogueAdapterV1.list(payload, permissions(payload));
    assert.equal(result.status, "ready");
    if (result.status !== "ready") throw new Error("Expected a ready catalogue projection");
    assert.equal(result.items[0].id, node.id);
    assert.equal(result.items[0].source, label);
    assert.deepEqual(result.items[0].title, node.title);
    assert.deepEqual(result.items[0].purpose, node.purpose);
    assert.deepEqual(result.contract.items[0].descriptor, node.descriptor);
    assert.deepEqual(result.contract.items[0].sections, catalogueContractSchema["x-dataset-sections"]);
    assert.deepEqual(payload, before);
  }
});

test("new kinds project explicitly without changing the prototype type", async () => {
  const kinds: [CatalogueNode["kind"], string][] = [["root", "directory"], ["table", "reference"], ["statistic", "reference"], ["metadata", "reference"], ["relationship", "reference"], ["analysis", "analysis"], ["workflow", "workflow"]];
  for (const [kind, expected] of kinds) {
    const node = copy(examples.nodes.find((item) => item.kind === "root")!);
    if (kind !== "root") { node.kind = kind; node.id = `synthetic:${kind}`; node.parent_id = "root:metadata"; }
    const payload = singleNodeListing(node), access = permissions(payload);
    access.allowedIds = new Set([...access.allowedIds, node.id]);
    const result = await catalogueAdapterV1.list(payload, access);
    assert.equal(result.status, "ready");
    if (result.status === "ready") {
      assert.equal(result.items[0].kind, expected);
      assert.equal(result.contract.items[0].kind, kind);
    }
  }
});

test("unknown and unavailable never become an empty known catalogue", async () => {
  const unknown = examples.listings.find((item) => item.total.state === "unknown" && item.availability.status === "available")!;
  const unknownResult = await catalogueAdapterV1.list(unknown, permissions(unknown));
  assert.equal(unknownResult.status, "ready");
  assert.equal(unknownResult.total, null);
  const zero = examples.listings.find((item) => item.total.value === 0)!;
  assert.equal((await catalogueAdapterV1.list(zero, permissions(zero))).total, 0);
  const unavailable = examples.listings.find((item) => item.availability.status === "unavailable")!;
  const result = await catalogueAdapterV1.list(unavailable, permissions(unavailable));
  assert.equal(result.status, "unavailable");
  assert.equal(result.total, null);
  assert.deepEqual(result.items, []);
});

test("a missing or malformed backend produces unavailable without fixture fallback", async () => {
  for (const payload of [undefined, null, {}, { ...examples.listings[0], schema_version: "context-catalogue-v99" }]) {
    const result = await catalogueAdapterV1.list(payload, permissions(examples.listings[0]));
    assert.equal(result.status, "unavailable");
    assert.deepEqual(result.items, []);
    assert.equal(result.total, null);
  }
});

test("permission revision or principal changes invalidate even empty cached membership", async () => {
  for (const listing of [examples.listings[0], examples.listings.find((item) => item.total.value === 0)!]) {
    for (const override of [{ accessRevision: "new-revision" }, { accessBinding: "another-principal" }]) {
      const result = await catalogueAdapterV1.list(listing, { ...permissions(listing), ...override });
      assert.equal(result.status, "revoked");
      assert.deepEqual(result.items, []);
      assert.equal(result.total, null);
    }
  }
});

test("revoked nodes, parents and related links are not retained in projections", async () => {
  const linked = examples.nodes.find((item) => (item.related_ids ?? []).length > 0)!;
  for (const id of [linked.id, linked.parent_id!, linked.related_ids![0]]) {
    const payload = singleNodeListing(linked), access = permissions(payload);
    access.allowedIds = new Set([...access.allowedIds].filter((candidate) => candidate !== id));
    const result = await catalogueAdapterV1.list(payload, access);
    assert.equal(result.status, "revoked");
    assert.equal(Object.hasOwn(result, "contract"), false);
    assert.deepEqual(result.items, []);
  }
});

test("snapshot selection and provenance origins cannot silently select another backend", async () => {
  const payload = examples.listings[0];
  const result = await catalogueAdapterV1.list(payload, { ...permissions(payload), snapshotId: "other-snapshot" });
  assert.equal(result.status, "unavailable");
  const transferred = examples.nodes.find((node) => node.provenance.origin)!;
  assert.ok(transferred);
  const projected = await catalogueAdapterV1.list(singleNodeListing(transferred), permissions(payload));
  assert.equal(projected.status, "ready");
  if (projected.status === "ready") assert.deepEqual(projected.contract.items[0].provenance.origin, transferred.provenance.origin);
});

test("readiness, authority and completion remain independent fields", async () => {
  const node = copy(examples.nodes.find((item) => item.kind === "dataset")!);
  node.lifecycle.query_readiness = "ready";
  node.lifecycle.embedding_readiness = "not_ready";
  node.lifecycle.scientific_approval = "unknown";
  node.lifecycle.ingestion = "partial";
  node.authority = "descriptive";
  const payload = singleNodeListing(node);
  payload.source_completeness = "partial";
  payload.query_completion = "complete";
  const result = await catalogueAdapterV1.list(payload, permissions(payload));
  assert.equal(result.status, "ready");
  if (result.status === "ready") {
    assert.equal(result.complete, true);
    assert.equal(result.contract.preview_truncated, false);
    assert.equal(result.contract.source_completeness, "partial");
    assert.deepEqual(result.contract.items[0].lifecycle, node.lifecycle);
    assert.equal(result.contract.items[0].authority, "descriptive");
  }
});

test("wire input rejects non-JSON values and cannot modify object prototypes", async () => {
  const operation = copy(examples.operations[0]);
  for (const invalid of [NaN, Infinity, undefined, 1n, () => 1, new Date()]) {
    const value = { ...operation, parameters: { value: invalid } };
    await assert.rejects(parseCatalogueContractModel("OperationRequest", value), CatalogueContractError);
  }
  const parameters = JSON.parse('{"__proto__":{"polluted":"yes"},"constructor":{"prototype":{"polluted":"yes"}}}') as OperationRequest["parameters"];
  const parsed = await parseCatalogueContractModel("OperationRequest", { ...operation, parameters });
  assert.equal(Object.hasOwn(parsed.parameters!, "__proto__"), true);
  assert.equal(Object.getPrototypeOf(parsed.parameters!), Object.prototype);
  assert.equal(Object.hasOwn({}, "polluted"), false);
});
