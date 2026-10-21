"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

type UiState = {
  sidebarExpanded: boolean;
  selectedFactoryId: string | null;
  /** Factories chosen at login (non-admin); scopes the in-app factory switcher. */
  selectedFactoryIds: string[];
  selectedMachineId: string | null;
  setSidebarExpanded: (expanded: boolean) => void;
  setSelectedFactoryId: (factoryId: string | null) => void;
  setSelectedFactoryIds: (factoryIds: string[]) => void;
  setSelectedMachineId: (machineId: string | null) => void;
  resetSession: () => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarExpanded: true,
      selectedFactoryId: null,
      selectedFactoryIds: [],
      selectedMachineId: null,
      setSidebarExpanded: (sidebarExpanded) => set({ sidebarExpanded }),
      setSelectedFactoryId: (selectedFactoryId) => set({ selectedFactoryId }),
      setSelectedFactoryIds: (selectedFactoryIds) => set({ selectedFactoryIds }),
      setSelectedMachineId: (selectedMachineId) => set({ selectedMachineId }),
      resetSession: () =>
        set({ selectedFactoryId: null, selectedFactoryIds: [], selectedMachineId: null }),
    }),
    {
      name: "spark-ui",
      partialize: (s) => ({
        sidebarExpanded: s.sidebarExpanded,
        selectedFactoryId: s.selectedFactoryId,
        selectedFactoryIds: s.selectedFactoryIds,
        selectedMachineId: s.selectedMachineId,
      }),
    }
  )
);
