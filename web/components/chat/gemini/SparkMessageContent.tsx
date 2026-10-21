"use client";

import { cn } from "@/lib/cn";
import { Table, TableBody, TableHeader, TableRow } from "@/components/ui/Table";
import { Fragment, memo, type ReactNode, useMemo } from "react";

type SparkMessageContentProps = {
  content: string;
  className?: string;
};

// Inline markdown: **bold** and `code`. Single-star italic is deliberately
// unsupported — spec text like "3*2.5 sq.mm" would false-positive as italic,
// and Thai answers never use it.
const INLINE_TOKEN_RE = /(\*\*[^*]+\*\*|`[^`\n]+`)/g;

function renderInline(text: string): ReactNode[] {
  const parts = text.split(INLINE_TOKEN_RE);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return (
        <strong key={i} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code
          key={i}
          className="rounded-[0.3rem] border border-gemini-border/50 bg-gemini-surface px-1 py-px font-mono text-[0.85em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

// Lines inside one block keep their line breaks — the model is instructed to
// put each step on its own line, and joining Thai lines with a space inserts
// a spurious word gap (Thai has no inter-word spaces).
function renderTextLines(lines: string[]): ReactNode[] {
  return lines.map((line, idx) => (
    <Fragment key={idx}>
      {idx > 0 && <br />}
      {renderInline(line)}
    </Fragment>
  ));
}

type ListItem = { text: string; subs: string[] };

type Block =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "ul"; items: ListItem[] }
  | { type: "ol"; start: number; items: ListItem[] }
  | { type: "table"; header: string[]; rows: string[][] }
  | { type: "code"; text: string }
  | { type: "quote"; lines: string[] }
  | { type: "hr" }
  | { type: "p"; lines: string[] };

const HEADING_RE = /^(#{1,4})\s+(.+)$/;
const BULLET_RE = /^[-*•]\s+(.+)$/;
const NUMBERED_RE = /^(\d+)[.)]\s+(.+)$/;
const HR_RE = /^(?:-{3,}|_{3,}|\*{3,})$/;
const FENCE_RE = /^```/;

// A leading "- " can appear on a table's header row because the backend
// formats each piece of evidence as one bullet — strip it before parsing the
// row so it doesn't get mistaken for list-item text.
function stripLeadingBullet(line: string): string {
  return line.replace(/^[-*•]\s+/, "");
}

function parseTableRow(line: string): string[] | null {
  const t = line.trim();
  if (t.length < 2 || !t.startsWith("|") || !t.endsWith("|")) return null;
  return t
    .slice(1, -1)
    .split("|")
    .map((cell) => cell.trim());
}

function isTableSeparatorRow(line: string): boolean {
  const cells = parseTableRow(line);
  if (!cells || cells.length === 0) return false;
  return cells.every((c) => c === "" || /^:?-{1,}:?$/.test(c));
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function isListItemLine(trimmed: string): boolean {
  return BULLET_RE.test(trimmed) || NUMBERED_RE.test(trimmed);
}

function breaksParagraph(trimmed: string): boolean {
  return (
    !trimmed ||
    HEADING_RE.test(trimmed) ||
    isListItemLine(trimmed) ||
    HR_RE.test(trimmed) ||
    FENCE_RE.test(trimmed) ||
    trimmed.startsWith(">") ||
    trimmed.startsWith("|")
  );
}

// Collects one list (ul or ol) starting at lines[i]. Items indented deeper
// than the first item become sub-items of the previous item; indented plain
// lines continue the previous item; blank lines between items of the same
// list are tolerated so the model's loose spacing doesn't split the list.
function collectList(
  lines: string[],
  start: number,
  kind: "ul" | "ol"
): { items: ListItem[]; olStart: number; next: number } {
  const items: ListItem[] = [];
  const baseIndent = indentOf(lines[start]);
  const ownRe = kind === "ul" ? BULLET_RE : NUMBERED_RE;
  let olStart = 1;
  let i = start;

  while (i < lines.length) {
    const raw = lines[i];
    const trimmed = raw.trim();

    if (!trimmed) {
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) j += 1;
      if (
        j < lines.length &&
        ownRe.test(lines[j].trim()) &&
        indentOf(lines[j]) <= baseIndent
      ) {
        i = j;
        continue;
      }
      break;
    }

    const indent = indentOf(raw);
    const bullet = trimmed.match(BULLET_RE);
    const numbered = trimmed.match(NUMBERED_RE);

    if (indent > baseIndent + 1 && items.length > 0) {
      const last = items[items.length - 1];
      if (bullet) {
        last.subs.push(bullet[1]);
      } else if (numbered) {
        last.subs.push(numbered[2]);
      } else {
        last.text += `\n${trimmed}`;
      }
      i += 1;
      continue;
    }

    const own = kind === "ul" ? bullet : numbered;
    if (!own) break;

    if (kind === "ol" && items.length === 0 && numbered) {
      olStart = parseInt(numbered[1], 10) || 1;
    }
    items.push({ text: kind === "ul" ? bullet![1] : numbered![2], subs: [] });
    i += 1;
  }

  return { items, olStart, next: i };
}

