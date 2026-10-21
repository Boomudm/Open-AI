"use client";

import { useUiStore } from "@/stores/uiStore";

/** Selected factory for API query params; undefined when "All" is selected. */
export function useFactoryIdParam(): string | undefined {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  return selectedFactoryId ?? undefined;
}
