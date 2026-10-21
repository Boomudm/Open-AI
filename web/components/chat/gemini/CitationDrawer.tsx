"use client";

import { CitationList } from "@/components/chat/gemini/CitationList";
import { ClientPortal } from "@/components/ui/ClientPortal";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { useIsDesktopNav } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/cn";
import {
  isCitationUserInitiated,
  resetCitationUserInitiated,
  subscribeCitationPresentation,
} from "@/lib/citationPresentation";
import {
  MSG_INDEXED_DOCS,
  MSG_SOURCES_CLOSE,
  MSG_SOURCES_PANEL,
} from "@/lib/messages.th";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import {
  findLastAssistantId,
  getActiveSources,
  useChatStore,
} from "@/stores/chatStore";
import { X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

const headerIconBtn =
  "h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover hover:text-gemini-text dark:hover:text-gemini-dark-text";

const SWIPE_DISMISS_PX = 80;

export function CitationDrawer() {
  const sourcesOpen = useChatStore((s) => s.sourcesOpen);
  const closeSources = useChatStore((s) => s.closeSources);
  const isDesktop = useIsDesktopNav();
  const [, bump] = useState(0);

  useEffect(() => subscribeCitationPresentation(() => bump((n) => n + 1)), []);

  useEffect(() => {
    if (isDesktop || !sourcesOpen) return;
    if (!isCitationUserInitiated()) {
      closeSources();
    }
  }, [sourcesOpen, isDesktop, closeSources]);

  useEffect(() => {
    if (!sourcesOpen) {
      resetCitationUserInitiated();
    }
  }, [sourcesOpen]);

  const visible =
    sourcesOpen && (isDesktop || isCitationUserInitiated());

  if (!visible) return null;
  return <CitationDrawerPanel isDesktop={isDesktop} />;
}

function CitationDrawerPanel({ isDesktop }: { isDesktop: boolean }) {
  const { indexedDocuments, indexedLoading } = useChatSession();
  const closeSources = useChatStore((s) => s.closeSources);
  const selectedId = useChatStore((s) => s.selectedMsgId);
  const messages = useChatStore((s) => s.messages);
  const sheetRef = useRef<HTMLElement | null>(null);
  const [sheetElement, setSheetElement] = useState<HTMLElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const headingId = useId();
  const dragStartY = useRef<number | null>(null);
  const dragOffset = useRef(0);
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);

  const activeSourceId = useMemo(
    () => selectedId ?? findLastAssistantId(messages),
    [selectedId, messages]
  );
  const sources = useMemo(
    () => getActiveSources(messages, selectedId, findLastAssistantId(messages)),
    [messages, selectedId]
  );

  const showCited = sources.length > 0;

  const setSheetRefs = useCallback((node: HTMLElement | null) => {
    sheetRef.current = node;
    setSheetElement(node);
  }, []);

  useEffect(() => {
    const sheet = sheetElement;
    if (!sheet) return;
    const appMain = document.querySelector<HTMLElement>('main[aria-label="Neo Chat"]');
    const mainWasInert = appMain?.inert ?? false;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    if (appMain) appMain.inert = true;
    const focusFrame = window.requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });
    const focusableSelector =
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeSources();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        sheet.querySelectorAll<HTMLElement>(focusableSelector)
      ).filter((element) => !element.hidden && element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener("keydown", onKeyDown);
      if (appMain) appMain.inert = mainWasInert;
      previousFocusRef.current?.focus();
      previousFocusRef.current = null;
    };
  }, [closeSources, sheetElement]);

  const finishDrag = useCallback(() => {
    if (dragOffset.current > SWIPE_DISMISS_PX) {
      closeSources();
    }
    dragStartY.current = null;
    dragOffset.current = 0;
    setDragY(0);
    setDragging(false);
  }, [closeSources]);

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (isDesktop) return;
      dragStartY.current = e.touches[0]?.clientY ?? null;
      setDragging(true);
    },
    [isDesktop]
  );

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (isDesktop || dragStartY.current == null) return;
      const y = e.touches[0]?.clientY ?? dragStartY.current;
      const delta = Math.max(0, y - dragStartY.current);
      dragOffset.current = delta;
      setDragY(delta);
    },
    [isDesktop]
  );

  const onTouchEnd = useCallback(() => {
    finishDrag();
  }, [finishDrag]);

  return (
    <ClientPortal>
      <div
        aria-hidden="true"
        className="fixed inset-0 bg-black/20 dark:bg-black/50 backdrop-blur-[1px] gemini-theme-transition"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        onClick={closeSources}
      />
      <aside
        ref={setSheetRefs}
        className={cn(
          "fixed flex flex-col gemini-theme-transition bg-gemini-bg dark:bg-gemini-dark-bg shadow-gemini-input-dark",
          isDesktop
            ? "top-0 right-0 bottom-0 w-full max-w-sm border-l border-gemini-border dark:border-gemini-dark-border transition-transform duration-300 ease-out"
            : "inset-x-0 bottom-0 max-h-[min(85dvh,640px)] rounded-t-2xl border-t border-gemini-border dark:border-gemini-dark-border"
        )}
        style={{
          zIndex: Z_OVERLAY_PANEL,
          transform: !isDesktop && dragY > 0 ? `translateY(${dragY}px)` : undefined,
          transition: dragging ? "none" : undefined,
        }}
        aria-label={MSG_SOURCES_PANEL}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
      >
        {!isDesktop && (
          <div
            className="shrink-0 flex justify-center pt-2 pb-1 touch-none"
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
            onTouchCancel={onTouchEnd}
          >
            <div
              className="h-1.5 w-10 rounded-full bg-gemini-border dark:bg-gemini-dark-border"
              aria-hidden
            />
          </div>
        )}
        <div className="shrink-0 flex items-center justify-between px-4 h-14 border-b border-gemini-border/60 dark:border-gemini-dark-border/60">
          <h2
            id={headingId}
            className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text"
          >
            {showCited ? MSG_SOURCES_PANEL : MSG_INDEXED_DOCS}
          </h2>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={closeSources}
            className={headerIconBtn}
            aria-label={MSG_SOURCES_CLOSE}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-2 gemini-scrollbar overscroll-contain">
          <CitationList
            sources={sources}
            indexedDocuments={indexedDocuments}
            indexedLoading={indexedLoading}
            messageId={activeSourceId}
            onItemOpen={closeSources}
          />
        </div>
      </aside>
    </ClientPortal>
  );
}
