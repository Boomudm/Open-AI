"use client";

import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { DEBOUNCE_MS } from "@/lib/query-config";
import type { Machine } from "@/lib/api";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, Search, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { SkeletonText } from "./SkeletonLoader";

export type MachineSelectorProps = {
  machines: Machine[];
  value: string | null;
  onChange: (machineId: string | null) => void;
  isLoading?: boolean;
  placeholder?: string;
  className?: string;
  triggerClassName?: string;
  /** Open dropdown above trigger (for bottom input bars) */
  dropdownPlacement?: "top" | "bottom";
  /** Show only machine ID in trigger label */
  compact?: boolean;
  /** Fetch more when user scrolls near end */
  onLoadMore?: () => void;
  hasMore?: boolean;
  /** Server-side search: parent supplies filtered machines */
  serverSearch?: boolean;
  searchQuery?: string;
  onSearchQueryChange?: (query: string) => void;
};

type GroupedMachines = {
  factoryId: string;
  machines: Machine[];
};

function groupByFactory(machines: Machine[]): GroupedMachines[] {
  const map = new Map<string, Machine[]>();
  for (const m of machines) {
    const list = map.get(m.factory_id) ?? [];
    list.push(m);
    map.set(m.factory_id, list);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([factoryId, items]) => ({
      factoryId,
      machines: items.sort((a, b) => a.machine_id.localeCompare(b.machine_id)),
    }));
}

type FlatItem =
  | { type: "header"; factoryId: string }
  | { type: "machine"; machine: Machine };

function flattenGroups(groups: GroupedMachines[]): FlatItem[] {
  const out: FlatItem[] = [];
  for (const g of groups) {
    out.push({ type: "header", factoryId: g.factoryId });
    for (const m of g.machines) {
      out.push({ type: "machine", machine: m });
    }
  }
  return out;
}

