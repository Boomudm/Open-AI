"use client";

import { AllDocumentsList } from "@/components/documents/AllDocumentsList";
import { DocumentsHubHero } from "@/components/documents/DocumentsHubHero";
import { CategoryCard } from "@/components/documents/CategoryCard";
import { CategoryDocumentList } from "@/components/documents/CategoryDocumentList";
import { CategoryCardSkeleton } from "@/components/documents/DocumentsHubSkeleton";
import { DocumentRow } from "@/components/documents/DocumentRow";
import { MachineGrid } from "@/components/documents/MachineGrid";
import { MachineLearningPage } from "@/components/documents/MachineLearningPage";
import { NoJobPositionBanner } from "@/components/documents/NoJobPositionBanner";
import type { IndexedDocument } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import {
  DOCUMENT_CATEGORY_META,
  HUB_CATEGORY_ORDER,
  INGEST_JOBS_HUB_META,
  MACHINES_HUB_META,
  type DocumentCategoryId,
  type HubCategoryId,
} from "@/lib/document-categories";
import {
  countByCategory,
  recentDocuments,
  routeBreadcrumb,
  searchDocumentsAndMachines,
  type DocumentsRoute,
} from "@/lib/documents-library";
import { useMachinesInfinite } from "@/hooks/useMachinesQuery";
import { useUiStore } from "@/stores/uiStore";
import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

export type DocumentsHubProps = {
  documents: IndexedDocument[];
  loading?: boolean;
  /** URL-controlled route (preferred for /documents). */
  route?: DocumentsRoute;
  onNavigate?: (route: DocumentsRoute) => void;
  initialRoute?: DocumentsRoute | null;
  initialDocId?: string | null;
  initialPage?: number;
  onRouteChange?: (route: DocumentsRoute) => void;
  onBreadcrumbChange?: (segments: string[], onBack?: () => void) => void;
  onOpenDoc: (doc: IndexedDocument, page?: number) => void;
  onAskAi?: (machineId: string) => void;
  onClearDeepLink?: () => void;
  fetchMachines?: boolean;
};

function hubBackTarget(route: DocumentsRoute): DocumentsRoute | null {
  switch (route.view) {
    case "hub":
      return null;
    case "machines":
    case "category":
    case "all":
    case "ingest_jobs":
      return { view: "hub" };
    case "machine":
      return { view: "machines" };
  }
}

