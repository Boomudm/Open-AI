"use client";

import { DocumentsPanel } from "@/components/documents/DocumentsPanel";
import { DocumentsBreadcrumb } from "@/components/documents/DocumentsBreadcrumb";
import { UploadDocumentButton } from "@/components/documents/UploadDocumentButton";
import { FactorySwitcher } from "@/components/layout/FactorySwitcher";
import { Button } from "@/components/ui/Button";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { EmptyState } from "@/components/ui/State";
import { useDocumentsLibrary } from "@/hooks/useDocumentsLibrary";
import { useDocumentsUrlState } from "@/hooks/useDocumentsUrlState";
import { useEnsureFactorySelected } from "@/hooks/useEnsureFactorySelected";
import { useIsDesktopNav } from "@/hooks/useMediaQuery";
import { useUiStore } from "@/stores/uiStore";
import type { IndexedDocument } from "@/lib/api";
import { Suspense, useCallback, useState } from "react";

function DocumentsContent() {
  const desktop = useIsDesktopNav();
  useEnsureFactorySelected();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const library = useDocumentsLibrary();
  const { route, machineId, deepLinkDocId, initialPage, setRoute, clearDeepLinkDoc } =
    useDocumentsUrlState();

  const [documentsBreadcrumb, setDocumentsBreadcrumb] = useState<{
    segments: string[];
    onBack?: () => void;
  }>({ segments: ["คลังเอกสาร"] });

  const handleBreadcrumbChange = useCallback(
    (segments: string[], onBack?: () => void) => {
      setDocumentsBreadcrumb((prev) => {
        if (
          prev.onBack === onBack &&
          prev.segments.length === segments.length &&
          prev.segments.every((s, i) => s === segments[i])
        ) {
          return prev;
        }
        return { segments, onBack };
      });
    },
    []
  );

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-gemini-border/50 dark:border-gemini-dark-border/50 bg-gemini-bg/90 dark:bg-gemini-dark-bg/90 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center gap-3">
          <DocumentsBreadcrumb
            segments={documentsBreadcrumb.segments}
            onBack={documentsBreadcrumb.onBack}
            className="flex-1 min-w-0"
          />
          <UploadDocumentButton variant="header" defaultMachineId={machineId ?? undefined} />
        </div>
      </header>

      <main className="max-w-5xl mx-auto w-full px-4 py-6">
        {!selectedFactoryId ? (
          <EmptyState
            title="เลือกโรงงานก่อน"
            message={
              desktop
                ? "เลือกโรงงานจากแถบด้านซ้ายเพื่อดูคู่มือและเอกสารในโรงงานนั้น"
                : "เลือกโรงงานด้านล่างเพื่อดูคู่มือและเอกสาร"
            }
            className="py-16 border-0 bg-transparent"
          >
            {!desktop && (
              <div className="mt-4 max-w-xs mx-auto">
                <FactorySwitcher expanded className="!px-0" />
              </div>
            )}
          </EmptyState>
        ) : (
          <QueryBoundary<IndexedDocument[]>
            query={{
              isLoading: library.isLoading,
              isError: library.isError,
              error: library.error,
              refetch: () => void library.refetch(),
              data: library.data,
            }}
            loadingMessage="กำลังโหลดคลังเอกสาร…"
            errorTitle="โหลดคลังเอกสารไม่สำเร็จ"
            className="py-16 border-0 bg-transparent"
          >
            {(documents) => (
              <>
                <DocumentsPanel
                  documents={documents}
                  loading={library.isFetching && !library.isLoading}
                  route={route}
                  onNavigate={setRoute}
                  initialDocId={deepLinkDocId}
                  initialPage={initialPage}
                  onBreadcrumbChange={handleBreadcrumbChange}
                  onClearDeepLink={clearDeepLinkDoc}
                />
                {library.hasMore && (
                  <div className="mt-6 flex flex-col items-center gap-2">
                    <p className="text-xs text-gemini-muted">
                      แสดง {documents.length} จาก {library.total} เอกสาร
                    </p>
                    <Button
                      type="button"
                      variant="secondary"
                      loading={library.isFetchingMore}
                      onClick={() => library.loadMore()}
                    >
                      โหลดเพิ่ม
                    </Button>
                  </div>
                )}
              </>
            )}
          </QueryBoundary>
        )}
      </main>
    </>
  );
}

export default function DocumentsPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[40vh] text-sm text-gemini-muted">
          กำลังโหลดคลังเอกสาร…
        </div>
      }
    >
      <DocumentsContent />
    </Suspense>
  );
}
