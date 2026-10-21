/** Human-readable label from operator username (e.g. operator_f01 → Operator F01). */
export function formatUserDisplayName(username: string): string {
  const trimmed = username.trim();
  if (!trimmed) return "Operator";
  return trimmed
    .split(/[_\-.]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

/** Secondary account line — only show a real email; never fabricate a domain. */
export function resolveUserEmail(storedEmail: string | null | undefined): string | null {
  const trimmed = storedEmail?.trim();
  if (!trimmed || trimmed.endsWith("@spark.local")) return null;
  return trimmed;
}

/** Initials for avatar placeholder (max 2 chars). */
export function userInitials(username: string): string {
  const parts = username.trim().split(/[_\-.]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  const single = parts[0] ?? "O";
  return single.slice(0, 2).toUpperCase();
}
