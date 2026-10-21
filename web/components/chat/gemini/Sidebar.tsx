"use client";

import { AccountMenu } from "@/components/chat/gemini/AccountMenu";
import { FactorySwitcher } from "@/components/layout/FactorySwitcher";
import { WorkspaceModeToggle } from "@/components/workspace/WorkspaceModeToggle";
import { NeoLogo } from "@/components/chat/gemini/NeoLogo";
import { SkeletonRow } from "@/components/ui/SkeletonLoader";
import { ClientPortal } from "@/components/ui/ClientPortal";
import { api } from "@/lib/api";
import { canWriteFactory, isAdminUser, isSuperAdminUser } from "@/lib/auth";
import { sessionLabel, type ChatSessionRow } from "@/lib/chat";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { useUiStore } from "@/stores/uiStore";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  LayoutGrid,
  MessageSquareWarning,
  PanelLeftClose,
  Search,
  SquarePen,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { rememberSystemAdminReturnPath } from "@/lib/system-admin/nocNavigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

export type GeminiSidebarView = "chats" | "documents" | "feedback";

export type GeminiSidebarProps = {
  expanded: boolean;
  onToggleExpanded: () => void;
  desktop: boolean;
  mobileOpen: boolean;
  onMobileClose: () => void;
  view: GeminiSidebarView;
  onViewChange: (view: GeminiSidebarView) => void;
  sessions: ChatSessionRow[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewChat: () => void;
  onDeleteSession?: (id: string) => void;
  onPinSession?: (id: string, pinned: boolean) => void;
  onRenameSession?: (id: string, title: string) => void;
  deletingSessionId?: string | null;
  creatingSession?: boolean;
  sessionsLoading?: boolean;
  sessionsError?: boolean;
  onRetrySessions?: () => void;
  hasMore?: boolean;
  onLoadMore?: () => void;
  isFetchingMore?: boolean;
  saveChatHistory?: boolean;
  onOpenSettings?: () => void;
  username?: string;
};

const navBtn = cn(
  "flex items-center gap-3 w-full rounded-full gemini-theme-transition gemini-focus-ring",
  "text-gemini-text dark:text-gemini-dark-text",
  "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
);

const iconOnlyBtn = cn(
  "shrink-0 h-10 w-10 flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring",
  "text-gemini-muted dark:text-gemini-dark-muted",
  "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
  "hover:text-gemini-text dark:hover:text-gemini-dark-text"
);

export function GeminiSidebar({
  expanded,
  onToggleExpanded,
  desktop,
  mobileOpen,
  onMobileClose,
  view,
  onViewChange,
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onPinSession,
  onRenameSession,
  deletingSessionId,
  creatingSession,
  sessionsLoading,
  sessionsError,
  onRetrySessions,
  hasMore,
  onLoadMore,
  isFetchingMore,
  saveChatHistory = true,
  onOpenSettings,
  username = "Operator",
}: GeminiSidebarProps) {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const showFeedbackTab = true;
  const canTriageFeedback = canWriteFactory(selectedFactoryId);
  const showSystemAdminLink = isSuperAdminUser() || isAdminUser();

  const { data: openFeedbackCount } = useQuery({
    queryKey: ["feedback-open-count", selectedFactoryId],
    queryFn: () =>
      api.feedbackOpenCount({
        factory_id: selectedFactoryId || undefined,
        status: "open",
      }),
    enabled: canTriageFeedback,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const { data: myFeedbackPage } = useQuery({
    queryKey: ["feedback-mine-open", selectedFactoryId],
    queryFn: () =>
      api.listFeedback({
        mine: true,
        status: "open",
        factory_id: selectedFactoryId || undefined,
        page: 1,
        page_size: 1,
      }),
    enabled: !canTriageFeedback,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const feedbackBadge = canTriageFeedback
    ? openFeedbackCount?.count
    : myFeedbackPage?.total;

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [richContent, setRichContent] = useState(expanded);

  useEffect(() => {
    if (!desktop) {
      setRichContent(true);
      return;
    }
    if (expanded) setRichContent(true);
  }, [expanded, desktop]);

  const handleAsideTransitionEnd = (event: React.TransitionEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget || event.propertyName !== "width") return;
    if (desktop && !expanded) {
      setRichContent(false);
      setSearchOpen(false);
    }
  };

  const filteredSessions = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => sessionLabel(s).toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  const pinnedSessions = useMemo(
    () => filteredSessions.filter((s) => s.pinned),
    [filteredSessions]
  );
  const recentSessions = useMemo(
    () => filteredSessions.filter((s) => !s.pinned),
    [filteredSessions]
  );

  const showLabels = desktop ? richContent : true;
  const widthClass = desktop
    ? expanded
      ? "w-chat-sidebar"
      : "w-chat-sidebar-collapsed"
    : "w-chat-sidebar";

  const handleSelect = (id: string) => {
    onSelectSession(id);
    onViewChange("chats");
    if (!desktop) onMobileClose();
  };

  const handleNewChat = () => {
    if (creatingSession) return;
    onNewChat();
    onViewChange("chats");
    setSearchOpen(false);
    if (!desktop) onMobileClose();
  };

  const toggleSearch = () => {
    if (!showLabels) {
      onToggleExpanded();
      setSearchOpen(true);
      return;
    }
    setSearchOpen((v) => !v);
  };

  return (
    <>
      {!desktop && mobileOpen && (
        <button
          type="button"
          aria-label="ปิดแถบด้านข้าง"
          className="fixed inset-0 z-[90] bg-black/40 dark:bg-black/60 backdrop-blur-[2px] lg:hidden sidebar-mobile-backdrop"
          onClick={onMobileClose}
        />
      )}

      <aside
        onTransitionEnd={handleAsideTransitionEnd}
        className={cn(
          "fixed inset-y-0 left-0 z-[100] flex flex-col overflow-hidden chat-sidebar-slide",
          "bg-gemini-sidebar dark:bg-gemini-dark-sidebar",
          widthClass,
          !desktop && !mobileOpen && "-translate-x-full",
          !desktop && mobileOpen && "translate-x-0"
        )}
        aria-label="แถบแชท"
      >
        <div
          className={cn(
            "shrink-0 flex items-center h-14 gemini-theme-transition",
            showLabels ? "px-3 gap-2 w-full" : "justify-center px-2"
          )}
        >
          {showLabels ? (
            <>
              <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                <NeoLogo heightClass="h-5" />
                <span
                  className={cn(
                    "truncate text-sm font-medium text-gemini-text dark:text-gemini-dark-text sidebar-slide-label",
                    richContent ? "sidebar-slide-label-visible" : "sidebar-slide-label-hidden"
                  )}
                >
                  แชท
                </span>
              </div>
              {desktop ? (
                <button
                  type="button"
                  onClick={onToggleExpanded}
                  className={cn(
                    iconOnlyBtn,
                    "sidebar-slide-fade",
                    richContent ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden"
                  )}
                  aria-label="ย่อแถบด้านข้าง"
                  title="ย่อแถบด้านข้าง"
                >
                  <PanelLeftClose className="h-5 w-5" />
                </button>
              ) : (
                mobileOpen && (
                  <button
                    type="button"
                    onClick={onMobileClose}
                    className={iconOnlyBtn}
                    aria-label="ปิด"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )
              )}
            </>
          ) : (
            <button
              type="button"
              onClick={onToggleExpanded}
              className={cn(
                "gemini-theme-transition gemini-focus-ring rounded-full flex items-center justify-center",
                "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
                "h-10 w-full max-w-full px-1"
              )}
              aria-label="ขยายแถบด้านข้าง"
              title="ขยายแถบด้านข้าง"
            >
              <NeoLogo heightClass="h-5" />
            </button>
          )}
        </div>

        <div
          className={cn(
            "shrink-0 space-y-0.5",
            showLabels ? "px-3" : "px-2 flex flex-col items-center gap-1"
          )}
        >
          <SidebarNavItem
            icon={<SquarePen className="h-[18px] w-[18px]" strokeWidth={1.75} />}
            label={creatingSession ? "กำลังสร้าง…" : "แชทใหม่"}
            showLabel={showLabels}
            active={false}
            primary
            disabled={creatingSession}
            onClick={handleNewChat}
          />

          <SidebarNavItem
            icon={<Search className="h-[18px] w-[18px]" strokeWidth={1.75} />}
            label="ค้นหาแชท"
            showLabel={showLabels}
            active={searchOpen}
            onClick={toggleSearch}
          />

          {searchOpen && showLabels && (
            <div
              className={cn(
                "px-1 pb-1 overflow-hidden sidebar-slide-fade",
                searchOpen ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden"
              )}
            >
              <input
                type="search"
                autoFocus
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="ค้นหาแชท"
                className={cn(
                  "w-full h-9 px-3 rounded-full text-sm gemini-theme-transition",
                  "bg-gemini-surface dark:bg-gemini-dark-surface",
                  "border border-gemini-border/60 dark:border-gemini-dark-border/60",
                  "text-gemini-text dark:text-gemini-dark-text",
                  "placeholder:text-gemini-muted dark:placeholder:text-gemini-dark-muted",
                  "focus:outline-none focus:ring-1 focus:ring-gemini-blue/40 dark:focus:ring-gemini-dark-blue/40"
                )}
                aria-label="ค้นหาแชท"
              />
            </div>
          )}

          <SidebarNavItem
            icon={<LayoutGrid className="h-[18px] w-[18px]" strokeWidth={1.75} />}
            label="เอกสาร"
            showLabel={showLabels}
            active={view === "documents"}
            onClick={() => {
              setSearchOpen(false);
              onViewChange("documents");
              if (!desktop) onMobileClose();
            }}
          />

          {showFeedbackTab && (
            <SidebarNavItem
              icon={<MessageSquareWarning className="h-[18px] w-[18px]" strokeWidth={1.75} />}
              label="แจ้งกลับ"
              showLabel={showLabels}
              active={view === "feedback"}
              badge={
                feedbackBadge && feedbackBadge > 0 ? feedbackBadge : undefined
              }
              onClick={() => {
                setSearchOpen(false);
                onViewChange("feedback");
                if (!desktop) onMobileClose();
              }}
            />
          )}

          {showSystemAdminLink && (
            <SidebarNavLink
              href="/system-admin"
              icon={<Activity className="h-[18px] w-[18px]" strokeWidth={1.75} />}
              label="ศูนย์ควบคุมระบบ"
              showLabel={showLabels}
              onNavigate={() => {
                rememberSystemAdminReturnPath();
                if (!desktop) onMobileClose();
              }}
            />
          )}

        </div>

        {view === "chats" && showLabels && (
          <div
            className={cn(
              "flex-1 min-h-0 flex flex-col mt-3 overflow-hidden sidebar-slide-fade",
              showLabels ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden"
            )}
          >
            {!saveChatHistory ? (
              <p className="px-5 py-2 text-xs text-gemini-muted dark:text-gemini-dark-muted leading-relaxed">
                ไม่ได้บันทึกประวัติแชท
              </p>
            ) : (
              <div className="flex-1 min-h-0 overflow-y-auto gemini-scrollbar px-2 pb-2">
                {sessionsError ? (
                  <div className="px-4 py-3 text-center space-y-2">
                    <p className="text-sm text-red-600 dark:text-red-400">โหลดรายการแชทไม่สำเร็จ</p>
                    {onRetrySessions && (
                      <button
                        type="button"
                        onClick={onRetrySessions}
                        className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline min-h-[44px] px-3"
                      >
                        ลองใหม่
                      </button>
                    )}
                  </div>
                ) : sessionsLoading && sessions.length === 0 ? (
                  <div className="space-y-1 px-1">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <SkeletonRow key={i} />
                    ))}
                  </div>
                ) : filteredSessions.length === 0 ? (
                  <p className="px-4 py-3 text-sm text-gemini-muted dark:text-gemini-dark-muted">
                    {searchQuery ? "ไม่พบแชท" : "ยังไม่มีการสนทนา"}
                  </p>
                ) : (
                  <>
                    {pinnedSessions.length > 0 && (
                      <SessionGroup
                        label="ปักหมุด"
                        sessions={pinnedSessions}
                        activeSessionId={activeSessionId}
                        onSelect={handleSelect}
                        onDelete={onDeleteSession}
                        onPin={onPinSession}
                        onRename={onRenameSession}
                        deletingSessionId={deletingSessionId}
                      />
                    )}
                    <SessionGroup
                      label={pinnedSessions.length > 0 ? "ล่าสุด" : "ล่าสุด"}
                      sessions={recentSessions}
                      activeSessionId={activeSessionId}
                      onSelect={handleSelect}
                      onDelete={onDeleteSession}
                      onPin={onPinSession}
                      onRename={onRenameSession}
                      deletingSessionId={deletingSessionId}
                    />
                  </>
                )}
                {hasMore && onLoadMore && (
                  <button
                    type="button"
                    onClick={onLoadMore}
                    disabled={isFetchingMore}
                    className={cn(
                      "w-full mt-1 py-2 text-sm text-gemini-muted dark:text-gemini-dark-muted min-h-[44px]",
                      "hover:text-gemini-blue dark:hover:text-gemini-dark-blue",
                      isFetchingMore && "opacity-60 cursor-wait"
                    )}
                  >
                    {isFetchingMore ? "กำลังโหลด…" : "โหลดเพิ่ม"}
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {view === "feedback" && showLabels && !canTriageFeedback && (
          <div className="flex-1 min-h-0 flex items-center justify-center px-5 pb-4">
            <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center">
              รายการที่คุณแจ้ง — ดูในแผงหลัก
            </p>
          </div>
        )}

        {!showLabels && <div className="flex-1" />}

        <div
          className={cn(
            "shrink-0 overflow-visible px-2 pb-3 pt-2",
            showLabels ? "" : "flex flex-col items-center gap-2"
          )}
        >
          <div
            className={cn(
              "sidebar-slide-fade w-full space-y-2",
              showLabels ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden hidden"
            )}
          >
            <WorkspaceModeToggle
              showLabel
              onNavigate={() => {
                if (!desktop) onMobileClose();
              }}
            />
            <FactorySwitcher expanded />
            <div className="flex items-center gap-1 min-w-0">
              <div className="flex-1 min-w-0">
                <AccountMenu username={username} showLabel collapsed={false} />
              </div>
              {onOpenSettings && (
                <button
                  type="button"
                  onClick={onOpenSettings}
                  className={iconOnlyBtn}
                  aria-label="ตั้งค่า"
                  title="ตั้งค่า"
                >
                  <SettingsIcon />
                </button>
              )}
            </div>
          </div>
          <div
            className={cn(
              "flex flex-col items-center gap-2 w-full sidebar-slide-fade",
              !showLabels ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden hidden"
            )}
          >
            <WorkspaceModeToggle
              collapsed
              onNavigate={() => {
                if (!desktop) onMobileClose();
              }}
            />
            <FactorySwitcher expanded={false} />
            {onOpenSettings && (
              <button
                type="button"
                onClick={onOpenSettings}
                className={iconOnlyBtn}
                aria-label="ตั้งค่า"
                title="ตั้งค่า"
              >
                <SettingsIcon />
              </button>
            )}
            <AccountMenu username={username} showLabel={false} collapsed />
          </div>
        </div>

      </aside>
    </>
  );
}

function SettingsIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="h-5 w-5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"
      />
    </svg>
  );
}

function SidebarNavLink({
  href,
  icon,
  label,
  showLabel,
  onNavigate,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  showLabel: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={href}
      onClick={() => {
        window.dispatchEvent(new CustomEvent("spark:dismiss-overlays"));
        onNavigate?.();
      }}
      title={!showLabel ? label : undefined}
      aria-label={!showLabel ? label : undefined}
      className={cn(
        showLabel ? cn(navBtn, "h-11 px-4 text-sm font-normal") : iconOnlyBtn
      )}
    >
      <span className="shrink-0 text-gemini-muted dark:text-gemini-dark-muted">{icon}</span>
      {showLabel && (
        <span className="sidebar-slide-label sidebar-slide-label-visible truncate flex-1 text-left">
          {label}
        </span>
      )}
    </Link>
  );
}

function SidebarNavItem({
  icon,
  label,
  active,
  showLabel,
  onClick,
  primary = false,
  disabled = false,
  badge,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  showLabel: boolean;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
  badge?: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={!showLabel ? label : undefined}
      aria-label={!showLabel ? label : undefined}
      className={cn(
        showLabel ? cn(navBtn, "h-11 px-4 text-sm font-normal") : iconOnlyBtn,
        primary && "bg-gemini-new-chat dark:bg-gemini-dark-new-chat shadow-gemini-new-chat dark:shadow-gemini-new-chat-dark",
        active && !primary && "bg-gemini-hover dark:bg-gemini-dark-hover",
        disabled && "opacity-60 cursor-wait"
      )}
    >
      <span className="shrink-0 text-gemini-muted dark:text-gemini-dark-muted">{icon}</span>
      {showLabel && (
        <span className="sidebar-slide-label sidebar-slide-label-visible truncate flex-1 text-left">
          {label}
        </span>
      )}
      {showLabel && badge != null && badge > 0 && (
        <span className="shrink-0 min-w-[1.25rem] h-5 px-1.5 flex items-center justify-center rounded-full text-[10px] font-medium bg-amber-500 text-white">
          {badge > 99 ? "99+" : badge}
        </span>
      )}
    </button>
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
      <p className="px-3 py-1 text-xs text-gemini-muted dark:text-gemini-dark-muted">{label}</p>
      {sessions.map((session) => (
        <ChatSessionItem
          key={session.session_id}
          session={session}
          active={session.session_id === activeSessionId}
          onSelect={() => onSelect(session.session_id)}
          onDelete={onDelete ? () => onDelete(session.session_id) : undefined}
          onPin={
            onPin ? (pinned) => onPin(session.session_id, pinned) : undefined
          }
          onRename={
            onRename ? (title) => onRename(session.session_id, title) : undefined
          }
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
        "group flex items-center rounded-full mb-0.5 relative",
        active && "bg-gemini-hover dark:bg-gemini-dark-hover"
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
              "flex-1 min-w-0 h-8 px-3 rounded-full text-sm",
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
            "flex-1 min-w-0 text-left px-4 py-2.5 rounded-full gemini-theme-transition gemini-focus-ring",
            "text-sm text-gemini-text dark:text-gemini-dark-text truncate",
            "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
            session.pinned && "pl-3"
          )}
        >
          <span className="flex items-center gap-1.5 min-w-0">
            {session.pinned && (
              <Pin className="h-3 w-3 shrink-0 text-gemini-muted dark:text-gemini-dark-muted" />
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
              "w-8 h-8 mr-0.5 flex items-center justify-center rounded-full",
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
