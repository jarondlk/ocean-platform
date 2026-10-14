/** Replace this adapter in C08/C14. No fetch, API credentials or model calls. */
import { catalogue, snapshots, tableFor, temperatures } from "./fixtures.ts";
import { text, type Answer, type CatalogueNode, type Run, type Scenario } from "./model.ts";

export const fixtureAdapter = {
  snapshots,
  open(id: string, snapshotId: string): CatalogueNode | undefined {
    const snapshot = snapshots.find((item) => item.id === snapshotId);
    return snapshot && !snapshot.excludedIds.includes(id) ? catalogue.find((node) => node.id === id) : undefined;
  },
  inventory(snapshotId: string): CatalogueNode[] {
    return catalogue.filter((node) => this.open(node.id, snapshotId));
  },
  list({ nodeId, snapshotId, search = "", page = 1, pageSize = 5, scenario = "normal" }: { nodeId: string; snapshotId: string; search?: string; page?: number; pageSize?: number; scenario?: Scenario }) {
    if (["loading", "error", "unavailable", "revoked"].includes(scenario)) return { status: scenario, items: [] as CatalogueNode[], total: null, returned: 0, complete: false };
    const query = search.trim().toLocaleLowerCase();
    const matches = ["empty", "zero"].includes(scenario) ? [] : this.inventory(snapshotId).filter((node) => query
      ? `${node.title.en} ${node.title.ja} ${node.id} ${node.source ?? ""}`.toLocaleLowerCase().includes(query)
      : node.parentId === nodeId);
    matches.sort((a, b) => a.id.localeCompare(b.id));
    const items = matches.slice((Math.max(1, page) - 1) * pageSize, Math.max(1, page) * pageSize);
    return { status: "ready", items, total: matches.length, returned: items.length, complete: true };
  },
  descendants(id: string, snapshotId: string): CatalogueNode[] {
    const inventory = this.inventory(snapshotId);
    return inventory.filter((node) => {
      let current: CatalogueNode | undefined = node;
      while (current?.parentId) {
        if (current.parentId === id) return true;
        current = inventory.find((item) => item.id === current?.parentId);
      }
      return false;
    });
  },
  breadcrumbs(id: string, snapshotId: string): CatalogueNode[] {
    const path: CatalogueNode[] = [];
    let node = this.open(id, snapshotId);
    while (node) { path.unshift(node); node = node.parentId ? this.open(node.parentId, snapshotId) : undefined; }
    return path;
  },
  table: tableFor,
  answer(run: Run): Answer {
    const available = this.inventory(run.snapshotId).filter((node) => node.kind === "dataset");
    const question = run.question.toLocaleLowerCase();
    const temperatureQuestion = /temperature|sst|水温|温度/.test(question);
    const inputIds = ["empty", "zero"].includes(run.scenario) ? [] : run.context.constraints.length
      ? run.context.constraints.filter((id) => this.open(id, run.snapshotId))
      : temperatureQuestion ? available.filter((node) => node.source === "SST").map((node) => node.id) : available.map((node) => node.id);
    const first = this.open(inputIds[0], run.snapshotId);
    const summary = temperatureQuestion && first?.source === "SST";
    const table = summary ? { ...this.table(first), rows: inputIds.flatMap((id) => { const input = this.open(id, run.snapshotId); return input?.source === "SST" ? this.table(input).rows : []; }) } : {
      entity: text("datasets", "データセット"),
      columns: [{ key: "source", title: text("Source", "ソース") }, { key: "datasets", title: text("Datasets", "データセット") }],
      rows: (["CTD", "SST", "Metagenome", "eDNA"] as const).map((source) => ({ source, datasets: inputIds.filter((id) => this.open(id, run.snapshotId)?.source === source).length })),
    };
    const partial = run.status === "partial";
    const body = summary
      ? text("The sample regional series warms from 8.4°C in February to 22.6°C in August.", "サンプルの地域時系列では、2月の8.4°Cから8月の22.6°Cまで上昇します。")
      : text(`${inputIds.length} sample datasets match this scope. Check coverage and sampling methods before comparing sources.`, `この範囲には${inputIds.length}件のサンプルデータセットがあります。比較前にカバレッジとサンプリング手法を確認してください。`);
    const limitation = summary && first ? first.limitation : text("Casts, regional grids, libraries and assays are different units of observation.", "観測、地域グリッド、ライブラリ、アッセイは異なる観測単位です。");
    return {
      body,
      series: summary ? temperatures.map((value, i) => ({ label: `${i + 1}`, value })) : undefined,
      receipt: {
        id: `receipt-${run.id}`, operation: summary ? "summary" : "inventory", authority: "descriptive", snapshotId: run.snapshotId,
        contextRevision: run.context.revision, inputIds, parameters: { question: run.question, scope: run.context.constraints.length ? "Pinned datasets" : "Full matching sample inventory", fixtureVersion: "P00.1" },
        totalRows: summary ? table.rows.length : inputIds.length, complete: !partial, contentIdentity: `sample:${run.snapshotId}:${run.id}:P00.1`, table,
        limitation: partial ? text("Partial sample result: relationship checks remain unfinished. Continue to review them.", "部分的なサンプル結果：関連性の確認は未完了です。続行して確認してください。") : limitation,
      },
    };
  },
};
