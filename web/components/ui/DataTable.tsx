"use client";

import { cn } from "@/lib/cn";
import { DEFAULT_PAGE_SIZE, paginationRange, type Paginated } from "@/lib/types/pagination";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronDown, ChevronUp, Columns3 } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "./Button";
import { EmptyState, ErrorState } from "./State";
import { SkeletonTable } from "./SkeletonLoader";

export type SortDirection = "asc" | "desc";

export type DataTableColumn<T> = {
  id: string;
  header: string;
  accessor: (row: T) => ReactNode;
  sortable?: boolean;
  width?: number | string;
  className?: string;
  defaultVisible?: boolean;
};

export type DataTableProps<T> = {
  columns: DataTableColumn<T>[];
  data: Paginated<T> | undefined;
  isLoading?: boolean;
  isError?: boolean;
  errorMessage?: string;
  onRetry?: () => void;
  page: number;
  pageSize?: number;
  onPageChange: (page: number) => void;
  sortColumn?: string;
  sortDirection?: SortDirection;
  onSort?: (columnId: string, direction: SortDirection) => void;
  rowKey: (row: T) => string;
  getRowClassName?: (row: T) => string | undefined;
  virtualizeThreshold?: number;
  rowHeight?: number;
  className?: string;
  toolbar?: ReactNode;
  emptyTitle?: string;
  emptyMessage?: string;
};

