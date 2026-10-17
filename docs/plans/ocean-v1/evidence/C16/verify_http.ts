/** Exercise the actual C16 browser client over an explicitly owned HTTP fixture. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { writeFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import { createCatalogueClient, defaultCatalogueScope } from "../../../../../frontend-v1/src/catalogue-service.ts";
import type { CatalogueListRequest, CatalogueNode } from "../../../../../frontend-v1/src/catalogue-service.ts";
import { catalogueLocationUrl, parseCatalogueLocation } from "../../../../../frontend-v1/src/catalogue-browser-state.ts";

const expectedCount = Number(process.argv[2]);
assert.equal(expectedCount, 100_000, "This acceptance probe requires the explicit100000-object fixture");
const port = Number(process.argv[3] ?? 3101);
assert([3100, 3101].includes(port));
const started = performance.now();
let requests = 0;
let transferred = 0;
const client = createCatalogueClient({ fetcher: async (input, init) => {
  assert.match(input, /^\/catalogue\/[a-z/-]+$/);
  assert.equal(init?.method, "POST"); assert.equal(init?.credentials, "omit");
  assert.equal(init?.cache, "no-store"); assert.equal(init?.redirect, "error");
  requests++;
  const response = await fetch(`http://127.0.0.1:${port}` + input, init);
  transferred += Number(response.headers.get("content-length") ?? 0);
  return response;
} });
const scope = defaultCatalogueScope();
const discovery = await client.snapshots({ scope });
assert.equal(discovery.total, 1);
assert.equal(discovery.latest_snapshot_id, "a".repeat(64));
const common = { snapshot_id: discovery.latest_snapshot_id!, scope };
const datasets = new Set<string>();
let listingPages = 0;
async function* pages(request: CatalogueListRequest) {
  const cursors = new Set<string>();
  while (true) {
    const page = await client.list(request);
    yield page;
    if (page.next_cursor === null) break;
    assert(!cursors.has(page.next_cursor), "Continuation must progress");
    cursors.add(page.next_cursor);
    const restored = parseCatalogueLocation(new URL(catalogueLocationUrl({
      ...parseCatalogueLocation(""), snapshotId: request.snapshot_id,
      parentId: request.parent_id ?? null, filters: request.filters ?? {},
      limit: request.limit ?? 100, cursor: page.next_cursor,
    }), "http://127.0.0.1:3100").search);
    assert.equal(restored.cursor, page.next_cursor);
    assert.equal(restored.snapshotId, request.snapshot_id);
    request = { ...request, cursor: restored.cursor };
  }
}
for await (const page of pages({ ...common, filters: { kinds: ["dataset"] }, limit: 500 })) {
  listingPages++;
  assert.equal(page.total.state, "known"); assert.equal(page.total.value, expectedCount);
  assert.equal(page.source_completeness, "complete"); assert.equal(page.query_completion, "complete");
  assert.equal(page.items.length, 500);
  for (const node of page.items) { assert(!datasets.has(node.id)); datasets.add(node.id); }
}
assert.equal(listingPages, 200); assert.equal(datasets.size, expectedCount);
const expectedIds = Array.from({ length: expectedCount }, (_, i) => "synthetic:dataset:" + String(i).padStart(6, "0"));
assert.deepEqual([...datasets].sort(), expectedIds);

const roots = await client.overview(common);
assert.equal(roots.items.length, 5);
const queue: CatalogueNode[] = [...roots.items];
const directoryIds = new Set<string>();
const treeDatasets = new Set<string>();
const treeNodes = new Set(roots.items.map((node) => node.id));
let treePages = 0;
while (queue.length) {
  const parent = queue.shift()!;
  assert(!directoryIds.has(parent.id)); directoryIds.add(parent.id);
  for await (const page of pages({ ...common, parent_id: parent.id, limit: 500 })) {
    treePages++;
    for (const node of page.items) {
      assert.equal(node.parent_id, parent.id); assert(!treeNodes.has(node.id)); treeNodes.add(node.id);
      if (node.kind === "dataset") treeDatasets.add(node.id);
      if (node.kind === "directory") queue.push(node);
    }
  }
}
assert.deepEqual([...treeDatasets].sort(), expectedIds);
assert.equal(directoryIds.size, 9);
const targets = [];
for (const rank of [26, 502, 100_000]) {
  const id = expectedIds[rank - 1];
  const node = await client.open({ ...common, object_id: id });
  const found = await client.list({ ...common, filters: { search: id }, limit: 1 });
  const throughParent = await client.list({ ...common, parent_id: node.parent_id, filters: { search: id }, limit: 1 });
  assert.equal(node.id, id); assert.equal(found.total.value, 1); assert.equal(found.items[0]?.id, id);
  assert.equal(throughParent.total.value, 1); assert.equal(throughParent.items[0]?.id, id);
  targets.push({ rank, id, parent_id: node.parent_id, direct_and_parent_search: true });
}
for (const hidden of ["synthetic:hidden", "synthetic:revoked", "synthetic:private-experiment"]) {
  const result = await client.list({ ...common, filters: { search: hidden } });
  assert.equal(result.total.value, 0); assert.equal(result.items.length, 0);
}
const hash = createHash("sha256").update(expectedIds.join("\n") + "\n").digest("hex");
const result = {
  state: "pass", expected_datasets: expectedCount, unique_browser_listing_ids: datasets.size,
  browser_listing_pages: listingPages, unique_tree_dataset_ids: treeDatasets.size,
  canonical_tree_objects: treeNodes.size, reachable_roots_and_directories: directoryIds.size,
  tree_pages: treePages, dataset_id_sequence_sha256: hash, targets, requests,
  response_content_length_bytes: transferred, wall_seconds: Number(((performance.now() - started) / 1000).toFixed(2)),
  node_rss_bytes: process.memoryUsage().rss,
  qualification: "Actual C16 client/validation/state boundary over owned loopback HTTP and real C14 service with explicit immutable synthetic100000 backend; not production latency/capacity or rendered100000 DOM nodes",
};
writeFileSync(new URL("./http-scale-result.json", import.meta.url), JSON.stringify(result, null, 2) + "\n");
process.stdout.write(JSON.stringify(result) + "\n");