function parseBlocks(content: string): Block[] {
  const lines = content.split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      i += 1;
      continue;
    }

    if (FENCE_RE.test(trimmed)) {
      i += 1;
      const codeLines: string[] = [];
      while (i < lines.length && !FENCE_RE.test(lines[i].trim())) {
        codeLines.push(lines[i]);
        i += 1;
      }
      i += 1;
      if (codeLines.length > 0) {
        blocks.push({ type: "code", text: codeLines.join("\n") });
      }
      continue;
    }

    const heading = trimmed.match(HEADING_RE);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length <= 2 ? 2 : 3,
        text: heading[2],
      });
      i += 1;
      continue;
    }

    if (HR_RE.test(trimmed)) {
      blocks.push({ type: "hr" });
      i += 1;
      continue;
    }

    const headerRow = parseTableRow(stripLeadingBullet(trimmed));
    if (
      headerRow &&
      i + 1 < lines.length &&
      isTableSeparatorRow(stripLeadingBullet(lines[i + 1].trim()))
    ) {
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length) {
        const row = parseTableRow(lines[i].trim());
        if (!row) break;
        rows.push(row);
        i += 1;
      }
      blocks.push({ type: "table", header: headerRow, rows });
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ""));
        i += 1;
      }
      blocks.push({ type: "quote", lines: quoteLines });
      continue;
    }

    if (BULLET_RE.test(trimmed)) {
      const { items, next } = collectList(lines, i, "ul");
      blocks.push({ type: "ul", items });
      i = next;
      continue;
    }

    if (NUMBERED_RE.test(trimmed)) {
      const { items, olStart, next } = collectList(lines, i, "ol");
      blocks.push({ type: "ol", start: olStart, items });
      i = next;
      continue;
    }

    const paraLines: string[] = [trimmed];
    i += 1;
    while (i < lines.length && !breaksParagraph(lines[i].trim())) {
      paraLines.push(lines[i].trim());
      i += 1;
    }
    blocks.push({ type: "p", lines: paraLines });
  }

  return blocks;
}

function ListItems({ items }: { items: ListItem[] }) {
  return (
    <>
      {items.map((item, j) => (
        <li key={j} className="pl-0.5">
          {renderTextLines(item.text.split("\n"))}
          {item.subs.length > 0 && (
            <ul className="mt-1.5 list-[circle] space-y-1 pl-4 marker:text-gemini-muted dark:marker:text-gemini-dark-muted">
              {item.subs.map((sub, k) => (
                <li key={k} className="pl-0.5">
                  {renderInline(sub)}
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </>
  );
}

function SparkMessageContentInner({ content, className }: SparkMessageContentProps) {
  const blocks = useMemo(() => parseBlocks(content), [content]);

  if (blocks.length === 0) {
    return (
      <p className={cn("chat-system-body", className)}>
        {content}
      </p>
    );
  }

  return (
    <div className={cn("chat-system-body space-y-3", className)}>
      {blocks.map((block, idx) => {
        if (block.type === "heading") {
          const Tag = block.level === 2 ? "h2" : "h3";
          return (
            <Tag
              key={idx}
              className={cn(
                "font-semibold tracking-[-0.01em] text-[color:var(--gemini-chat-body)]",
                // space-y wins over mt-* on children, so breathing room above
                // headings comes from padding instead.
                block.level === 2
                  ? "pt-1.5 text-[1rem] leading-6"
                  : "pt-0.5 text-[0.9375rem] leading-6"
              )}
            >
              {renderInline(block.text)}
            </Tag>
          );
        }

        if (block.type === "ul") {
          return (
            <ul
              key={idx}
              className="list-disc space-y-1.5 pl-5 marker:text-gemini-muted dark:marker:text-gemini-dark-muted"
            >
              <ListItems items={block.items} />
            </ul>
          );
        }

        if (block.type === "ol") {
          return (
            <ol
              key={idx}
              start={block.start}
              className="list-decimal space-y-1.5 pl-5 marker:text-gemini-muted dark:marker:text-gemini-dark-muted"
            >
              <ListItems items={block.items} />
            </ol>
          );
        }

        if (block.type === "table") {
          // Plain th/td (not the shared TableHead/TableCell) — those default
          // to whitespace-nowrap, which is right for short admin-table
          // columns but wrong here: spec-table description cells run long
          // and need to wrap instead of forcing the table to scroll wide.
          return (
            <Table key={idx} className="my-1">
              <TableHeader>
                <TableRow>
                  {block.header.map((cell, j) => (
                    <th
                      key={j}
                      className="px-3 py-2 text-left text-xs font-mono uppercase tracking-wider text-spark-text-secondary font-medium align-top"
                    >
                      {renderInline(cell)}
                    </th>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {block.rows.map((row, r) => (
                  <TableRow key={r}>
                    {row.map((cell, c) => (
                      <td
                        key={c}
                        className="px-3 py-2 text-[0.8125rem] leading-[1.55] text-spark-text-primary align-top"
                      >
                        {renderInline(cell)}
                      </td>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          );
        }

        if (block.type === "code") {
          return (
            <pre
              key={idx}
              className="overflow-x-auto rounded-lg border border-gemini-border/60 bg-gemini-surface px-3.5 py-3 font-mono text-[0.8125rem] leading-relaxed"
            >
              <code>{block.text}</code>
            </pre>
          );
        }

        if (block.type === "quote") {
          return (
            <blockquote
              key={idx}
              className="border-l-2 border-gemini-border pl-3 text-gemini-muted dark:text-gemini-dark-muted"
            >
              {renderTextLines(block.lines)}
            </blockquote>
          );
        }

        if (block.type === "hr") {
          return <hr key={idx} className="border-gemini-border/60" />;
        }

        return <p key={idx}>{renderTextLines(block.lines)}</p>;
      })}
    </div>
  );
}

export const SparkMessageContent = memo(SparkMessageContentInner);