export function MachineSelector({
  machines,
  value,
  onChange,
  isLoading,
  placeholder = "เลือกเครื่องจักร…",
  className,
  triggerClassName,
  dropdownPlacement = "bottom",
  compact = false,
  onLoadMore,
  hasMore,
  serverSearch = false,
  searchQuery: controlledQuery,
  onSearchQueryChange,
}: MachineSelectorProps) {
  const [open, setOpen] = useState(false);
  const [localQuery, setLocalQuery] = useState("");
  const query = controlledQuery ?? localQuery;
  const debouncedQuery = useDebouncedValue(query, serverSearch ? 0 : DEBOUNCE_MS);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  const selected = useMemo(
    () => machines.find((m) => m.machine_id === value) ?? null,
    [machines, value]
  );

  const filtered = useMemo(() => {
    if (serverSearch) return machines;
    const q = debouncedQuery.trim().toLowerCase();
    if (!q) return machines;
    return machines.filter(
      (m) =>
        m.machine_id.toLowerCase().includes(q) ||
        m.machine_name.toLowerCase().includes(q) ||
        (m.machine_type?.toLowerCase().includes(q) ?? false) ||
        m.factory_id.toLowerCase().includes(q)
    );
  }, [machines, debouncedQuery, serverSearch]);

  const setQuery = useCallback(
    (next: string) => {
      if (onSearchQueryChange) onSearchQueryChange(next);
      else setLocalQuery(next);
    },
    [onSearchQueryChange]
  );

  const flatItems = useMemo(
    () => flattenGroups(groupByFactory(filtered)),
    [filtered]
  );

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => listRef.current,
    // Two-line rows need ~52px; 36px caused text to spill and overlap adjacent rows.
    estimateSize: (index) => (flatItems[index]?.type === "header" ? 32 : 52),
    overscan: 12,
  });

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const closeAndRestoreFocus = useCallback(() => {
    setOpen(false);
    window.setTimeout(() => triggerRef.current?.focus(), 0);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeAndRestoreFocus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [closeAndRestoreFocus, open]);

  const handleScroll = useCallback(() => {
    if (!listRef.current || !onLoadMore || !hasMore) return;
    const { scrollTop, scrollHeight, clientHeight } = listRef.current;
    if (scrollHeight - scrollTop - clientHeight < 80) {
      onLoadMore();
    }
  }, [onLoadMore, hasMore]);

  const selectMachine = useCallback(
    (machineId: string | null) => {
      onChange(machineId);
      setOpen(false);
      setQuery("");
    },
    [onChange, setQuery]
  );

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key !== "ArrowDown") return;
          event.preventDefault();
          setOpen(true);
          window.setTimeout(() => searchRef.current?.focus(), 0);
        }}
        className={cn(
          "flex items-center justify-between gap-2 w-full h-9 px-2.5",
          "font-mono text-sm rounded-sm border border-spark-border",
          "bg-spark-elevated text-spark-text-primary hover:border-spark-border-strong",
          "spark-focus-ring transition-colors",
          triggerClassName
        )}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listboxId : undefined}
        aria-label={
          selected
            ? `เครื่องจักรที่เลือก ${selected.machine_id} ${selected.machine_name}`
            : placeholder
        }
      >
        <span className="truncate tabular-nums">
          {selected
            ? compact
              ? selected.machine_id
              : `${selected.machine_id} · ${selected.machine_name}`
            : value
              ? value
              : placeholder}
        </span>
        <ChevronDown className={cn("h-3.5 w-3.5 shrink-0", triggerClassName ? "text-current opacity-60" : "text-spark-text-muted")} />
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-50 min-w-[280px] max-w-[min(100vw-2rem,360px)]",
            dropdownPlacement === "top" ? "bottom-full mb-2 right-0" : "mt-1 left-0",
            "rounded-2xl overflow-hidden",
            "bg-gemini-bg dark:bg-gemini-dark-surface",
            "border border-gemini-border/60 dark:border-gemini-dark-border/60",
            "shadow-xl dark:shadow-2xl"
          )}
        >
          <div className="p-2.5 border-b border-gemini-border/40 dark:border-gemini-dark-border/40">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gemini-muted dark:text-gemini-dark-muted" />
              <input
                ref={searchRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="ค้นหาเครื่องจักร…"
                className={cn(
                  "w-full h-9 pl-9 pr-8 rounded-full text-sm",
                  "bg-gemini-surface dark:bg-gemini-dark-hover",
                  "text-gemini-text dark:text-gemini-dark-text",
                  "placeholder:text-gemini-muted dark:placeholder:text-gemini-dark-muted",
                  "focus:outline-none focus:ring-1 focus:ring-gemini-blue/30 dark:focus:ring-gemini-dark-blue/30",
                  "transition-colors"
                )}
                autoFocus
                aria-label="ค้นหาเครื่องจักร"
              />
              {query && (
                <Tooltip content="ล้างคำค้นหา">
                  <button
                    type="button"
                    onClick={() => setQuery("")}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gemini-muted dark:text-gemini-dark-muted hover:text-gemini-text dark:hover:text-gemini-dark-text"
                    aria-label="ล้างคำค้นหา"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </Tooltip>
              )}
            </div>
          </div>

          {isLoading ? (
            <div className="p-3">
              <SkeletonText lines={3} />
            </div>
          ) : flatItems.length === 0 ? (
            <p className="p-3 text-xs text-gemini-muted dark:text-gemini-dark-muted">ไม่พบเครื่องจักร</p>
          ) : (
            <div
              id={listboxId}
              ref={listRef}
              className="max-h-64 overflow-auto gemini-scrollbar"
              onScroll={handleScroll}
              role="listbox"
              aria-label="รายการเครื่องจักร"
            >
              <div
                style={{
                  height: `${virtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {virtualizer.getVirtualItems().map((vRow) => {
                  const item = flatItems[vRow.index];
                  if (item.type === "header") {
                    return (
                      <div
                        key={`h-${item.factoryId}`}
                        style={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          width: "100%",
                          height: `${vRow.size}px`,
                          transform: `translateY(${vRow.start}px)`,
                        }}
                        className="px-3 py-1.5 text-[10px] uppercase tracking-wider text-gemini-muted dark:text-gemini-dark-muted bg-gemini-surface/50 dark:bg-gemini-dark-hover/50"
                        role="presentation"
                      >
                        โรงงาน {item.factoryId}
                      </div>
                    );
                  }
                  const m = item.machine;
                  const active = m.machine_id === value;
                  return (
                    <button
                      key={m.machine_id}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => selectMachine(m.machine_id)}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: `${vRow.size}px`,
                        transform: `translateY(${vRow.start}px)`,
                      }}
                      className={cn(
                        "flex flex-col items-start justify-center w-full px-3 text-left overflow-hidden",
                        "text-xs transition-colors",
                        active
                          ? "bg-gemini-blue/10 dark:bg-gemini-dark-blue/15 text-gemini-blue dark:text-gemini-dark-blue"
                          : "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-gemini-text dark:text-gemini-dark-text"
                      )}
                    >
                      <span className="tabular-nums font-medium leading-tight font-mono">{m.machine_id}</span>
                      <span className="text-[10px] leading-snug text-gemini-muted dark:text-gemini-dark-muted truncate w-full">
                        {m.machine_name}
                        {m.machine_type ? ` · ${m.machine_type}` : ""}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {value && (
            <div className="p-1.5 border-t border-gemini-border/40 dark:border-gemini-dark-border/40">
              <button
                type="button"
                onClick={() => selectMachine(null)}
                className="w-full px-3 py-2 text-xs text-gemini-muted dark:text-gemini-dark-muted hover:text-gemini-blue dark:hover:text-gemini-dark-blue hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover rounded-full transition-colors"
              >
                ล้างการเลือก
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
