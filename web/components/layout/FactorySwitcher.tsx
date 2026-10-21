"use client";

import { ClientPortal } from "@/components/ui/ClientPortal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tooltip } from "@/components/ui/Tooltip";
import { useFactoriesQuery } from "@/hooks/useFactoriesQuery";
import { api } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { invalidateFactoryScopedQueries } from "@/lib/invalidateFactoryQueries";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useUiStore } from "@/stores/uiStore";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Check, ChevronDown } from "lucide-react";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

export type FactorySwitcherProps = {
  expanded: boolean;
  className?: string;
};

type MenuCoords = {
  left: number;
  top?: number;
  bottom?: number;
  width: number;
  maxHeight?: number;
};

export function FactorySwitcher({ expanded, className }: FactorySwitcherProps) {
  const { data: factories = [] } = useFactoriesQuery();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const selectedFactoryIds = useUiStore((s) => s.selectedFactoryIds);
  const setSelectedFactoryId = useUiStore((s) => s.setSelectedFactoryId);
  const setSelectedMachineId = useUiStore((s) => s.setSelectedMachineId);
  const queryClient = useQueryClient();
  const pathname = usePathname();

  const [open, setOpen] = useState(false);
  const [confirmAll, setConfirmAll] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const { data: profile } = useQuery({
    queryKey: queryKeys.myProfile(),
    queryFn: () => api.getMyProfile(),
    staleTime: STALE_STATIC,
  });
  const profileAdmin =
    profile?.is_super_admin || profile?.roles.includes("admin") || false;
  const isAdminRoute = pathname?.startsWith("/admin") ?? false;
  const canShowAll = isAdminRoute && (profileAdmin || canWriteFactory(null));
  const visibleFactories = useMemo(() => {
    if (profileAdmin) return factories;
    if (selectedFactoryIds.length > 0) {
      return factories.filter((f) => selectedFactoryIds.includes(f.factory_id));
    }
    return factories;
  }, [factories, profileAdmin, selectedFactoryIds]);
  const selectedFactory = visibleFactories.find((f) => f.factory_id === selectedFactoryId);

  const selectFactory = (factoryId: string | null) => {
    if (factoryId === null && !canShowAll) {
      return;
    }
    if (factoryId === null && !profileAdmin && canWriteFactory(null)) {
      setConfirmAll(true);
      return;
    }
    setSelectedFactoryId(factoryId);
    setSelectedMachineId(null);
    invalidateFactoryScopedQueries(queryClient);
    setOpen(false);
  };

  useEffect(() => {
    if (canShowAll || selectedFactoryId || visibleFactories.length === 0) return;
    setSelectedFactoryId(visibleFactories[0].factory_id);
    setSelectedMachineId(null);
    invalidateFactoryScopedQueries(queryClient);
  }, [
    canShowAll,
    selectedFactoryId,
    visibleFactories,
    setSelectedFactoryId,
    setSelectedMachineId,
    queryClient,
  ]);

  const label = selectedFactory
    ? selectedFactory.factory_name
    : selectedFactoryId
      ? selectedFactoryId
      : canShowAll
        ? "ทั้งหมด"
        : "เลือกโรงงาน";

  const close = useCallback(() => {
    setOpen(false);
    setCoords(null);
  }, []);

  const updateCoords = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const panelWidth = Math.max(r.width, 220);
    const margin = 8;
    const left = Math.min(Math.max(margin, r.left), window.innerWidth - panelWidth - margin);
    const spaceBelow = window.innerHeight - r.bottom - margin;
    const spaceAbove = r.top - margin;
    const preferBelow = spaceBelow >= spaceAbove;

    if (preferBelow) {
      setCoords({
        left,
        top: r.bottom + margin,
        width: panelWidth,
        maxHeight: Math.max(160, spaceBelow - margin),
      });
    } else {
      setCoords({
        left,
        bottom: window.innerHeight - r.top + margin,
        width: panelWidth,
        maxHeight: Math.max(160, spaceAbove - margin),
      });
    }
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    updateCoords();
    window.addEventListener("resize", updateCoords);
    window.addEventListener("scroll", updateCoords, true);
    return () => {
      window.removeEventListener("resize", updateCoords);
      window.removeEventListener("scroll", updateCoords, true);
    };
  }, [open, updateCoords]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    const onDismiss = () => close();
    document.addEventListener("keydown", onKey);
    window.addEventListener("spark:dismiss-overlays", onDismiss);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("spark:dismiss-overlays", onDismiss);
    };
  }, [open, close]);

  if (visibleFactories.length === 0) return null;

  const triggerClass = cn(
    "gemini-theme-transition gemini-focus-ring w-full flex items-center gap-2 rounded-xl border",
    "border-gemini-border/60 dark:border-gemini-dark-border/60",
    "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
    expanded ? "h-10 px-3 text-sm" : "h-10 w-10 justify-center mx-auto",
    open && "bg-gemini-hover dark:bg-gemini-dark-hover"
  );

  const triggerHint = expanded
    ? "เปลี่ยนโรงงานที่ต้องการดูข้อมูล"
    : `เลือกโรงงาน — ตอนนี้: ${label}`;

  return (
    <>
      <div className={cn("shrink-0", expanded ? "px-2 pb-2" : "px-1.5 pb-2", className)}>
        <Tooltip content={triggerHint} side="right" disabled={expanded}>
          <button
            ref={triggerRef}
            type="button"
            onClick={() => setOpen((v) => !v)}
            className={triggerClass}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={`โรงงาน: ${label}`}
          >
          <Building2 className="h-4 w-4 shrink-0 text-gemini-muted" strokeWidth={1.75} />
          {expanded && (
            <>
              <span className="flex-1 min-w-0 text-left truncate text-gemini-text dark:text-gemini-dark-text">
                {label}
              </span>
              <ChevronDown
                className={cn("h-4 w-4 shrink-0 text-gemini-muted transition-transform", open && "rotate-180")}
                strokeWidth={1.75}
              />
            </>
          )}
          </button>
        </Tooltip>
      </div>

      {open && coords && (
        <ClientPortal>
          <button
            type="button"
            className="fixed inset-0 cursor-default"
            style={{ zIndex: Z_OVERLAY_BACKDROP }}
            aria-label="ปิดเมนูโรงงาน"
            onClick={close}
          />
          <div
            role="listbox"
            aria-label="เลือกโรงงาน"
            className={cn(
              "fixed overflow-y-auto gemini-scrollbar rounded-xl border shadow-lg",
              "border-gemini-border/70 dark:border-gemini-dark-border/70",
              "bg-gemini-bg dark:bg-gemini-dark-bg py-1"
            )}
            style={{
              zIndex: Z_OVERLAY_PANEL,
              left: coords.left,
              top: coords.top,
              bottom: coords.bottom,
              width: coords.width,
              maxHeight: coords.maxHeight,
            }}
          >
            {canShowAll && (
              <button
                type="button"
                role="option"
                aria-selected={!selectedFactoryId}
                onClick={() => selectFactory(null)}
                className={cn(
                  "w-full flex items-center gap-2 px-3 py-2 text-sm text-left",
                  "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
                  !selectedFactoryId && "bg-gemini-hover/70 dark:bg-gemini-dark-hover/70"
                )}
              >
                <span className="flex-1 truncate">ทั้งหมด</span>
                {!selectedFactoryId && <Check className="h-4 w-4 shrink-0 text-gemini-accent" />}
              </button>
            )}
            {visibleFactories.map((factory) => {
              const active = selectedFactoryId === factory.factory_id;
              return (
                <button
                  key={factory.factory_id}
                  type="button"
                  role="option"
                  aria-selected={active}
                  onClick={() => selectFactory(factory.factory_id)}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-2 text-sm text-left",
                    "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
                    active && "bg-gemini-hover/70 dark:bg-gemini-dark-hover/70"
                  )}
                >
                  <span className="flex-1 min-w-0">
                    <span className="block truncate">{factory.factory_name}</span>
                    <span className="block truncate text-xs font-mono text-gemini-muted">
                      {factory.factory_id}
                    </span>
                  </span>
                  {active && <Check className="h-4 w-4 shrink-0 text-gemini-accent" />}
                </button>
              );
            })}
          </div>
        </ClientPortal>
      )}

      {confirmAll && (
        <ConfirmDialog
          open
          onClose={() => setConfirmAll(false)}
          onConfirm={() => {
            setSelectedFactoryId(null);
            setSelectedMachineId(null);
            invalidateFactoryScopedQueries(queryClient);
            setOpen(false);
            setConfirmAll(false);
          }}
          title="เลือกทุกโรงงาน?"
          message="การดูข้อมูลรวมทุกโรงงานอาจช้ากว่าการเลือกโรงงานเดียว — ต้องการดำเนินการต่อหรือไม่?"
          confirmLabel="เลือกทั้งหมด"
          cancelLabel="ยกเลิก"
        />
      )}
    </>
  );
}