export function DataTable<T>({
  columns,
  data,
  isLoading,
  isError,
  errorMessage,
  onRetry,
  page,
  pageSize = DEFAULT_PAGE_SIZE,
  onPageChange,
  sortColumn,
  sortDirection = "desc",
  onSort,
  rowKey,
  getRowClassName,
  virtualizeThreshold = 200,
  rowHeight = 40,
  className,
  toolbar,
  emptyTitle = "No rows",
  emptyMessage = "Try adjusting your filters",
}: DataTableProps<T>) {
  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() =>
    new Set(columns.filter((c) => c.defaultVisible !== false).map((c) => c.id))
  );
  const [showColumnMenu, setShowColumnMenu] = useState(false);
  const parentRef = useRef<HTMLDivElement>(null);
  const columnMenuRef = useRef<HTMLDivElement>(null);
  const columnToggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!showColumnMenu) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setShowColumnMenu(false);
        columnToggleRef.current?.focus();
      }
    }
    function onPointerDown(e: MouseEvent) {
      const target = e.target as Node;
      if (
        columnMenuRef.current?.contains(target) ||
        columnToggleRef.current?.contains(target)
      ) {
        return;
      }
      setShowColumnMenu(false);
    }
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("mousedown", onPointerDown);
    columnMenuRef.current?.querySelector<HTMLElement>("input")?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("mousedown", onPointerDown);
    };
  }, [showColumnMenu]);

  useEffect(() => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const col of columns) {
        if (col.defaultVisible === false) continue;
        if (!next.has(col.id)) {
          next.add(col.id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [columns]);

  const activeColumns = useMemo(
    () => columns.filter((c) => visibleColumns.has(c.id)),
    [columns, visibleColumns]
  );

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const { start, end } = paginationRange(page, pageSize, total);
  const useVirtual = rows.length > virtualizeThreshold;

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => rowHeight,
    overscan: 10,
    enabled: useVirtual,
  });

  const handleSort = useCallback(
    (columnId: string) => {
      if (!onSort) return;
      const nextDir =
        sortColumn === columnId && sortDirection === "asc" ? "desc" : "asc";
      onSort(columnId, nextDir);
    },
    [onSort, sortColumn, sortDirection]
  );

  const toggleColumn = useCallback((id: string) => {
    setVisibleColumns((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        if (next.size > 1) next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  if (isLoading) {
    return <SkeletonTable className={className} />;
  }

  if (isError) {
    return (
      <ErrorState
        message={errorMessage}
        onRetry={onRetry}
        className={className}
      />
    );
  }

  if (total === 0) {
    return (
      <div className={cn("border border-spark-border rounded-sm bg-spark-surface", className)}>
        {toolbar && (
          <div className="px-3 py-2 border-b border-spark-border bg-spark-elevated">{toolbar}</div>
        )}
        <EmptyState title={emptyTitle} message={emptyMessage} className="py-12" />
      </div>
    );
  }

  const renderRow = (row: T) => (
    <tr
      key={rowKey(row)}
      className={cn(
        "border-b border-spark-border hover:bg-spark-hover/50 transition-colors",
        getRowClassName?.(row)
      )}
    >
      {activeColumns.map((col) => (
        <td
          key={col.id}
          className={cn(
            "px-3 py-2 text-sm font-sans text-spark-text-primary tabular-nums align-middle",
            col.className
          )}
          style={col.width ? { width: col.width } : undefined}
        >
          {col.accessor(row)}
        </td>
      ))}
    </tr>
  );

  return (
    <div className={cn("border border-spark-border rounded-sm bg-spark-surface", className)}>
      {(toolbar || columns.length > 1) && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-spark-border bg-spark-elevated">
          {toolbar ?? <span />}
          <div className="relative">
            <Button
              ref={columnToggleRef}
              variant="ghost"
              size="sm"
              onClick={() => setShowColumnMenu((v) => !v)}
              aria-expanded={showColumnMenu}
              aria-haspopup="true"
              leftIcon={<Columns3 className="h-3.5 w-3.5" />}
            >
              Columns
            </Button>
            {showColumnMenu && (
              <div
                ref={columnMenuRef}
                role="menu"
                aria-label="Toggle columns"
                className="absolute right-0 top-full mt-1 z-20 min-w-[160px] border border-spark-border rounded-sm bg-spark-surface shadow-none py-1"
              >
                {columns.map((col) => (
                  <label
                    key={col.id}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono text-spark-text-secondary hover:bg-spark-hover cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={visibleColumns.has(col.id)}
                      onChange={() => toggleColumn(col.id)}
                      className="accent-spark-accent"
                    />
                    {col.header}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div
        ref={useVirtual ? parentRef : undefined}
        className={cn("overflow-x-auto", useVirtual && "max-h-[520px] overflow-y-auto")}
      >
        <table className="w-full border-collapse">
          <thead className="sticky top-0 z-10 bg-spark-elevated">
            <tr className="border-b border-spark-border">
              {activeColumns.map((col) => (
                <th
                  key={col.id}
                  className={cn(
                    "px-3 py-2 text-left text-[10px] font-mono uppercase tracking-wider text-spark-text-muted",
                    col.className
                  )}
                  style={col.width ? { width: col.width } : undefined}
                  aria-sort={
                    col.sortable && sortColumn === col.id
                      ? sortDirection === "asc"
                        ? "ascending"
                        : "descending"
                      : undefined
                  }
                >
                  {col.sortable && onSort ? (
                    <button
                      type="button"
                      onClick={() => handleSort(col.id)}
                      className="inline-flex items-center gap-1 hover:text-spark-accent spark-focus-ring rounded-sm"
                    >
                      {col.header}
                      {sortColumn === col.id &&
                        (sortDirection === "asc" ? (
                          <ChevronUp className="h-3 w-3" />
                        ) : (
                          <ChevronDown className="h-3 w-3" />
                        ))}
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              ))}
            </tr>
          </thead>
          {useVirtual ? (
            <tbody
              style={{
                height: `${virtualizer.getTotalSize()}px`,
                position: "relative",
                display: "block",
              }}
            >
              {virtualizer.getVirtualItems().map((vRow) => {
                const row = rows[vRow.index];
                return (
                  <tr
                    key={rowKey(row)}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      transform: `translateY(${vRow.start}px)`,
                      display: "table",
                      tableLayout: "fixed",
                    }}
                    className={cn(
                      "border-b border-spark-border hover:bg-spark-hover/50",
                      getRowClassName?.(row)
                    )}
                  >
                    {activeColumns.map((col) => (
                      <td
                        key={col.id}
                        className={cn(
                          "px-3 py-2 text-sm font-sans text-spark-text-primary tabular-nums",
                          col.className
                        )}
                      >
                        {col.accessor(row)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          ) : (
            <tbody>{rows.map(renderRow)}</tbody>
          )}
        </table>
      </div>

      <div className="flex items-center justify-between gap-3 px-3 py-2 border-t border-spark-border text-xs font-mono text-spark-text-secondary">
        <span className="tabular-nums">
          {total === 0 ? "0 rows" : `${start}–${end} of ${total}`}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Prev
          </Button>
          <span className="tabular-nums">
            Page {page} / {totalPages}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
