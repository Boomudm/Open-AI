"use client";

import { AccountMenu } from "@/components/chat/gemini/AccountMenu";
import { NeoLogo } from "@/components/chat/gemini/NeoLogo";
import { SettingsModal } from "@/components/chat/gemini/SettingsModal";
import { FactorySwitcher } from "@/components/layout/FactorySwitcher";
import { Tooltip } from "@/components/ui/Tooltip";
import { useChatSettings } from "@/hooks/useChatSettings";
import { useTheme } from "@/hooks/useTheme";
import { useAuthProfile } from "@/hooks/useAuthProfile";
import { api } from "@/lib/api";
import {
  canUploadDocuments,
  canWriteFactory,
  getUsername,
  isAdminUser,
} from "@/lib/auth";
import { cn } from "@/lib/cn";
import {
  filterWorkspaceNavItems,
  getWorkspacePageTitle,
  isWorkspaceNavActive,
  WORKSPACE_NAV_ITEMS,
  type WorkspaceNavItemConfig,
} from "@/lib/workspaceNav";
import { workspaceNavIcon } from "@/lib/workspaceNavIcons";
import { WorkspaceChatSidebarPanel } from "@/components/workspace/WorkspaceChatSidebarPanel";
import { useChatSidebar } from "@/hooks/chat/useChatSidebar";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useUiStore } from "@/stores/uiStore";
import { PanelLeftClose, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { rememberSystemAdminReturnPath } from "@/lib/system-admin/nocNavigation";
import { Suspense, useEffect, useRef, useState } from "react";

const SIDEBAR_KEY = "spark_workspace_sidebar_expanded";

export type WorkspaceSidebarProps = {
  desktop: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
};

const navBtn = cn(
  "sidebar-nav-link workspace-nav-item gemini-focus-ring",
  "text-gemini-text dark:text-gemini-dark-text"
);

const navBtnCollapsed = cn(
  "sidebar-nav-link workspace-nav-item workspace-nav-item-collapsed gemini-focus-ring",
  "text-gemini-muted hover:text-gemini-text dark:hover:text-gemini-dark-text"
);

const iconOnlyBtn = cn(
  "sidebar-nav-link shrink-0 h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg gemini-focus-ring",
  "text-gemini-muted",
  "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
);

export function WorkspaceSidebar({
  desktop,
  expanded,
  onToggleExpanded,
  mobileOpen,
  onMobileClose,
}: WorkspaceSidebarProps) {
  const pathname = usePathname();
  const { profile } = useAuthProfile();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const asideRef = useRef<HTMLElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const { data: chatCapabilities } = useQuery({
    queryKey: queryKeys.chatCapabilities(),
    queryFn: () => api.getChatCapabilities(),
    enabled: settingsOpen,
    staleTime: STALE_STATIC,
  });
  const [username, setUsername] = useState("Operator");
  const [richContent, setRichContent] = useState(expanded);
  const { settings, setSettings, toggleRagSource } = useChatSettings();
  const { preference: themePreference, setPreference: setThemePreference } = useTheme();

  const canWrite = canWriteFactory(selectedFactoryId);
  const { data: openFeedbackCount } = useQuery({
    queryKey: ["feedback-open-count", selectedFactoryId],
    queryFn: () =>
      api.feedbackOpenCount({
        factory_id: selectedFactoryId || undefined,
        status: "open",
      }),
    enabled: canWrite,
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  useEffect(() => {
    setUsername(getUsername() || "Operator");
  }, []);

  useEffect(() => {
    if (!desktop) {
      setRichContent(true);
      return;
    }
    if (expanded) setRichContent(true);
  }, [expanded, desktop]);

  useEffect(() => {
    const aside = asideRef.current;
    if (!aside) return;
    aside.inert = !desktop && !mobileOpen;
  }, [desktop, mobileOpen]);

  useEffect(() => {
    if (desktop || !mobileOpen || settingsOpen) return;
    const aside = asideRef.current;
    if (!aside) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const focusableSelector =
      'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
    const focusFirst = window.requestAnimationFrame(() => {
      const closeButton = aside.querySelector<HTMLElement>('button[aria-label="ปิด"]');
      (closeButton ?? aside.querySelector<HTMLElement>(focusableSelector))?.focus();
    });

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onMobileClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        aside.querySelectorAll<HTMLElement>(focusableSelector)
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
      window.cancelAnimationFrame(focusFirst);
      document.removeEventListener("keydown", onKeyDown);
      const previousFocus = previousFocusRef.current;
      window.setTimeout(() => previousFocus?.focus(), 0);
      previousFocusRef.current = null;
    };
  }, [desktop, mobileOpen, onMobileClose, settingsOpen]);

  const handleAsideTransitionEnd = (event: React.TransitionEvent<HTMLElement>) => {
    if (event.target !== event.currentTarget || event.propertyName !== "width") return;
    if (desktop && !expanded) setRichContent(false);
  };

  const visibleItems = filterWorkspaceNavItems(WORKSPACE_NAV_ITEMS, {
    isAdmin: isAdminUser(),
    isSuperAdmin: Boolean(profile?.is_super_admin),
    canWrite,
    canUpload: canUploadDocuments(selectedFactoryId),
  });

  const feedbackBadge =
    openFeedbackCount && openFeedbackCount.count > 0 ? openFeedbackCount.count : undefined;

  const showLabels = desktop ? richContent : true;
  const widthClass = desktop
    ? expanded
      ? "w-chat-sidebar"
      : "w-chat-sidebar-collapsed"
    : "w-chat-sidebar";

  const isActive = (href: string) => isWorkspaceNavActive(pathname, href);
  const onChat = pathname === "/chat";

  return (
    <>
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onSettingsChange={setSettings}
        onRagSourceToggle={toggleRagSource}
        themePreference={themePreference}
        onThemePreferenceChange={setThemePreference}
        serverModel={chatCapabilities?.llm_model}
        serverProfile={chatCapabilities?.llm_profile}
        topKFast={chatCapabilities?.top_k_fast}
        topKAdvanced={chatCapabilities?.top_k_advanced}
      />

      {!desktop && mobileOpen && (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-[90] bg-black/40 dark:bg-black/60 backdrop-blur-[2px] lg:hidden sidebar-mobile-backdrop"
          onClick={onMobileClose}
        />
      )}

      <aside
        ref={asideRef}
        onTransitionEnd={handleAsideTransitionEnd}
        className={cn(
          "fixed inset-y-0 left-0 z-[100] flex flex-col overflow-hidden chat-sidebar-slide workspace-sidebar",
          "bg-gemini-sidebar dark:bg-gemini-dark-sidebar",
          widthClass,
          !desktop && !mobileOpen && "-translate-x-full",
          !desktop && mobileOpen && "translate-x-0"
        )}
        aria-label="เมนูหลัก"
        aria-hidden={!desktop && !mobileOpen}
      >
        <div
          className={cn(
            "shrink-0 flex items-center h-12 workspace-sidebar-header gemini-theme-transition",
            showLabels ? "px-4 gap-1.5 w-full" : "justify-center px-1.5"
          )}
        >
          {showLabels ? (
            <>
              <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
                <NeoLogo heightClass="h-5" />
                <span className="truncate text-xs font-semibold tracking-tight text-gemini-text dark:text-gemini-dark-text">
                  {getWorkspacePageTitle(pathname)}
                </span>
              </div>
              {onChat ? null : (
                <FactorySwitcher expanded={false} className="!p-0" />
              )}
              {desktop ? (
                <Tooltip content="ย่อแถบด้านข้างให้เหลือไอคอน" side="right">
                  <button
                    type="button"
                    onClick={onToggleExpanded}
                    className={cn(
                      iconOnlyBtn,
                      "sidebar-slide-fade",
                      richContent ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden"
                    )}
                    aria-label="ย่อแถบเมนู"
                  >
                    <PanelLeftClose className="h-4 w-4" />
                  </button>
                </Tooltip>
              ) : (
                <Tooltip content="ปิดเมนูนำทาง">
                  <button
                    type="button"
                    onClick={onMobileClose}
                    className={iconOnlyBtn}
                    aria-label="ปิด"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </Tooltip>
              )}
            </>
          ) : (
            <Tooltip content="ขยายแถบด้านข้างแสดงชื่อเมนู" side="right">
              <button
                type="button"
                onClick={onToggleExpanded}
                className="h-9 w-full max-w-full flex items-center justify-center rounded-lg hover:bg-gemini-hover gemini-focus-ring"
                aria-label="ขยายแถบเมนู"
              >
                <NeoLogo heightClass="h-5" />
              </button>
            </Tooltip>
          )}
        </div>

        {!onChat ? (
          <div
            className={cn(
              "shrink-0 overflow-hidden sidebar-slide-fade",
              showLabels
                ? "sidebar-slide-fade-visible px-2.5 pb-2 pt-1"
                : "sidebar-slide-fade-hidden hidden max-h-0 p-0"
            )}
          >
            <FactorySwitcher
              expanded
              className="!border-gemini-border/40 dark:!border-gemini-dark-border/40 !rounded-lg !text-xs"
            />
          </div>
        ) : null}

        <WorkspaceSidebarNav
          visibleItems={visibleItems}
          showLabels={showLabels}
          desktop={desktop}
          onChat={onChat}
          isActive={isActive}
          feedbackBadge={feedbackBadge}
          onMobileClose={onMobileClose}
        />

        <div className="shrink-0 overflow-visible px-2 pb-2.5 pt-2 workspace-sidebar-footer">
          <div
            className={cn(
              "sidebar-slide-fade space-y-2 w-full",
              showLabels ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden hidden"
            )}
          >
            <div className="flex items-center gap-1 min-w-0">
              <div className="flex-1 min-w-0">
                <AccountMenu username={username} showLabel collapsed={false} />
              </div>
              <Tooltip content="ตั้งค่าโมเดล AI และธีม">
                <button
                  type="button"
                  onClick={() => setSettingsOpen(true)}
                  className={iconOnlyBtn}
                  aria-label="ตั้งค่า"
                >
                  <SettingsIcon />
                </button>
              </Tooltip>
            </div>
          </div>
          <div
            className={cn(
              "flex flex-col items-center gap-2 w-full sidebar-slide-fade",
              !showLabels ? "sidebar-slide-fade-visible" : "sidebar-slide-fade-hidden hidden"
            )}
          >
            <Tooltip content="ตั้งค่าโมเดล AI และธีม" side="right">
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className={iconOnlyBtn}
                aria-label="ตั้งค่า"
              >
                <SettingsIcon />
              </button>
            </Tooltip>
            <AccountMenu username={username} showLabel={false} collapsed />
          </div>
        </div>
      </aside>
    </>
  );
}

function WorkspaceSidebarNav({
  visibleItems,
  showLabels,
  desktop,
  onChat,
  isActive,
  feedbackBadge,
  onMobileClose,
}: {
  visibleItems: WorkspaceNavItemConfig[];
  showLabels: boolean;
  desktop: boolean;
  onChat: boolean;
  isActive: (href: string) => boolean;
  feedbackBadge?: number;
  onMobileClose: () => void;
}) {
  return (
    <nav
      className={cn(
        "flex-1 min-h-0 flex flex-col overflow-hidden sidebar-nav-link",
        showLabels ? "px-2" : "px-1"
      )}
    >
      <div
        className={cn(
          "shrink-0 py-0.5 space-y-px",
          onChat ? "" : "overflow-y-auto gemini-scrollbar"
        )}
      >
        {visibleItems.map((item) => {
          if (item.href === "/chat") {
            return (
              <ChatNavSlot
                key={item.href}
                item={item}
                onChat={onChat}
                showLabels={showLabels}
                desktop={desktop}
                onMobileClose={onMobileClose}
              />
            );
          }

          return (
            <WorkspaceNavLink
              key={item.href}
              item={item}
              active={isActive(item.href)}
              badge={item.href === "/feedback" ? feedbackBadge : undefined}
              showLabels={showLabels}
              onNavigate={() => {
                if (!desktop) onMobileClose();
              }}
            />
          );
        })}
      </div>

      <div
        className={cn(
          "flex flex-col flex-1 min-h-0 overflow-hidden",
          (!onChat || !showLabels) && "hidden"
        )}
        aria-hidden={!onChat || !showLabels}
      >
        <Suspense fallback={null}>
          <WorkspaceChatSidebarPanelConnected
            showLabels={showLabels}
            desktop={desktop}
            onNavigate={onMobileClose}
          />
        </Suspense>
      </div>
    </nav>
  );
}

function WorkspaceChatSidebarPanelConnected(
  props: Omit<React.ComponentProps<typeof WorkspaceChatSidebarPanel>, "chat">
) {
  const chat = useChatSidebar({ enabled: true });
  return <WorkspaceChatSidebarPanel {...props} chat={chat} />;
}

function ChatNavSlot({
  item,
  onChat,
  showLabels,
  desktop,
  onMobileClose,
}: {
  item: WorkspaceNavItemConfig;
  onChat: boolean;
  showLabels: boolean;
  desktop: boolean;
  onMobileClose: () => void;
}) {
  if (onChat) {
    return (
      <Suspense fallback={<NewChatNavPlaceholder showLabels={showLabels} />}>
        <ChatNavSlotActive
          showLabels={showLabels}
          desktop={desktop}
          onMobileClose={onMobileClose}
        />
      </Suspense>
    );
  }

  return (
    <WorkspaceNavLink
      item={item}
      active={false}
      showLabels={showLabels}
      onNavigate={() => {
        if (!desktop) onMobileClose();
      }}
    />
  );
}

function NewChatNavPlaceholder({ showLabels }: { showLabels: boolean }) {
  return (
    <span
      className={cn(
        showLabels
          ? cn(navBtn, "workspace-nav-item-new-chat w-full font-medium opacity-70")
          : navBtnCollapsed
      )}
      aria-hidden
    >
      <span className="workspace-nav-item-icon shrink-0">
        {workspaceNavIcon("squarePen")}
      </span>
      {showLabels && <span className="truncate flex-1 text-left">แชทใหม่</span>}
    </span>
  );
}

function ChatNavSlotActive({
  showLabels,
  desktop,
  onMobileClose,
}: {
  showLabels: boolean;
  desktop: boolean;
  onMobileClose: () => void;
}) {
  const chat = useChatSidebar({ enabled: true });
  const newChatLabel = chat.creatingSession ? "กำลังสร้าง…" : "แชทใหม่";

  return (
    <Tooltip content={newChatLabel} side="right" disabled={showLabels}>
      <button
        type="button"
        disabled={chat.creatingSession}
        onClick={() => {
          window.dispatchEvent(new CustomEvent("spark:dismiss-overlays"));
          void chat.handleNewChat();
          if (!desktop) onMobileClose();
        }}
        className={cn(
          showLabels
            ? cn(navBtn, "workspace-nav-item-new-chat w-full font-medium")
            : navBtnCollapsed,
          chat.creatingSession && "opacity-60 cursor-wait"
        )}
        aria-current="page"
      >
        <span className="workspace-nav-item-icon shrink-0">
          {workspaceNavIcon("squarePen")}
        </span>
        {showLabels && (
          <span className="truncate flex-1 text-left">{newChatLabel}</span>
        )}
      </button>
    </Tooltip>
  );
}

function WorkspaceNavLink({
  item,
  active,
  badge,
  showLabels,
  onNavigate,
}: {
  item: WorkspaceNavItemConfig;
  active: boolean;
  badge?: number;
  showLabels: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Tooltip content={item.label} side="right" disabled={showLabels}>
      <Link
        href={item.href}
        onClick={() => {
          window.dispatchEvent(new CustomEvent("spark:dismiss-overlays"));
          if (item.href === "/system-admin") {
            rememberSystemAdminReturnPath();
          }
          onNavigate?.();
        }}
        className={cn(
          showLabels ? navBtn : navBtnCollapsed,
          active && "workspace-nav-item-active"
        )}
        aria-current={active ? "page" : undefined}
      >
        <span className="workspace-nav-item-icon">{workspaceNavIcon(item.icon)}</span>
        {showLabels && (
          <>
            <span className="truncate flex-1 text-left">
              {item.label}
            </span>
            {badge != null && badge > 0 && (
              <span className="shrink-0 min-w-[1.125rem] h-4 px-1 flex items-center justify-center rounded-full text-[9px] font-semibold bg-amber-500 text-white">
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </>
        )}
      </Link>
    </Tooltip>
  );
}

export function useWorkspaceSidebarState() {
  const [expanded, setExpanded] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(SIDEBAR_KEY);
    if (stored !== null) setExpanded(stored === "true");
  }, []);

  const toggleExpanded = () => {
    setExpanded((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_KEY, String(next));
      return next;
    });
  };

  return { expanded, mobileOpen, setMobileOpen, toggleExpanded };
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.26.604.852.997 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}
