"use client";

import { DocumentRow } from "@/components/documents/DocumentRow";
import type { IndexedDocument } from "@/lib/api";
import { NoJobPositionBanner } from "@/components/documents/NoJobPositionBanner";
import { cn } from "@/lib/cn";
import { docDisplayLabel } from "@/lib/documents-library";
import { FileText, Search } from "lucide-react";
import { useMemo, useState } from "react";

export type AllDocumentsListProps = {
  documents: IndexedDocument[];
  loading?: boolean;
  onOpenDoc: (doc: IndexedDocument) => void;
};

export function AllDocumentsList({
  documents,
  loading,
  onOpenDoc,
}: AllDocumentsListProps) {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [ocrLowOnly, setOcrLowOnly] = useState(false);

  const types = useMemo(() => {
    const set = new Set(documents.map((d) => d.document_type));
    return Array.from(set).sort();
  }, [documents]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return documents.filter((d) => {
      if (typeFilter && d.document_type !== typeFilter) return false;
      if (ocrLowOnly) {
        const ocrMin = d.extra_metadata?.ocr_confidence_min;
        if (ocrMin == null || Number(ocrMin) >= 70) return false;
      }
      if (!q) return true;
      return docDisplayLabel(d).toLowerCase().includes(q);
    });
  }, [documents, search, typeFilter, ocrLowOnly]);

  if (loading) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-12">
        กำลังโหลดเอกสาร…
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <NoJobPositionBanner />
      <h2 className="text-base font-semibold text-gemini-text dark:text-gemini-dark-text">
        เอกสารทั้งหมด ({documents.length})
      </h2>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gemini-muted dark:text-gemini-dark-muted" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ค้นหาเอกสาร…"
            className={cn(
              "w-full h-10 pl-9 pr-3 rounded-full text-sm gemini-theme-transition",
              "bg-gemini-surface dark:bg-gemini-dark-surface",
              "border border-gemini-border/70 dark:border-gemini-dark-border/70",
              "text-gemini-text dark:text-gemini-dark-text"
            )}
          />
        </div>
        {types.length > 0 && (
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className={cn(
              "h-10 px-3 rounded-full text-sm min-w-[10rem]",
              "bg-gemini-surface dark:bg-gemini-dark-surface",
              "border border-gemini-border/70 dark:border-gemini-dark-border/70",
              "text-gemini-text dark:text-gemini-dark-text"
            )}
            aria-label="กรองตามประเภทเอกสาร"
          >
            <option value="">ทุกประเภท</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        )}
        <label className="flex items-center gap-2 h-10 px-3 rounded-full text-sm border border-gemini-border/70 dark:border-gemini-dark-border/70 cursor-pointer">
          <input
            type="checkbox"
            checked={ocrLowOnly}
            onChange={(e) => setOcrLowOnly(e.target.checked)}
          />
          OCR ต่ำ (&lt;70%)
        </label>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center py-16 text-center">
          <FileText className="h-10 w-10 text-gemini-muted mb-3" />
          <p className="text-sm text-gemini-muted">
            {documents.length === 0
              ? "ยังไม่มีเอกสาร"
              : "ไม่พบเอกสารที่ตรงกับการค้นหา"}
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
