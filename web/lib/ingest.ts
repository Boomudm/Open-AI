/** Truncate a filename for table display while preserving extension when possible. */
export function truncateFilename(name: string, max = 20): string {
  if (name.length <= max) return name;
  const dot = name.lastIndexOf(".");
  const ext = dot > 0 ? name.slice(dot) : "";
  const baseMax = max - ext.length - 1;
  if (baseMax < 1) return `${name.slice(0, max - 1)}…`;
  return `${name.slice(0, baseMax)}…${ext}`;
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
