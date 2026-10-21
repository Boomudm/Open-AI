"use client";

import { MachineCard } from "@/components/documents/MachineCard";
import { MachineCardSkeleton } from "@/components/documents/DocumentsHubSkeleton";
import type { IndexedDocument, Machine } from "@/lib/api";
import { cn } from "@/lib/cn";
import { countDocsPerMachine } from "@/lib/documents-library";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";

export type MachineGridProps = {
  machines: Machine[];
  documents: IndexedDocument[];
  loading?: boolean;
  onSelectMachine: (machineId: string) => void;
};

export function MachineGrid({
  machines,
  documents,
  loading,
  onSelectMachine,
}: MachineGridProps) {
  const [search, setSearch] = useState("");
  const docCounts = useMemo(() => countDocsPerMachine(documents), [documents]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return machines;
    return machines.filter(
      (m) =>
        m.machine_id.toLowerCase().includes(q) ||
        m.machine_name.toLowerCase().includes(q) ||
        (m.machine_type?.toLowerCase().includes(q) ?? false)
    );
  }, [machines, search]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-10 rounded-full bg-gemini-hover dark:bg-gemini-dark-hover animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <MachineCardSkeleton key={i} />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gemini-muted" />
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="ค้นหา MC-001, ชื่อเครื่อง…"
          className={cn(
            "w-full h-10 pl-9 pr-3 rounded-full text-sm",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/70 dark:border-gemini-dark-border/70",
            "text-gemini-text dark:text-gemini-dark-text"
          )}
        />
      </div>

      {filtered.length === 0 ? (
        <p className="text-sm text-center text-gemini-muted py-12">ไม่พบเครื่องจักร</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((m) => (
            <MachineCard
              key={m.machine_id}
              machine={m}
              docCount={docCounts.get(m.machine_id) ?? 0}
              onClick={() => onSelectMachine(m.machine_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
