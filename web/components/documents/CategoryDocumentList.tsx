"use client";

import { DocumentRow } from "@/components/documents/DocumentRow";
import { DocumentUploadPanel } from "@/components/documents/DocumentUploadPanel";
import type { IndexedDocument } from "@/lib/api";
import {
  DOCUMENT_CATEGORY_META,
  type DocumentCategoryId,
} from "@/lib/document-categories";
import { filterCategoryDocuments } from "@/lib/documents-library";
import { FileText } from "lucide-react";
import { useMemo } from "react";

export type CategoryDocumentListProps = {
  category: DocumentCategoryId;
  documents: IndexedDocument[];
  loading?: boolean;
  onOpenDoc: (doc: IndexedDocument) => void;
};

export function CategoryDocumentList({
  category,
  documents,
  loading,
  onOpenDoc,
}: CategoryDocumentListProps) {
  const meta = DOCUMENT_CATEGORY_META[category];
  const filtered = useMemo(
    () => filterCategoryDocuments(documents, category, true),
    [documents, category]
  );

  if (loading) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-12">
        กำลังโหลด…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <DocumentUploadPanel title={`อัปโหลดเอกสาร — ${meta.label}`} documentCategory={category} />
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted">
        {meta.description}
      </p>
      {filtered.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-center">
          <FileText className="h-10 w-10 text-gemini-muted mb-3" />
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
            ยังไม่มีเอกสารในหมวดนี้
          </p>
          <p className="text-xs text-gemini-muted mt-1 max-w-xs">
            ใช้ปุ่มอัปโหลดด้านบนเพื่อเพิ่มเอกสารในหมวดนี้
          </p>
        </div>
      ) : (
        <div className="grid gap-2">
          {filtered.map((doc) => (
            <DocumentRow key={doc.doc_id} doc={doc} onOpen={onOpenDoc} />
          ))}
        </div>
      )}
    </div>
  );
}
