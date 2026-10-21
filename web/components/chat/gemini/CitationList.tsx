"use client";

import { sourceLocator } from "@/components/chat/gemini/sourceLocator";
import { FeedbackReportButton } from "@/components/feedback/FeedbackReportButton";
import { useChatSession } from "@/contexts/ChatSessionContext";
import type { IndexedDocument, Source } from "@/lib/api";
import { isUuid } from "@/lib/chat";
import { cn } from "@/lib/cn";
import {
  MSG_INDEXED_DOCS,
  MSG_NO_INDEXED_DOCS,
  MSG_SOURCES_LOADING,
} from "@/lib/messages.th";

export type CitationListProps = {
  sources: Source[];
  indexedDocuments: IndexedDocument[];
  indexedLoading?: boolean;
  messageId?: string | null;
  onItemOpen?: () => void;
};

export function CitationList({
  sources,
  indexedDocuments,
  indexedLoading,
  messageId,
  onItemOpen,
}: CitationListProps) {
  const { factoryId, sessionId, machineId, onOpenDocument } = useChatSession();
  const showCited = sources.length > 0;

  if (showCited) {
    return (
      <>
        {sources.map((s, i) => {
          const locator = sourceLocator(s);
          const contextLabel = `${s.title ?? s.source_file ?? s.doc_id}${locator ? ` · ${locator}` : ""}`;
          const key = s.chunk_id ?? `${s.doc_id}-${s.page ?? s.source_sheet}-${s.row_number ?? i}`;
          return (
            <div
              key={key}
              className={cn(
                "p-3 rounded-xl gemini-theme-transition",
                "border border-gemini-border/70 dark:border-gemini-dark-border/70",
                "hover:bg-gemini-hover/50 dark:hover:bg-gemini-dark-hover/50"
              )}
            >
              <p className="text-sm text-gemini-text dark:text-gemini-dark-text truncate">
                {s.source_file ?? s.title ?? s.doc_id}
              </p>
              <div className="flex items-center gap-2 mt-1 text-[11px] text-gemini-muted dark:text-gemini-dark-muted">
                {locator && (
                  <span>
                    {s.page != null && s.can_view && s.doc_id && onOpenDocument ? (
                      <button
                        type="button"
                        className="inline-flex min-h-6 items-center rounded px-1 hover:text-gemini-blue dark:hover:text-gemini-dark-blue underline-offset-2 hover:underline gemini-focus-ring"
                        onClick={() => {
                          onOpenDocument(
                            s.doc_id!,
                            s.page ?? undefined,
                            s.title ?? s.source_file,
                            s.spans?.[0]?.text ?? undefined
                          );
                          onItemOpen?.();
                        }}
                      >
                        {locator}
                      </button>
                    ) : (
                      <>{locator}</>
                    )}
                  </span>
                )}
                {s.chunk_id && (
                  <span className="font-mono truncate max-w-[8rem]" title={s.chunk_id}>
                    chunk:{s.chunk_id.slice(0, 8)}…
                  </span>
                )}
                {s.needs_review && (
                  <span
                    className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300"
                    title="ตีความโดย AI จากภาพ ยังไม่ผ่านการตรวจสอบโดยมนุษย์"
                  >
                    ยังไม่ยืนยัน
                  </span>
                )}
                <span className="ml-auto text-gemini-blue dark:text-gemini-dark-blue tabular-nums">
                  {(s.score * 100).toFixed(0)}%
                </span>
              </div>
              <div className="mt-2 flex items-center gap-3 flex-wrap">
                {s.can_view && s.doc_id && onOpenDocument && (
                  <button
                    type="button"
                    onClick={() => {
                      onOpenDocument(
                        s.doc_id!,
                        s.page ?? undefined,
                        s.title ?? s.source_file,
                        s.spans?.[0]?.text ?? undefined
                      );
                      onItemOpen?.();
                    }}
                    className="inline-flex min-h-11 items-center rounded-lg px-2 text-xs font-medium text-gemini-blue dark:text-gemini-dark-blue hover:bg-gemini-hover/60 hover:underline dark:hover:bg-gemini-dark-hover/60 gemini-focus-ring"
                  >
                    เปิดเอกสาร
                  </button>
                )}
                {factoryId && s.doc_id && (
                  <FeedbackReportButton
                    compact
                    payload={{
                      factoryId,
                      sourceType: "rag_source",
                      docId: s.doc_id,
                      page: s.page ?? null,
                      sessionId,
                      messageId: messageId && isUuid(messageId) ? messageId : null,
                      machineId,
                      contextLabel,
                      contextSnapshot: {
                        doc_title: s.title ?? s.source_file,
                        page: s.page,
                        chunk_id: s.chunk_id,
                        source_sheet: s.source_sheet,
                        row_number: s.row_number,
                        score: s.score,
                      },
                    }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </>
    );
  }

  if (indexedLoading) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-8">
        {MSG_SOURCES_LOADING}
      </p>
    );
  }

  if (indexedDocuments.length === 0) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-8">
        {MSG_NO_INDEXED_DOCS}
      </p>
    );
  }

  return (
    <>
      <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted px-1 pb-1">
        {MSG_INDEXED_DOCS}
      </p>
      {indexedDocuments.map((doc) => (
        <div
          key={doc.doc_id}
          className={cn(
            "p-3 rounded-xl gemini-theme-transition",
            "border border-gemini-border/70 dark:border-gemini-dark-border/70",
            "hover:bg-gemini-hover/50 dark:hover:bg-gemini-dark-hover/50"
          )}
        >
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text truncate">
            {doc.title ?? doc.source_file ?? doc.doc_id}
          </p>
          <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-1">
            {doc.document_type.replace(/_/g, " ")}
            {doc.chunks_count > 0 && ` · ${doc.chunks_count} chunks`}
          </p>
        </div>
      ))}
    </>
  );
}
