"use client";

import type { DocumentCategoryId } from "@/lib/document-categories";
import type { DocumentsRoute } from "@/lib/documents-library";
import { parseAsString, useQueryStates } from "nuqs";
import { useCallback, useEffect, useMemo } from "react";
import { useUiStore } from "@/stores/uiStore";

const CATEGORY_IDS: DocumentCategoryId[] = [
  "knowledge",
  "maintenance",
  "compliance",
  "inspection",
  "inventory",
  "enterprise",
];

function isCategoryId(value: string): value is DocumentCategoryId {
  return (CATEGORY_IDS as string[]).includes(value);
}

function routeFromParams(
  view: string,
  machine: string,
  category: string
): DocumentsRoute {
  if (view === "machines") return { view: "machines" };
  if (view === "machine" && machine) return { view: "machine", machineId: machine };
  if (view === "category" && category && isCategoryId(category)) {
    return { view: "category", category };
  }
  if (view === "all") return { view: "all" };
  return { view: "hub" };
}

export function useDocumentsUrlState() {
  const setSelectedMachineId = useUiStore((s) => s.setSelectedMachineId);
  const [raw, setRaw] = useQueryStates(
    {
      view: parseAsString.withDefault("hub"),
      machine: parseAsString.withDefault(""),
      category: parseAsString.withDefault(""),
      doc: parseAsString.withDefault(""),
      page: parseAsString.withDefault(""),
    },
    { history: "push", shallow: true }
  );

  const machineId = (raw.machine ?? "").trim();
  const deepLinkDocId = (raw.doc ?? "").trim() || null;
  const initialPage = raw.page ? Number.parseInt(raw.page, 10) : undefined;

  const route = useMemo(
    () => routeFromParams(raw.view ?? "hub", machineId, (raw.category ?? "").trim()),
    [raw.view, machineId, raw.category]
  );

  useEffect(() => {
    if (machineId) setSelectedMachineId(machineId);
  }, [machineId, setSelectedMachineId]);

  const setRoute = useCallback(
    (next: DocumentsRoute) => {
      switch (next.view) {
        case "hub":
          setRaw({ view: "hub", machine: null, category: null });
          break;
        case "machines":
          setRaw({ view: "machines", machine: null, category: null });
          break;
        case "machine":
          setRaw({ view: "machine", machine: next.machineId, category: null });
          break;
        case "category":
          setRaw({ view: "category", category: next.category, machine: null });
          break;
        case "all":
          setRaw({ view: "all", machine: null, category: null });
          break;
        case "ingest_jobs":
          break;
      }
    },
    [setRaw]
  );

  const clearDeepLinkDoc = useCallback(() => setRaw({ doc: null, page: null }), [setRaw]);

  return {
    route,
    machineId: machineId || null,
    deepLinkDocId,
    initialPage: Number.isFinite(initialPage) ? initialPage : undefined,
    setRoute,
    clearDeepLinkDoc,
  };
}
