import type { ReactNode } from "react";
import { citationIdsFromBracketToken } from "@/lib/citation-navigation";
import type { CitationTarget } from "@/lib/citation-navigation";

type Block =
  | { kind: "paragraph"; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "blockquote"; text: string }
  | { kind: "code"; language: string; text: string }
  | { kind: "table"; headers: string[]; rows: string[][] };

const inlinePatternSource = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\)|\[[A-Za-z0-9_:.-]+(?:\s*[,;]\s*[A-Za-z0-9_:.-]+)*\])/;

type RenderOptions = {
  citationTargets?: ReadonlyMap<string, CitationTarget>;
  onCitationSelect?: (target: CitationTarget) => void;
};

export function MarkdownAnswer({
  text,
  citationTargets,
  onCitationSelect,
}: {
  text: string;
  citationTargets?: ReadonlyMap<string, CitationTarget>;
  onCitationSelect?: (target: CitationTarget) => void;
}) {
  const blocks = parseMarkdown(text);
  if (!blocks.length) {
    return <div className="answer">No response.</div>;
  }

  return (
    <div className="answer answer-markdown">
      {blocks.map((block, index) => renderBlock(block, index, { citationTargets, onCitationSelect }))}
    </div>
  );
}

function parseMarkdown(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "code", language, text: codeLines.join("\n") });
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      index += 1;
      continue;
    }

    if (isTableStart(lines, index)) {
      const headers = splitTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ kind: "table", headers, rows });
      continue;
    }

    const unordered = /^\s*[-*]\s+(.+)$/.exec(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.exec(line);
    if (unordered || ordered) {
      const orderedList = Boolean(ordered);
      const items: string[] = [];
      while (index < lines.length) {
        const match = orderedList
          ? /^\s*\d+[.)]\s+(.+)$/.exec(lines[index])
          : /^\s*[-*]\s+(.+)$/.exec(lines[index]);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ kind: "list", ordered: orderedList, items });
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ kind: "blockquote", text: quoteLines.join(" ") });
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length && shouldContinueParagraph(lines, index)) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function shouldContinueParagraph(lines: string[], index: number): boolean {
  const trimmed = lines[index].trim();
  if (!trimmed) return false;
  if (trimmed.startsWith("```") || trimmed.startsWith(">")) return false;
  if (/^(#{1,4})\s+/.test(trimmed)) return false;
  if (/^\s*[-*]\s+/.test(lines[index]) || /^\s*\d+[.)]\s+/.test(lines[index])) return false;
  if (isTableStart(lines, index)) return false;
  return true;
}

function isTableStart(lines: string[], index: number): boolean {
  if (index + 1 >= lines.length) return false;
  return lines[index].includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1]);
}

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderBlock(block: Block, index: number, options: RenderOptions): ReactNode {
  if (block.kind === "heading") {
    const Tag = block.level <= 2 ? "h4" : "h5";
    return <Tag key={index}>{renderInline(block.text, `h-${index}`, options)}</Tag>;
  }
  if (block.kind === "list") {
    const Tag = block.ordered ? "ol" : "ul";
    return (
      <Tag key={index}>
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{renderInline(item, `li-${index}-${itemIndex}`, options)}</li>
        ))}
      </Tag>
    );
  }
  if (block.kind === "blockquote") {
    return <blockquote key={index}>{renderInline(block.text, `q-${index}`, options)}</blockquote>;
  }
  if (block.kind === "code") {
    return (
      <pre className="answer-code" key={index}>
        <code>{block.text}</code>
      </pre>
    );
  }
  if (block.kind === "table") {
    return (
      <div className="markdown-table-wrap" key={index}>
        <table className="markdown-table">
          <thead>
            <tr>
              {block.headers.map((header, headerIndex) => (
                <th key={headerIndex}>{renderInline(header, `th-${index}-${headerIndex}`, options)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {block.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {block.headers.map((_header, cellIndex) => (
                  <td key={cellIndex}>{renderInline(row[cellIndex] || "", `td-${index}-${rowIndex}-${cellIndex}`, options)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }
  return <p key={index}>{renderInline(block.text, `p-${index}`, options)}</p>;
}

function renderInline(text: string, keyPrefix: string, options: RenderOptions): ReactNode[] {
  const nodes: ReactNode[] = [];
  const inlinePattern = new RegExp(inlinePatternSource.source, "g");
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = inlinePattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(text.slice(cursor, match.index));
    }
    const token = match[0];
    const key = `${keyPrefix}-${match.index}`;
    nodes.push(renderInlineToken(token, key, options));
    cursor = match.index + token.length;
  }

  if (cursor < text.length) {
    nodes.push(text.slice(cursor));
  }
  return nodes;
}

function renderInlineToken(token: string, key: string, options: RenderOptions): ReactNode {
  if (token.startsWith("`") && token.endsWith("`")) {
    return <code key={key}>{token.slice(1, -1)}</code>;
  }
  if (token.startsWith("**") && token.endsWith("**")) {
    return <strong key={key}>{renderInline(token.slice(2, -2), `${key}-strong`, options)}</strong>;
  }
  if (token.startsWith("*") && token.endsWith("*")) {
    return <em key={key}>{renderInline(token.slice(1, -1), `${key}-em`, options)}</em>;
  }
  const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
  if (link) {
    const safeLink = sanitizeHref(link[2]);
    if (!safeLink) {
      return <span key={key}>{link[1]}</span>;
    }
    return (
      <a
        href={safeLink.href}
        key={key}
        rel={safeLink.external ? "noopener noreferrer" : undefined}
        target={safeLink.external ? "_blank" : undefined}
      >
        {link[1]}
      </a>
    );
  }
  const citationIds = citationIdsFromBracketToken(token);
  if (citationIds.length) {
    return (
      <span className="citation-chip-group" key={key}>
        {citationIds.map((citationId) => {
          const target = options.citationTargets?.get(citationId);
          if (target?.valid && options.onCitationSelect) {
            return (
              <button
                aria-label={`Inspect citation ${citationId}`}
                className="citation-chip citation-chip-button"
                key={citationId}
                onClick={() => options.onCitationSelect?.(target)}
                title={target.title}
                type="button"
              >
                [{citationId}]
              </button>
            );
          }
          return (
            <span
              aria-disabled={target && !target.valid ? "true" : undefined}
              className={`citation-chip${target && !target.valid ? " citation-chip-invalid" : ""}`}
              key={citationId}
              title={target?.detail}
            >
              [{citationId}]
            </span>
          );
        })}
      </span>
    );
  }
  return token;
}

function sanitizeHref(rawHref: string): { href: string; external: boolean } | null {
  const href = rawHref.trim();
  if (!href || /[\u0000-\u001f\u007f\\]/.test(href) || href.startsWith("//")) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(href, "https://ocean-platform.invalid");
  } catch {
    return null;
  }

  const hasExplicitScheme = /^[a-z][a-z0-9+.-]*:/i.test(href);
  if (hasExplicitScheme && !["http:", "https:"].includes(parsed.protocol)) {
    return null;
  }

  const external = parsed.protocol === "http:" || parsed.protocol === "https:"
    ? parsed.origin !== "https://ocean-platform.invalid"
    : false;
  if (!external && parsed.origin !== "https://ocean-platform.invalid") {
    return null;
  }

  return { href, external };
}
