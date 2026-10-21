import type { Source } from "@/lib/api";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function optionalString(value: unknown): string | null | undefined {
  if (value === null) return null;
  return typeof value === "string" ? value : undefined;
}

function optionalNumber(value: unknown): number | null | undefined {
  if (value === null) return null;
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function optionalBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

/** Strictly parse a single RAG citation from SSE or REST payloads. */
export function parseChatSource(raw: unknown): Source | null {
  const record = asRecord(raw);
  if (!record) return null;

  const score = record.score;
  if (typeof score !== "number" || !Number.isFinite(score)) return null;

  return {
    doc_id: optionalString(record.doc_id),
    title: optionalString(record.title),
    source_file: optionalString(record.source_file),
    page: optionalNumber(record.page),
    source_sheet: optionalString(record.source_sheet),
    row_number: optionalNumber(record.row_number),
    extraction_source: optionalString(record.extraction_source),
    needs_review: optionalBoolean(record.needs_review),
    spans: Array.isArray(record.spans)
      ? (record.spans as { text?: string | null }[])
      : undefined,
    document_type: optionalString(record.document_type),
    score,
    view_url: optionalString(record.view_url),
    can_view: optionalBoolean(record.can_view),
    chunk_id: optionalString(record.chunk_id),
  };
}

export function parseChatSources(raw: unknown): Source[] {
  if (!Array.isArray(raw)) return [];
  const parsed: Source[] = [];
  for (const item of raw) {
    const source = parseChatSource(item);
    if (source) parsed.push(source);
  }
  return parsed;
}
