"use client";

import { useFactoriesQuery } from "@/hooks/useFactoriesQuery";
import { useUiStore } from "@/stores/uiStore";
import { useEffect } from "react";

const DEFAULT_FACTORY_ID = "F-01";

/** Factory-scoped pages need one site selected — pick F-01 (or first) when admin is on "ทั้งหมด". */
export function useEnsureFactorySelected(): void {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const setSelectedFactoryId = useUiStore((s) => s.setSelectedFactoryId);
  const { data: factories = [], isSuccess } = useFactoriesQuery();

  useEffect(() => {
    if (selectedFactoryId || !isSuccess || factories.length === 0) return;
    const preferred =
      factories.find((f) => f.factory_id === DEFAULT_FACTORY_ID) ?? factories[0];
    setSelectedFactoryId(preferred.factory_id);
  }, [selectedFactoryId, isSuccess, factories, setSelectedFactoryId]);
}
