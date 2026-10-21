"use client";

import { IngestForm } from "@/components/ingest/IngestForm";
import { canUploadDocuments } from "@/lib/auth";
import { cn } from "@/lib/cn";
import {
  filterTypesForCategory,
  resolveDefaultDocumentType,
} from "@/lib/ingest-defaults";
import type { DocumentCategoryId } from "@/lib/document-categories";
import { queryKeys } from "@/lib/query-keys";
import { useUiStore } from "@/stores/uiStore";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { useDocumentTypes } from "@/hooks/useDocumentTypes";

export type DocumentUploadPanelProps = {
  /** Collapsible section title */
  title?: string;
  defaultMachineId?: string;
  defaultOpen?: boolean;
  className?: string;
  factoryId?: string | null;
  /** Hub category — filters types and sets smart default. */
  documentCategory?: DocumentCategoryId;
  filterDocumentTypes?: string[];
  defaultDocumentType?: string;
};

export function DocumentUploadPanel({
  title = "อัปโหลดเอกสาร",
  defaultMachineId,
  defaultOpen = false,
  className,
  factoryId: factoryIdProp,
  documentCategory,
  filterDocumentTypes: filterDocumentTypesProp,
  defaultDocumentType: defaultDocumentTypeProp,
}: DocumentUploadPanelProps) {
  const queryClient = useQueryClient();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const factoryId = factoryIdProp ?? selectedFactoryId;
  const canUpload = canUploadDocuments(factoryId);
  const [open, setOpen] = useState(defaultOpen);
  const { documentTypes: allDocumentTypes } = useDocumentTypes();

  const filterDocumentTypes = useMemo(() => {
    if (filterDocumentTypesProp?.length) return filterDocumentTypesProp;
    if (!documentCategory) return undefined;
    return filterTypesForCategory(allDocumentTypes, documentCategory);
  }, [filterDocumentTypesProp, documentCategory, allDocumentTypes]);

  const defaultDocumentType = useMemo(() => {
    if (defaultDocumentTypeProp) return defaultDocumentTypeProp;
    const pool = filterDocumentTypes ?? allDocumentTypes;
    return resolveDefaultDocumentType({
      category: documentCategory,
      defaultMachineId,
      availableTypes: pool,
    });
  }, [
    defaultDocumentTypeProp,
    filterDocumentTypes,
    allDocumentTypes,
    documentCategory,
    defaultMachineId,
  ]);

  if (!canUpload) {
    return null;
  }

  const invalidateDocs = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents() });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({ queryKey: ["ingestJobs"] });
  };

  return (
    <div
      className={cn(
        "rounded-2xl border border-gemini-border/70 dark:border-gemini-dark-border/70 overflow-hidden",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "w-full flex items-center justify-between gap-2 px-4 py-3 text-sm font-medium",
          "hover:bg-gemini-hover/50 dark:hover:bg-gemini-dark-hover/50 gemini-theme-transition"
        )}
      >
        <span className="inline-flex items-center gap-2">
          <Upload className="h-4 w-4 text-gemini-blue dark:text-gemini-dark-blue" />
          {title}
        </span>
        {open ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-gemini-border/50 dark:border-gemini-dark-border/50 pt-4">
          <IngestForm
            embedded
            defaultMachineId={defaultMachineId}
            filterDocumentTypes={filterDocumentTypes}
            documentCategory={documentCategory}
            defaultDocumentType={defaultDocumentType}
            onSuccess={invalidateDocs}
          />
        </div>
      )}
    </div>
  );
}