export function DocumentsHub({
  documents,
  loading,
  route: controlledRoute,
  onNavigate,
  initialRoute,
  initialDocId,
  initialPage,
  onRouteChange,
  onBreadcrumbChange,
  onOpenDoc,
  onAskAi,
  onClearDeepLink,
  fetchMachines = true,
}: DocumentsHubProps) {
  const router = useRouter();
  const isControlled = controlledRoute !== undefined;
  const [internalRoute, setInternalRoute] = useState<DocumentsRoute>(
    () => controlledRoute ?? initialRoute ?? { view: "hub" }
  );
  const route = isControlled ? controlledRoute! : internalRoute;
  const [hubSearch, setHubSearch] = useState("");
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const showIngestJobsTab = canWriteFactory(selectedFactoryId);

  const { machines, isLoading: machinesLoading } = useMachinesInfinite("", {
    enabled: fetchMachines,
  });

  const navigate = useCallback(
    (next: DocumentsRoute) => {
      if (isControlled) onNavigate?.(next);
      else setInternalRoute(next);
      onRouteChange?.(next);
    },
    [isControlled, onNavigate, onRouteChange]
  );

  const goBack = useCallback(() => {
    const target = hubBackTarget(route);
    if (target) navigate(target);
  }, [route, navigate]);

  const goBackRef = useRef(goBack);
  goBackRef.current = goBack;
  const stableGoBack = useCallback(() => {
    goBackRef.current();
  }, []);

  const onBreadcrumbChangeRef = useRef(onBreadcrumbChange);
  onBreadcrumbChangeRef.current = onBreadcrumbChange;

  const breadcrumbSegments = useMemo(() => routeBreadcrumb(route), [route]);
  const breadcrumbBack = hubBackTarget(route) ? stableGoBack : undefined;

  useEffect(() => {
    onBreadcrumbChangeRef.current?.(breadcrumbSegments, breadcrumbBack);
  }, [breadcrumbSegments, breadcrumbBack]);

  const consumedDeepLinkRef = useRef<string | null>(null);

  useEffect(() => {
    if (!initialDocId || consumedDeepLinkRef.current === initialDocId) return;
    const match = documents.find((d) => d.doc_id === initialDocId);
    if (!match) return;
    consumedDeepLinkRef.current = initialDocId;
    if (match.machine_id) {
      navigate({ view: "machine", machineId: match.machine_id });
    }
    onOpenDoc(match, initialPage);
    onClearDeepLink?.();
  }, [initialDocId, initialPage, documents, navigate, onOpenDoc, onClearDeepLink]);

  const hubSearchResults = useMemo(() => {
    if (!hubSearch.trim() || route.view !== "hub") return null;
    return searchDocumentsAndMachines(documents, machines, hubSearch);
  }, [hubSearch, route.view, documents, machines]);

  const recent = useMemo(() => recentDocuments(documents, 5), [documents]);

  const selectedMachine = useMemo(() => {
    if (route.view !== "machine") return null;
    return machines.find((m) => m.machine_id === route.machineId) ?? null;
  }, [route, machines]);

  useEffect(() => {
    if (route.view === "ingest_jobs") {
      router.replace("/upload#jobs");
    }
  }, [route.view, router]);

  if (route.view === "ingest_jobs") {
    return (
      <p className="text-sm text-center text-gemini-muted py-12">
        กำลังไปหน้าอัปโหลด…
      </p>
    );
  }

  if (route.view === "all") {
    return (
      <AllDocumentsList
        documents={documents}
        loading={loading}
        onOpenDoc={(doc) => onOpenDoc(doc)}
      />
    );
  }

  if (route.view === "category") {
    return (
      <CategoryDocumentList
        category={route.category}
        documents={documents}
        loading={loading}
        onOpenDoc={(doc) => onOpenDoc(doc)}
      />
    );
  }

  if (route.view === "machines") {
    return (
      <MachineGrid
        machines={machines}
        documents={documents}
        loading={loading || machinesLoading}
        onSelectMachine={(id) => navigate({ view: "machine", machineId: id })}
      />
    );
  }

  if (route.view === "machine") {
    if (!selectedMachine) {
      return (
        <p className="text-sm text-center text-gemini-muted py-12">
          {machinesLoading ? "กำลังโหลดเครื่องจักร…" : "ไม่พบเครื่องจักร"}
        </p>
      );
    }
    return (
      <MachineLearningPage
        machine={selectedMachine}
        documents={documents}
        onOpenDoc={(doc) => onOpenDoc(doc)}
        onAskAi={onAskAi}
      />
    );
  }

  // Hub view
  return (
    <div data-testid="documents-hub" className="max-w-4xl mx-auto w-full space-y-6">
      <NoJobPositionBanner />
      <DocumentsHubHero
        documentCount={documents.length}
        machineCount={machines.length}
        showIngestJobs={showIngestJobsTab}
        onBrowseMachines={() => navigate({ view: "machines" })}
        onBrowseAll={() => navigate({ view: "all" })}
        onIngestJobs={() => router.push("/upload#jobs")}
      />
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gemini-muted" />
        <input
          type="search"
          value={hubSearch}
          onChange={(e) => setHubSearch(e.target.value)}
          placeholder="ค้นหาเอกสาร / เครื่องจักร…"
          className={cn(
            "w-full h-10 pl-9 pr-3 rounded-full text-sm",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/70 dark:border-gemini-dark-border/70",
            "text-gemini-text dark:text-gemini-dark-text"
          )}
        />
      </div>

      {hubSearchResults &&
        (hubSearchResults.documents.length > 0 || hubSearchResults.machines.length > 0) && (
          <div className="rounded-2xl border border-gemini-border/70 dark:border-gemini-dark-border/70 p-3 space-y-3">
            {hubSearchResults.machines.length > 0 && (
              <div>
                <p className="text-xs font-medium text-gemini-muted mb-2">เครื่องจักร</p>
                <div className="flex flex-wrap gap-2">
                  {hubSearchResults.machines.map((m) => (
                    <button
                      key={m.machine_id}
                      type="button"
                      onClick={() => navigate({ view: "machine", machineId: m.machine_id })}
                      className="text-xs px-3 py-1.5 rounded-full bg-gemini-hover dark:bg-gemini-dark-hover font-mono"
                    >
                      {m.machine_id} · {m.machine_name}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {hubSearchResults.documents.length > 0 && (
              <div className="grid gap-1">
                <p className="text-xs font-medium text-gemini-muted mb-1">เอกสาร</p>
                {hubSearchResults.documents.map((doc) => (
                  <DocumentRow key={doc.doc_id} doc={doc} onOpen={(d) => onOpenDoc(d)} />
                ))}
              </div>
            )}
          </div>
        )}

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CategoryCardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {HUB_CATEGORY_ORDER.map((id: HubCategoryId) => {
            if (id === "machines") {
              const meta = MACHINES_HUB_META;
              return (
                <CategoryCard
                  key={id}
                  icon={meta.icon}
                  label={meta.label}
                  description={meta.description}
                  countLabel={`${machines.length} เครื่อง`}
                  onClick={() => navigate({ view: "machines" })}
                />
              );
            }
            const meta = DOCUMENT_CATEGORY_META[id as DocumentCategoryId];
            const count = countByCategory(documents, id as DocumentCategoryId, true);
            return (
              <CategoryCard
                key={id}
                icon={meta.icon}
                label={meta.label}
                description={meta.description}
                countLabel={`${count} เอกสาร`}
                onClick={() => navigate({ view: "category", category: id as DocumentCategoryId })}
              />
            );
          })}
          {showIngestJobsTab && (
            <CategoryCard
              key="ingest_jobs"
              icon={INGEST_JOBS_HUB_META.icon}
              label={INGEST_JOBS_HUB_META.label}
              description={INGEST_JOBS_HUB_META.description}
              countLabel="ติดตามงาน"
              onClick={() => router.push("/upload#jobs")}
            />
          )}
        </div>
      )}

      {!loading && recent.length > 0 && (
        <section>
          <h2 className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text mb-2">
            อัปเดตล่าสุด
          </h2>
          <div className="grid gap-2">
            {recent.map((doc) => (
              <DocumentRow key={doc.doc_id} doc={doc} onOpen={(d) => onOpenDoc(d)} />
            ))}
          </div>
        </section>
      )}

      <button
        type="button"
        onClick={() => navigate({ view: "all" })}
        className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline"
      >
        ดูเอกสารทั้งหมด
      </button>
    </div>
  );
}
