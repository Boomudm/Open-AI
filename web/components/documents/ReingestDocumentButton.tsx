"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { api } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";

export type ReingestDocumentButtonProps = {
  docId: string;
  factoryId?: string | null;
  compact?: boolean;
  className?: string;
  onReingested?: () => void;
};

export function ReingestDocumentButton({
  docId,
  factoryId,
  compact = false,
  className,
  onReingested,
}: ReingestDocumentButtonProps) {
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!canWriteFactory(factoryId)) {
    return null;
  }

  async function handleClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    setLoading(true);
    setError("");
    try {
      await api.reingestDocument(docId);
      await queryClient.invalidateQueries({ queryKey: queryKeys.documents() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.ingestJobs() });
      onReingested?.();
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  const hint = "Re-ingest document";

  return (
    <span className={cn("inline-flex flex-col items-end", className)}>
      <Tooltip content={hint} disabled={!compact}>
        <button
          type="button"
          onClick={(e) => void handleClick(e)}
          disabled={loading}
          aria-label={hint}
          className={cn(
            "inline-flex items-center gap-1 gemini-theme-transition gemini-focus-ring relative",
            "disabled:opacity-50 disabled:cursor-not-allowed",
            compact
              ? "h-8 w-8 justify-center rounded-full text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover hover:text-gemini-blue dark:hover:text-gemini-dark-blue"
              : "text-xs px-2.5 py-1 rounded-full border border-gemini-border/70 dark:border-gemini-dark-border/70 text-gemini-muted dark:text-gemini-dark-muted hover:text-gemini-blue dark:hover:text-gemini-dark-blue",
            loading && compact && "text-transparent"
          )}
        >
          <RefreshCw className={cn(compact ? "h-4 w-4" : "h-3.5 w-3.5", loading && "animate-spin")} />
          {!compact && <span>{loading ? "Re-ingesting…" : "Re-ingest"}</span>}
          {compact && loading && (
            <Loader2 className="h-4 w-4 animate-spin absolute inset-0 m-auto" aria-hidden />
          )}
        </button>
      </Tooltip>
      {error && (
        <span className="text-[10px] text-red-600 dark:text-red-400 mt-0.5 max-w-[8rem] text-right">
          {error}
        </span>
      )}
    </span>
  );
}
