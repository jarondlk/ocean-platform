"use client";
import { useId, useState } from "react";
import { ArrowRight, Database, FileText, Folder, Link2 } from "lucide-react";
import { fixtureAdapter } from "./adapter";
import { methods, roots } from "./fixtures";
import type { CatalogueNode, Locale, Source } from "./model";
import "./catalogue-overview.css";

type Props = { locale: Locale; snapshotId: string; onOpen: (id: string) => void; onBrowse: () => void };
type LinkKind = "candidate" | "reference";
type Relationship = { from: string; to: string; kind: LinkKind };
type MapNode = { id: string; x: number; y: number };

// This is the complete map of a deliberately small 2022 selection, not a graph
// of the entire catalogue. Every visible link must exist in fixture relatedIds.
const mapLayout: MapNode[] = [
  { id: "ctd-2022", x: 20, y: 16 },
  { id: "metagenome-2022", x: 20, y: 50 },
  { id: "edna-2022", x: 20, y: 84 },
  { id: "sst-2022", x: 50, y: 50 },
  { id: "seasonal", x: 80, y: 23 },
  { id: "diversity", x: 80, y: 77 },
];
const sources: Source[] = ["CTD", "SST", "Metagenome", "eDNA"];

function selectionLinks(nodes: CatalogueNode[]): Relationship[] {
  const links: Relationship[] = [];
  const seen = new Set<string>();
  const available = new Map(nodes.map((node) => [node.id, node]));
  for (const node of nodes) for (const id of node.relatedIds) {
    const target = available.get(id);
    if (!target || target.kind !== "dataset") continue;
    const kind: LinkKind = node.kind === "dataset" ? "candidate" : "reference";
    const key = kind === "candidate" ? [node.id, id].sort().join(":") : `${node.id}:${id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    links.push({ from: node.id, to: id, kind });
  }
  return links;
}

export function CatalogueOverview({ locale, snapshotId, onOpen, onBrowse }: Props) {
  const label = (en: string, ja: string) => locale === "en" ? en : ja;
  const componentId = useId();
  const [filter, setFilter] = useState<"all" | LinkKind>("candidate");
  const [selectedId, setSelectedId] = useState("sst-2022");
  const snapshot = fixtureAdapter.snapshots.find((item) => item.id === snapshotId);
  const inventory = fixtureAdapter.inventory(snapshotId);
  const datasets = inventory.filter((node) => node.kind === "dataset");
  const records = inventory.filter((node) => node.kind !== "directory");
  const mapNodes = mapLayout.flatMap((position) => {
    const node = fixtureAdapter.open(position.id, snapshotId);
    return node ? [{ ...position, node }] : [];
  });
  const allLinks = selectionLinks(mapNodes.map(({ node }) => node));
  const links = allLinks.filter((link) => filter === "all" || link.kind === filter);
  const selected = mapNodes.find(({ id }) => id === selectedId)?.node ?? mapNodes[0]?.node;
  const relationships = selected ? links.filter((link) => link.from === selected.id || link.to === selected.id) : [];
  const positionFor = (id: string) => mapNodes.find((node) => node.id === id)!;
  const shortTitle = (node: CatalogueNode) => node.kind === "dataset" ? `${node.source} ${node.year}`
    : node.id === "seasonal" ? label("Seasonal summary", "季節別の水温集計") : label("Diversity workflow", "多様性ワークフロー");
  const nodeType = (node: CatalogueNode) => node.kind === "dataset" ? label("Dataset", "データセット")
    : node.kind === "workflow" ? label("Workflow · not run", "ワークフロー・未実行") : label("Published record · sample", "公開記録・サンプル");

  if (!snapshot) return <div className="catalogue-overview catalogue-overview-empty" role="status">
    <h2>{label("Snapshot unavailable", "スナップショットを利用できません")}</h2>
    <p>{label("Select another snapshot to browse its catalogue.", "別のスナップショットを選択してください。")}</p>
  </div>;

  return <div className="catalogue-overview">
    <section className="catalogue-overview-intro" aria-labelledby={`${componentId}-find`}>
      <div><h2 id={`${componentId}-find`}>{label("Find data and context", "データとコンテキストを探す")}</h2>
        <p>{datasets.length} {label("datasets", "データセット")} <span aria-hidden="true">·</span> {records.length} {label("catalogue records", "カタログ記録")} <span aria-hidden="true">·</span> {label("Synthetic inventory", "合成データの一覧")}</p>
      </div>
      <button className="button secondary" onClick={onBrowse}>{label("Browse data", "データを閲覧")}<ArrowRight size={15} /></button>
    </section>

    <nav className="catalogue-root-links" aria-label={label("Catalogue collections", "カタログのコレクション")}>
      {roots.map((root) => {
        const node = fixtureAdapter.open(root, snapshotId);
        const count = fixtureAdapter.descendants(root, snapshotId).filter((item) => item.kind !== "directory").length;
        const fallback = { data: label("Data", "データ"), analyses: label("Analyses", "解析"), statistics: label("Statistics", "統計"), metadata: label("Metadata", "メタデータ"), relationships: label("Relationships", "関連性") };
        return <button key={root} onClick={() => onOpen(root)} disabled={!node} title={!node ? label("Collection unavailable in this snapshot", "このスナップショットでは利用できません") : undefined}>
          <Folder size={15} aria-hidden="true" /><span>{node?.title[locale] ?? fallback[root]}</span><small>{node ? count : label("Unavailable", "利用不可")}</small>
          <span className="sr-only">{node ? label("records", "記録") : label("Unavailable in this snapshot", "このスナップショットでは利用できません")}</span>
        </button>;
      })}
    </nav>

    <section className="catalogue-source-section" aria-labelledby={`${componentId}-sources`}>
      <div className="catalogue-overview-section-heading"><h3 id={`${componentId}-sources`}>{label("By source", "ソースから探す")}</h3><span>{label("Dataset counts in this snapshot", "このスナップショットのデータセット件数")}</span></div>
      {datasets.length === 0 && <p className="catalogue-overview-notice" role="status">{label("No datasets are recorded in this snapshot.", "このスナップショットにはデータセットがありません。")}</p>}
      <div className="catalogue-source-rows">{sources.map((source) => {
        const sourceDatasets = datasets.filter((node) => node.source === source);
        const collection = fixtureAdapter.open(source.toLowerCase(), snapshotId);
        const years = Array.from(new Set(sourceDatasets.map((node) => node.year).filter((year): year is number => year !== undefined))).sort();
        return <button key={source} className="catalogue-source-row" disabled={!collection} onClick={() => onOpen(source.toLowerCase())} title={!collection ? label("Collection unavailable in this snapshot", "このスナップショットでは利用できません") : undefined}>
          <Database size={19} strokeWidth={1.5} aria-hidden="true" />
          <span className="catalogue-source-name"><strong>{source === "Metagenome" && locale === "ja" ? "メタゲノム" : source}</strong><span>{methods[source].title[locale]}</span></span>
          <span className="catalogue-source-years">{!collection ? label("Collection unavailable", "コレクション利用不可") : years.length ? years.join(" · ") : label("No datasets", "データセットなし")}</span>
          <span className="catalogue-source-count"><strong>{sourceDatasets.length}</strong><small>{label("datasets", "データセット")}</small></span>
          <ArrowRight size={15} aria-hidden="true" />
          {!collection && <span className="sr-only">{label("Collection unavailable in this snapshot", "このスナップショットでは利用できません")}</span>}
        </button>;
      })}</div>
    </section>

    <section className="catalogue-relationship-section" aria-labelledby={`${componentId}-relationships`}>
      <div className="catalogue-overview-section-heading"><div><h3 id={`${componentId}-relationships`}>{label("Inspect relationships", "関連性を確認")}</h3><p>{label("2022 selection", "2022年の選択記録")} <span aria-hidden="true">·</span> {mapNodes.length} {label("of", "/")} {records.length} {label("catalogue records", "カタログ記録")}</p></div><Link2 size={17} aria-hidden="true" /></div>
      <fieldset className="catalogue-map-filters"><legend className="sr-only">{label("Show relationship type", "表示する関連性の種類")}</legend>
        {(["candidate", "reference", "all"] as const).map((kind) => <label key={kind} className={filter === kind ? "selected" : ""}><input type="radio" name={`${componentId}-link-kind`} value={kind} checked={filter === kind} onChange={() => setFilter(kind)} /><span>{kind === "candidate" ? label("Candidate links", "候補リンク") : kind === "reference" ? label("Analysis references", "解析の参照") : label("All links", "すべてのリンク")}</span></label>)}
      </fieldset>
      <p className="catalogue-map-qualification">{filter === "candidate" ? label("Related source records; time and space proximity is not checked.", "ソース記録間の候補。時間・空間の近接性は未確認です。") : filter === "reference" ? label("Record references show context, not validated inputs or scientific approval.", "記録の参照はコンテキストです。検証済みの入力や科学的承認を示しません。") : label("Dashed: candidate source links. Solid: analysis record references.", "破線：ソース間の候補。実線：解析記録の参照。")}</p>
      {mapNodes.length === 0 ? <p className="catalogue-overview-notice" role="status">{label("This selection has no available records in the current snapshot.", "現在のスナップショットでは、この選択記録を利用できません。")}</p> : <>
        <div className="catalogue-map-scroll"><div className="catalogue-map" role="group" aria-label={label("Relationship map; the same records and links are listed below", "関連性マップ。同じ記録とリンクの一覧が下にあります")}>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" className="catalogue-map-lines">{links.map((link) => {
            const from = positionFor(link.from); const to = positionFor(link.to);
            // References bend outside the central source links to keep this tiny
            // graph readable. They never imply source-data physical identity.
            const curve = link.kind === "reference" && to.id === "ctd-2022";
            return <path key={`${link.from}-${link.to}`} className={`catalogue-map-link ${link.kind}`} d={curve ? `M ${from.x} ${from.y} C ${from.x - 7} ${from.y - 18}, ${to.x + 22} ${to.y - 11}, ${to.x} ${to.y}` : `M ${from.x} ${from.y} L ${to.x} ${to.y}`} vectorEffect="non-scaling-stroke" />;
          })}</svg>
          {mapNodes.map(({ node, x, y }) => <button key={node.id} className={`catalogue-map-node ${selected?.id === node.id ? "selected" : ""} ${node.kind !== "dataset" ? "analysis-record" : ""}`} style={{ left: `${x}%`, top: `${y}%` }} onClick={() => setSelectedId(node.id)} aria-pressed={selected?.id === node.id} aria-controls={`${componentId}-detail`} aria-label={`${shortTitle(node)} — ${node.title[locale]} — ${nodeType(node)}`}>
            <strong>{shortTitle(node)}</strong><span>{nodeType(node)}</span>
          </button>)}
        </div></div>
        <div className="catalogue-map-record-list" role="group" aria-label={label("Map records", "マップの記録一覧")}>{mapNodes.map(({ node }) => <button key={node.id} aria-pressed={selected?.id === node.id} aria-controls={`${componentId}-detail`} onClick={() => setSelectedId(node.id)}>{node.kind === "dataset" ? <Database size={13} aria-hidden="true" /> : <FileText size={13} aria-hidden="true" />}<span>{shortTitle(node)}</span><span className="sr-only">{nodeType(node)}</span></button>)}</div>
        {selected && <article className="catalogue-map-detail" id={`${componentId}-detail`} aria-labelledby={`${componentId}-detail-title`}>
          <div className="catalogue-map-detail-heading"><div><span>{nodeType(selected)}</span><h4 id={`${componentId}-detail-title`}>{selected.title[locale]}</h4></div><button className="text-button" onClick={() => onOpen(selected.id)}>{label("Open record", "記録を開く")}<ArrowRight size={14} /></button></div>
          <p>{selected.purpose[locale]}</p><p className="catalogue-map-detail-limitation">{selected.limitation[locale]}</p>
          <p className="catalogue-map-selected-links" role="status">{relationships.length ? <>{label("Shown links", "表示中のリンク")}: {relationships.map((link) => {
            const other = mapNodes.find(({ id }) => id === (link.from === selected.id ? link.to : link.from))!.node;
            return `${shortTitle(other)} (${link.kind === "candidate" ? label("candidate", "候補") : label("record reference", "記録の参照")})`;
          }).join(" · ")}</> : label("No links shown for this record with the current filter.", "現在のフィルターでは、この記録のリンクはありません。")}</p>
        </article>}
        <details className="catalogue-map-link-list"><summary>{label("Relationship list", "関連性の一覧")} <span>({links.length})</span></summary>
          {links.length === 0 ? <p>{label("No links match this filter.", "このフィルターに一致するリンクはありません。")}</p> : <ul>{links.map((link) => {
            const from = positionFor(link.from).node; const to = positionFor(link.to).node;
            return <li key={`${link.from}-${link.to}`}><span className={`catalogue-link-key ${link.kind}`} aria-hidden="true" /><span>{shortTitle(from)} {link.kind === "reference" ? label("references", "が参照"): "↔"} {shortTitle(to)}<small>{link.kind === "candidate" ? label("Candidate source link · unverified", "ソース間の候補・未確認") : label("Analysis record reference · sample", "解析記録の参照・サンプル")}</small></span></li>;
          })}</ul>}
        </details>
      </>}
      <div className="catalogue-identity-note"><div><strong>{label("Physical identity", "物理的な試料の識別")}</strong><p>{label("No verified physical pairing is recorded in these fixtures.", "この合成データに検証済みの物理的な対応付けはありません。")}</p></div>
        <div>{fixtureAdapter.open("identities", snapshotId) && <button className="text-button" onClick={() => onOpen("identities")}>{label("Identity records", "識別情報")}<ArrowRight size={13} /></button>}{fixtureAdapter.open("matching", snapshotId) && <button className="text-button" onClick={() => onOpen("matching")}>{label("Matching rules", "対応付けルール")}<ArrowRight size={13} /></button>}</div>
      </div>
    </section>
  </div>;
}
