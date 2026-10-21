"use client";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ClientPortal } from "@/components/ui/ClientPortal";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { useChatSettings } from "@/hooks/useChatSettings";
import type { useChatSidebar } from "@/hooks/chat/useChatSidebar";
import { sessionLabel, type ChatSessionRow } from "@/lib/chat";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import {
  FileText,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Trash2,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type WorkspaceChatSidebarPanelProps = {
  showLabels: boolean;
  desktop: boolean;
  onNavigate?: () => void;
  chat: ReturnType<typeof useChatSidebar>;
};

export function WorkspaceChatSidebarPanel({
  showLabels,
  desktop,
  onNavigate,
  chat,
}: WorkspaceChatSidebarPanelProps) {
  const { settings } = useChatSettings();
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredSessions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return chat.sessions;
    return chat.sessions.filter((s) => sessionLabel(s).toLowerCase().includes(q));
  }, [chat.sessions, searchQuery]);

  const pinnedSessions = useMemo(
    () => filteredSessions.filter((s) => s.pinned),
    [filteredSessions]
  );
  const recentSessions = useMemo(
    () => filteredSessions.filter((s) => !s.pinned),
    [filteredSessions]
  );

  const handleSelect = (id: string) => {
    chat.handleSelectSession(id);
    if (!desktop) onNavigate?.();
  };

  if (!showLabels) return null;

  return (
    <>
      <div className="workspace-sidebar-divider shrink-0" />

      <div className="shrink-0 px-1 pb-1">
        <button
          type="button"
          onClick={() => setSearchOpen((v) => !v)}
          className={cn(
            "sidebar-nav-link workspace-nav-item w-full gemini-focus-ring",
            "text-gemini-text dark:text-gemini-dark-text",
            searchOpen && "workspace-nav-item-active"
          )}
        >
          <span className="workspace-nav-item-icon">
            <FileText className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <span className="truncate flex-1 text-left text-[0.8125rem]">ค้นหาแชท</span>
        </button>

        {searchOpen && (
          <div className="px-0.5 pt-1 pb-1">
            <input
              type="search"
              autoFocus
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="ค้นหาแชท"
              className={cn(
                "w-full h-8 px-2.5 rounded-lg text-xs gemini-theme-transition",
                "bg-gemini-surface dark:bg-gemini-dark-surface",
                "border border-gemini-border/50 dark:border-gemini-dark-border/50",
                "text-gemini-text dark:text-gemini-dark-text",
                "placeholder:text-gemini-muted dark:placeholder:text-gemini-dark-muted",
                "focus:outline-none focus:ring-1 focus:ring-gemini-blue/40 dark:focus:ring-gemini-dark-blue/40"
              )}
              aria-label="ค้นหาแชท"
            />
          </div>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto gemini-scrollbar px-1 pb-1.5">
        {!settings.saveChatHistory ? (
          <p className="px-2 py-2 text-[11px] text-gemini-muted dark:text-gemini-dark-muted leading-relaxed">
            ไม่ได้บันทึกประวัติแชท
          </p>
        ) : chat.sessionsError ? (
          <div className="px-3 py-3 text-center space-y-2">
            <p className="text-sm text-red-600 dark:text-red-400">โหลดรายการแชทไม่สำเร็จ</p>
            <button
              type="button"
              onClick={() => void chat.refetchSessions()}
              className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline min-h-[44px] px-3"
            >
              ลองใหม่
            </button>
          </div>
        ) : chat.sessionsLoading && chat.sessions.length === 0 ? (
          <div className="space-y-1 px-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        ) : filteredSessions.length === 0 ? (
          <p className="px-2 py-2 text-xs text-gemini-muted dark:text-gemini-dark-muted">
            {searchQuery ? "ไม่พบแชท" : "ยังไม่มีการสนทนา"}
          </p>
        ) : (
          <>
            {pinnedSessions.length > 0 && (
              <SessionGroup
                label="ปักหมุด"
                sessions={pinnedSessions}
                activeSessionId={chat.sessionId}
                onSelect={handleSelect}
                onDelete={chat.handleDeleteSession}
                onPin={chat.handlePinSession}
                onRename={chat.handleRenameSession}
                deletingSessionId={chat.deletingSessionId}
              />
            )}
            <SessionGroup
              label={pinnedSessions.length > 0 ? "ล่าสุด" : "ล่าสุด"}
              sessions={recentSessions}
              activeSessionId={chat.sessionId}
              onSelect={handleSelect}
              onDelete={chat.handleDeleteSession}
              onPin={chat.handlePinSession}
              onRename={chat.handleRenameSession}
              deletingSessionId={chat.deletingSessionId}
            />
          </>
        )}
        {chat.sessionsHasMore && (
          <button
            type="button"
            onClick={() => chat.loadMoreSessions()}
            disabled={chat.sessionsFetchingMore}
            className={cn(
              "w-full mt-1 py-2 text-sm text-gemini-muted dark:text-gemini-dark-muted min-h-[44px]",
              "hover:text-gemini-blue dark:hover:text-gemini-dark-blue",
              chat.sessionsFetchingMore && "opacity-60 cursor-wait"
            )}
          >
            {chat.sessionsFetchingMore ? "กำลังโหลด…" : "โหลดเพิ่ม"}
          </button>
        )}
      </div>

      <ConfirmDialog
        open={!!chat.pendingDeleteSessionId}
        onClose={() => chat.setPendingDeleteSessionId(null)}
        onConfirm={() => void chat.confirmDeleteSession()}
        title="ลบการสนทนา"
        message="ลบการสนทนานี้ถาวร?"
        confirmLabel="ลบ"
        cancelLabel="ยกเลิก"
        destructive
        loading={Boolean(
          chat.pendingDeleteSessionId &&
            chat.deletingSessionId === chat.pendingDeleteSessionId
        )}
      />
    </>
  );
}

function SessionGroup({
  label,
  sessions,
  activeSessionId,
  onSelect,
  onDelete,
  onPin,
  onRename,
  deletingSessionId,
}: {
  label: string;
  sessions: ChatSessionRow[];
  activeSessionId: string;
  onSelect: (id: string) => void;
  onDelete?: (id: string) => void;
  onPin?: (id: string, pinned: boolean) => void;
  onRename?: (id: string, title: string) => void;
  deletingSessionId?: string | null;
}) {
  if (sessions.length === 0) return null;
  return (
    <div className="mb-2">
      <p className="px-2 py-1 text-[10px] font-medium uppercase tracking-wide text-gemini-muted/80 dark:text-gemini-dark-muted/80">
        {label}
      </p>
      {sessions.map((session) => (
        <ChatSessionItem
          key={session.session_id}
          session={session}
          active={session.session_id === activeSessionId}
          onSelect={() => onSelect(session.session_id)}
          onDelete={onDelete ? () => onDelete(session.session_id) : undefined}
          onPin={onPin ? (pinned) => onPin(session.session_id, pinned) : undefined}
          onRename={onRename ? (title) => onRename(session.session_id, title) : undefined}
          deleting={deletingSessionId === session.session_id}
        />
      ))}
    </div>
  );
}

function ChatSessionItem({
  session,
  active,
  onSelect,
  onDelete,
  onPin,
  onRename,
  deleting,
}: {
  session: ChatSessionRow;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void;
  onPin?: (pinned: boolean) => void;
  onRename?: (title: string) => void;
  deleting?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(sessionLabel(session));
  const menuBtnRef = useRef<HTMLButtonElement>(null);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);

  const updateMenuPos = useCallback(() => {
    const el = menuBtnRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const width = 144;
    const menuHeight = 140;
    const spaceBelow = window.innerHeight - r.bottom - 8;
    const top =
      spaceBelow >= menuHeight ? r.bottom + 4 : Math.max(8, r.top - menuHeight - 4);
    setMenuPos({
      top,
      left: Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8)),
    });
  }, []);

  useLayoutEffect(() => {
    if (!menuOpen) return;
    updateMenuPos();
    window.addEventListener("resize", updateMenuPos);
    window.addEventListener("scroll", updateMenuPos, true);
    return () => {
      window.removeEventListener("resize", updateMenuPos);
      window.removeEventListener("scroll", updateMenuPos, true);
    };
  }, [menuOpen, updateMenuPos]);

  useEffect(() => {
    if (!menuOpen) return;
    const dismiss = () => setMenuOpen(false);
    window.addEventListener("spark:dismiss-overlays", dismiss);
    return () => window.removeEventListener("spark:dismiss-overlays", dismiss);
  }, [menuOpen]);

  useEffect(() => {
    if (!renaming) setRenameValue(sessionLabel(session));
  }, [session, renaming]);

  const submitRename = () => {
    const trimmed = renameValue.trim();
    if (trimmed && onRename) onRename(trimmed);
    setRenaming(false);
    setMenuOpen(false);
  };

  return (
    <div
      className={cn(
        "group flex items-center workspace-session-item mb-px relative",
        active && "workspace-nav-item-active"
      )}
    >
      {renaming ? (
        <form
          className="flex-1 flex items-center gap-1 px-2 py-1"
          onSubmit={(e) => {
            e.preventDefault();
            submitRename();
          }}
        >
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setRenaming(false);
            }}
            onBlur={submitRename}
            className={cn(
              "flex-1 min-w-0 h-8 px-3 rounded-xl text-sm",
              "bg-gemini-surface dark:bg-gemini-dark-surface",
              "border border-gemini-border/60 dark:border-gemini-dark-border/60",
              "text-gemini-text dark:text-gemini-dark-text focus:outline-none focus:ring-1 focus:ring-gemini-blue/40"
            )}
            aria-label="เปลี่ยนชื่อแชท"
          />
        </form>
      ) : (
        <button
          type="button"
          onClick={onSelect}
          title={sessionLabel(session)}
          className={cn(
            "flex-1 min-w-0 text-left workspace-session-item gemini-theme-transition gemini-focus-ring",
            "text-gemini-text dark:text-gemini-dark-text truncate",
            "hover:bg-gemini-hover/60 dark:hover:bg-gemini-dark-hover/60",
            session.pinned && "pl-1.5"
          )}
        >
          <span className="flex items-center gap-1 min-w-0">
            {session.pinned && (
              <Pin className="h-2.5 w-2.5 shrink-0 text-gemini-muted dark:text-gemini-dark-muted" />
            )}
            <span className="truncate">{sessionLabel(session)}</span>
          </span>
        </button>
      )}
      {!renaming && (onDelete || onPin || onRename) && (
        <div className="relative shrink-0">
          <button
            ref={menuBtnRef}
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((v) => {
                const next = !v;
                if (next) requestAnimationFrame(updateMenuPos);
                return next;
              });
            }}
            className={cn(
              "w-8 h-8 mr-0.5 flex items-center justify-center rounded-xl",
              "text-gemini-muted dark:text-gemini-dark-muted hover:text-gemini-text",
              "opacity-100 sm:opacity-0 sm:group-hover:opacity-100 focus:opacity-100 transition-opacity",
              menuOpen && "opacity-100"
            )}
            aria-label="ตัวเลือกแชท"
          >
            <MoreHorizontal className="h-4 w-4" />
          </button>
          {menuOpen && menuPos && (
            <ClientPortal>
              <button
                type="button"
                className="fixed inset-0 cursor-default bg-transparent"
                style={{ zIndex: Z_OVERLAY_BACKDROP }}
                aria-label="ปิดเมนู"
                onClick={() => setMenuOpen(false)}
              />
              <div
                className={cn(
                  "fixed min-w-[9rem] py-1 rounded-xl shadow-lg",
                  "bg-gemini-surface dark:bg-gemini-dark-surface",
                  "border border-gemini-border/60 dark:border-gemini-dark-border/60"
                )}
                style={{ zIndex: Z_OVERLAY_PANEL, top: menuPos.top, left: menuPos.left }}
              >
                {onRename && (
                  <button
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-left"
                    onClick={() => {
                      setRenaming(true);
                      setMenuOpen(false);
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    แก้ชื่อ
                  </button>
                )}
                {onPin && (
                  <button
                    type="button"
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-left"
                    onClick={() => {
                      onPin(!session.pinned);
                      setMenuOpen(false);
                    }}
                  >
                    {session.pinned ? (
                      <PinOff className="h-3.5 w-3.5" />
                    ) : (
                      <Pin className="h-3.5 w-3.5" />
                    )}
                    {session.pinned ? "เลิกปักหมุด" : "ปักหมุด"}
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    disabled={deleting}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-500 hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-left"
                    onClick={() => {
                      setMenuOpen(false);
                      onDelete();
                    }}
                  >
                    <Trash2 className={cn("h-3.5 w-3.5", deleting && "animate-pulse")} />
                    ลบ
                  </button>
                )}
              </div>
            </ClientPortal>
          )}
        </div>
      )}
    </div>
  );
}
