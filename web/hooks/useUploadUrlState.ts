"use client";

import { parseAsString, useQueryStates } from "nuqs";
import { useCallback, useEffect, useRef } from "react";
import { useUiStore } from "@/stores/uiStore";

export function useUploadUrlState() {
  const setSelectedMachineId = useUiStore((s) => s.setSelectedMachineId);
  const [raw, setRaw] = useQueryStates(
    { machine: parseAsString.withDefault("") },
    { history: "replace", shallow: true }
  );

  const machineInitRef = useRef(false);
  const machineId = (raw.machine ?? "").trim();

  useEffect(() => {
    if (machineInitRef.current) return;
    machineInitRef.current = true;
    if (machineId) {
      setSelectedMachineId(machineId);
      return;
    }
    const fromStore = useUiStore.getState().selectedMachineId;
    if (fromStore) {
      setRaw({ machine: fromStore });
      setSelectedMachineId(fromStore);
    }
  }, [machineId, setRaw, setSelectedMachineId]);

  const setMachineId = useCallback(
    (id: string | null) => setRaw({ machine: id || null }),
    [setRaw]
  );

  return {
    machineId: machineId || null,
    setMachineId,
  };
}
