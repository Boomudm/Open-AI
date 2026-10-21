"use client";

import { cn } from "@/lib/cn";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useRef, type ReactNode } from "react";

export type VirtualListProps<T> = {
  items: T[];
  estimateSize?: number;
  overscan?: number;
  className?: string;
  height?: number | string;
  getKey?: (item: T, index: number) => string | number;
  renderItem: (item: T, index: number) => ReactNode;
  /** Stick scroll to bottom (alert feed) */
  followOutput?: boolean;
  onScroll?: (offset: number) => void;
};

export function VirtualList<T>({
  items,
  estimateSize = 40,
  overscan = 8,
  className,
  height = "100%",
  getKey,
  renderItem,
  followOutput = false,
  onScroll,
}: VirtualListProps<T>) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimateSize,
    overscan,
    getItemKey: getKey ? (index) => getKey(items[index], index) : undefined,
  });

  useEffect(() => {
    if (followOutput && items.length > 0) {
      virtualizer.scrollToIndex(items.length - 1, { align: "end" });
    }
  }, [followOutput, items.length, virtualizer]);

  const handleScroll = useCallback(() => {
    if (parentRef.current && onScroll) {
      onScroll(parentRef.current.scrollTop);
    }
  }, [onScroll]);

  return (
    <div
      ref={parentRef}
      className={cn("overflow-auto spark-scrollbar", className)}
      style={{ height }}
      onScroll={handleScroll}
    >
      <div
        style={{
          height: `${virtualizer.getTotalSize()}px`,
          width: "100%",
          position: "relative",
        }}
      >
        {virtualizer.getVirtualItems().map((virtualRow) => {
          const item = items[virtualRow.index];
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              {renderItem(item, virtualRow.index)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
