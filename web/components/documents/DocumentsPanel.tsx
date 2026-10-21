"use client";

import { DocumentViewer } from "@/components/documents/DocumentViewer";
import { DocumentsHub } from "@/components/documents/DocumentsHub";
import type { IndexedDocument } from "@/lib/api";
import type { DocumentsRoute } from "@/lib/documents-library";
import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export type DocumentsPanelProps = {
  documents: IndexedDocument[];
  loading?: boolean;
  route?: DocumentsRoute;
  onNavigate?: (route: DocumentsRoute) => void;
  initialRoute?: DocumentsRoute | null;
  initialDocId?: string | null;
  initialPage?: number;
  onRouteChange?: (route: DocumentsRoute) => void;
  onBreadcrumbChange?: (segments: string[], onBack?: () => void) => void;
  onAskAi?: (machineId: string) => void;
  onClearDeepLink?: () => void;
  /** When false, DocumentsHub skips its own machines query (unused in standalone /documents). */
  fetchMachines?: boolean;
};

export function DocumentsPanel({
  documents,
  loading,
  route,
  onNavigate,
  initialRoute,
  initialDocId,
  initialPage,
  onRouteChange,
  onBreadcrumbChange,
  onAskAi,
  onClearDeepLink,
  fetchMachines = true,
}: DocumentsPanelProps) {
  const [viewer, setViewer] = useState<{
    docId: string;
    title?: string | null;
    mimeType?: string | null;
    page?: number;
  } | null>(null);

  const pathname = usePathname();

  const openDoc = useCallback((doc: IndexedDocument, page?: number) => {
    setViewer({
      docId: doc.doc_id,
      title: doc.title ?? doc.original_filename ?? doc.source_file,
      mimeType: doc.mime_type,
      page,
    });
  }, []);

  useEffect(() => {
    setViewer(null);
  }, [pathname]);

  return (
    <>
      <DocumentsHub
        documents={documents}
        loading={loading}
        route={route}
        onNavigate={onNavigate}
        initialRoute={initialRoute}
        initialDocId={initialDocId}
        initialPage={initialPage}
        onRouteChange={onRouteChange}
        onBreadcrumbChange={onBreadcrumbChange}
        onOpenDoc={openDoc}
        onAskAi={onAskAi}
        onClearDeepLink={onClearDeepLink}
        fetchMachines={fetchMachines}
      />
      {viewer && (
        <DocumentViewer
          key={viewer.docId}
          docId={viewer.docId}
          title={viewer.title}
          mimeType={viewer.mimeType}
          initialPage={viewer.page}
          onClose={() => setViewer(null)}
        />
      )}
    </>
  );
}
