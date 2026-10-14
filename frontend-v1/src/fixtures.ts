import { text, type CatalogueNode, type Snapshot, type Source, type Table, type Text } from "./model.ts";

export const snapshots: Snapshot[] = [
  { id: "sample-02", title: text("Sample 02 · latest", "サンプル02・最新"), date: "2026-10-13", excludedIds: ["ctd-2021"] },
  { id: "sample-01", title: text("Sample 01", "サンプル01"), date: "2026-10-01", excludedIds: ["edna-2023", "metagenome-2023"] },
];
const directory = (id: string, parentId: string | null, title: Text, root: CatalogueNode["root"]): CatalogueNode => ({
  id, parentId, title, root, kind: "directory", purpose: text("Synthetic catalogue collection.", "合成データのカタログコレクション。"),
  limitation: text("Sample inventory only.", "サンプルの一覧です。"), relatedIds: [],
});
export const roots = ["data", "analyses", "statistics", "metadata", "relationships"] as const;
const sourceInfo: Record<Source, { title: Text; purpose: Text; limitation: Text; method: Text }> = {
  CTD: {
    title: text("Water profiles", "海水の鉛直プロファイル"),
    purpose: text("Temperature and salinity by cast and depth.", "観測ごとの深度別の水温・塩分。"),
    limitation: text("Depth measurements are not independent sampling events.", "深度ごとの測定値は独立した採水イベントではありません。"),
    method: text("Synthetic CTD cast; depth in metres, temperature in °C, salinity in PSU.", "合成CTD観測。深度：m、水温：°C、塩分：PSU。"),
  },
  SST: {
    title: text("Regional temperature", "地域の海面水温"),
    purpose: text("A regional surface-temperature series.", "地域の海面水温時系列。"),
    limitation: text("Regional SST does not establish temperature at a sampling site.", "地域の海面水温は採水地点の水温を示すものではありません。"),
    method: text("Synthetic MUR-style regional series; monthly sample values in °C. Not real satellite measurements.", "MURを参考にした合成の地域時系列。月別サンプル値（°C）。実際の衛星測定値ではありません。"),
  },
  Metagenome: {
    title: text("Community composition", "群集組成"),
    purpose: text("Complete abundance rows for a small sample community.", "小さなサンプル群集の全存在量データ。"),
    limitation: text("This is the full synthetic table. Omission from a preview never means zero abundance.", "合成データの全テーブルです。プレビューからの省略は存在量ゼロを意味しません。"),
    method: text("Synthetic relative abundance; eight taxa, one library, percentages sum to 100.", "合成相対存在量。8分類群、1ライブラリ、合計100%。"),
  },
  eDNA: {
    title: text("Species detections", "種の検出"),
    purpose: text("Source occurrences, assays and control qualifications.", "ソース出現記録、アッセイ、対照の条件。"),
    limitation: text("An occurrence is not a physical sample. A non-detection does not prove absence.", "出現記録は物理的な試料ではありません。未検出は不在を証明しません。"),
    method: text("Synthetic MiFish-style assays. Environmental samples and negative controls are labelled separately.", "MiFishを参考にした合成アッセイ。環境試料と陰性対照を区別しています。"),
  },
};
export const methods = sourceInfo;
const datasets: CatalogueNode[] = (["CTD", "SST", "Metagenome", "eDNA"] as Source[]).flatMap((source) => [2021, 2022, 2023].map((year) => ({
  id: `${source.toLowerCase()}-${year}`, parentId: source.toLowerCase(), source, year, root: "data" as const, kind: "dataset" as const,
  title: text(`${source === "SST" ? "Miyagi" : "Onagawa"} · ${sourceInfo[source].title.en} ${year}`, `${source === "SST" ? "宮城" : "女川"}・${sourceInfo[source].title.ja} ${year}`),
  purpose: sourceInfo[source].purpose, limitation: sourceInfo[source].limitation,
  relatedIds: [`${source === "SST" ? "ctd" : "sst"}-${year}`, "matching", "units"],
})));
const reference = (id: string, parentId: string, title: Text, purpose: Text, root: CatalogueNode["root"], kind: CatalogueNode["kind"] = "reference"): CatalogueNode => ({
  id, parentId, title, purpose, root, kind, limitation: text("Illustrative fixture; no real scientific approval.", "説明用サンプル。実際の科学的承認はありません。"), relatedIds: ["sst-2022", "ctd-2022"],
});
export const catalogue: CatalogueNode[] = [
  directory("data", null, text("Data", "データ"), "data"),
  directory("analyses", null, text("Analyses", "解析"), "analyses"),
  directory("statistics", null, text("Statistics", "統計"), "statistics"),
  directory("metadata", null, text("Metadata", "メタデータ"), "metadata"),
  directory("relationships", null, text("Relationships", "関連性"), "relationships"),
  ...(["CTD", "SST", "Metagenome", "eDNA"] as Source[]).map((source) => ({ ...directory(source.toLowerCase(), "data", text(source, source === "Metagenome" ? "メタゲノム" : source), "data"), source })),
  ...datasets,
  directory("published", "analyses", text("Published results", "公開済みの結果"), "analyses"),
  directory("workflows", "analyses", text("Available workflows", "利用可能なワークフロー"), "analyses"),
  reference("seasonal", "published", text("Seasonal temperature summary", "季節別の水温集計"), text("Illustrative published-analysis record; authority is not independently verified.", "公開解析を模した記録。独立した科学的検証はありません。"), "analyses", "analysis"),
  reference("diversity", "workflows", text("Community diversity", "群集多様性"), text("A workflow description, not a completed finding.", "完了した知見ではなく、ワークフローの説明です。"), "analyses", "workflow"),
  reference("inventory", "statistics", text("Inventory counts", "インベントリ件数"), text("Counts of canonical datasets in this sample snapshot.", "サンプルスナップショット内の正規データセット件数。"), "statistics"),
  reference("coverage", "statistics", text("Coverage and gaps", "カバレッジと欠測"), text("Source-specific spatial and temporal coverage.", "ソースごとの空間・時間カバレッジ。"), "statistics"),
  reference("units", "metadata", text("Variables and units", "変数と単位"), text("Temperature (°C), depth (m), salinity (PSU), abundance (%).", "水温（°C）、深度（m）、塩分（PSU）、存在量（%）。"), "metadata"),
  reference("sampling", "metadata", text("Sampling methods", "サンプリング手法"), text("Keep casts, regional grids, libraries and assays distinct.", "観測、地域グリッド、ライブラリ、アッセイを区別します。"), "metadata"),
  reference("provenance", "metadata", text("Source provenance", "ソースの来歴"), text("All records are locally generated synthetic fixtures.", "すべての記録はローカルで生成した合成データです。"), "metadata"),
  reference("identities", "relationships", text("Sample identities", "試料の識別情報"), text("Physical identity is distinct from a source occurrence.", "物理的な試料の識別情報とソース出現記録は異なります。"), "relationships"),
  reference("matching", "relationships", text("Matching rules", "対応付けルール"), text("Proximity links are candidates; they are not verified comparisons.", "近接リンクは候補であり、検証済みの比較ではありません。"), "relationships"),
];
export const temperatures = [9.2, 8.4, 9.6, 11.9, 15.1, 18.4, 21.2, 22.6, 21.3, 18.4, 14.9, 11.5];
export function tableFor(node: CatalogueNode): Table {
  if (node.source === "SST") return {
    entity: text("monthly regional observations", "月別の地域観測"),
    columns: [{ key: "date", title: text("Month", "月") }, { key: "temperature", title: text("SST", "海面水温"), unit: "°C" }, { key: "support", title: text("Support", "空間単位") }],
    rows: temperatures.map((temperature, i) => ({ date: `${node.year}-${String(i + 1).padStart(2, "0")}`, temperature, support: "Regional / 地域" })),
  };
  if (node.source === "CTD") return {
    entity: text("depth measurements · 1 cast", "深度別測定値・1観測"),
    columns: [{ key: "cast", title: text("Cast", "観測") }, { key: "depth", title: text("Depth", "深度"), unit: "m" }, { key: "temperature", title: text("Temperature", "水温"), unit: "°C" }, { key: "salinity", title: text("Salinity", "塩分"), unit: "PSU" }],
    rows: [0, 2, 5, 10, 15, 20, 25, 30].map((depth, i) => ({ cast: `sample-${node.year}-01`, depth, temperature: +(18.6 - i * 0.7).toFixed(1), salinity: +(32.1 + i * 0.1).toFixed(1) })),
  };
  if (node.source === "Metagenome") return {
    entity: text("taxa · 1 sample library", "分類群・1試料ライブラリ"),
    columns: [{ key: "taxon", title: text("Taxon", "分類群") }, { key: "abundance", title: text("Abundance", "存在量"), unit: "%" }],
    rows: ["Taxon A", "Taxon B", "Taxon C", "Taxon D", "Taxon E", "Taxon F", "Taxon G", "Taxon H"].map((taxon, i) => ({ taxon, abundance: [32, 24, 15, 10, 8, 5, 4, 2][i] })),
  };
  if (node.source === "eDNA") return {
    entity: text("assays · 4 source occurrences", "アッセイ・4ソース出現記録"),
    columns: [{ key: "occurrence", title: text("Occurrence", "出現記録") }, { key: "assay", title: text("Assay", "アッセイ") }, { key: "type", title: text("Type", "種別") }, { key: "detection", title: text("Detection", "検出") }],
    rows: Array.from({ length: 8 }, (_, i) => ({ occurrence: `sample-${node.year}-${Math.floor(i / 2) + 1}`, assay: `MiFish-${i + 1}`, type: i >= 6 ? "Negative control / 陰性対照" : "Environmental / 環境", detection: i % 3 ? "Detected / 検出" : "Not detected / 未検出" })),
  };
  return {
    entity: text("definition records", "定義レコード"),
    columns: [{ key: "name", title: text("Definition", "定義") }, { key: "value", title: text("Value", "値") }],
    rows: [{ name: "fixture", value: "Synthetic / 合成データ" }, { name: "id", value: node.id }, { name: "version", value: "P00.1" }],
  };
}
