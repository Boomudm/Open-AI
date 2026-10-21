export function sourceLocator(source: {
  page?: number | null;
  source_sheet?: string | null;
  row_number?: number | null;
}): string | null {
  if (source.page != null) return `p.${source.page}`;
  if (source.source_sheet && source.row_number != null) {
    return `${source.source_sheet} · row ${source.row_number}`;
  }
  if (source.source_sheet) return source.source_sheet;
  return null;
}
