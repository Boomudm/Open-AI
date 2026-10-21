"use client";

import { DocumentViewer } from "@/components/documents/DocumentViewer";
import { FeedbackInboxPanel } from "@/components/feedback/FeedbackInboxPanel";
import { useDocumentsLibrary } from "@/hooks/useDocumentsLibrary";
import { useEnsureFactorySelected } from "@/hooks/useEnsureFactorySelected";
import { useIndexedDocuments } from "@/hooks/useIndexedDocuments";
import { useUiStore } from "@/stores/uiStore";
import { useCallback, useState } from "react";

export default function FeedbackPage() {
  useEnsureFactorySelected();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const { data: libraryDocuments = [] } = useDocumentsLibrary();
  const { data: indexedDocuments = [] } = useIndexedDocuments(null);

  const [docViewer, setDocViewer] = useState<{
    docId: string;
    page?: number;
    title?: string | null;
    mimeType?: string | null;
    factoryId?: string | null;
    machineId?: string | null;
  } | null>(null);

  const handleOpenDocument = useCallback(
    (docId: string, page?: number, title?: string | null) => {
      const match =
        indexedDocuments.find((d) => d.doc_id === docId) ??
        libraryDocuments.find((d) => d.doc_id === docId);
      setDocViewer({
        docId,
        page,
        title: title ?? match?.title ?? match?.source_file,
        mimeType: match?.mime_type,
        factoryId: match?.factory_id ?? selectedFactoryId,
        machineId: match?.machine_id ?? null,
      });
    },
    [indexedDocuments, libraryDocuments, selectedFactoryId]
  );

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-gemini-border/50 dark:border-gemini-dark-border/50 bg-gemini-bg/90 dark:bg-gemini-dark-bg/90 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <h1 className="text-lg font-semibold text-gemini-text dark:text-gemini-dark-text">
            แจ้งกลับความรู้
          </h1>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
            ตรวจสอบและจัดการ feedback จากหน้างาน
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto w-full px-4 py-6">
        <FeedbackInboxPanel
          factoryId={selectedFactoryId}
          onOpenDocument={handleOpenDocument}
        />
      </main>

      {docViewer && (
        <DocumentViewer
          key={docViewer.docId}
          docId={docViewer.docId}
          title={docViewer.title}
          mimeType={docViewer.mimeType}
          initialPage={docViewer.page}
          factoryId={docViewer.factoryId}
          machineId={docViewer.machineId}
          onClose={() => setDocViewer(null)}
        />
      )}
    </>
  );
}
