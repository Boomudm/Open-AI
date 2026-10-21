"use client";

import {
  useWorkspaceSidebarState,
  WorkspaceSidebar,
} from "@/components/workspace/WorkspaceSidebar";
import { OfflineStatusBar } from "@/components/offline/OfflineStatusBar";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import { getWorkspacePageTitle } from "@/lib/workspaceNav";
import { useIsDesktopNav } from "@/hooks/useMediaQuery";
import { Menu } from "lucide-react";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

export function WorkspaceShell({ children }: { children: React.ReactNode }) {
  const desktop = useIsDesktopNav();
  const pathname = usePathname();
  const isChat = pathname.startsWith("/chat");
  const pageTitle = getWorkspacePageTitle(pathname);
  const { expanded, mobileOpen, setMobileOpen, toggleExpanded } = useWorkspaceSidebarState();
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (desktop) setMobileOpen(false);
  }, [desktop, setMobileOpen]);

  useEffect(() => {
    const openSidebar = () => setMobileOpen(true);
    window.addEventListener("spark:open-workspace-sidebar", openSidebar);
    return () => window.removeEventListener("spark:open-workspace-sidebar", openSidebar);
  }, [setMobileOpen]);

  useEffect(() => {
    if (!contentRef.current) return;
    contentRef.current.inert = !desktop && mobileOpen;
  }, [desktop, mobileOpen]);

  return (
    <div
      className={cn(
        "flex h-[100dvh] min-h-0 overflow-hidden bg-gemini-bg dark:bg-gemini-dark-bg gemini-theme-transition"
      )}
    >
      <WorkspaceSidebar
        desktop={desktop}
        expanded={expanded}
        onToggleExpanded={toggleExpanded}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      <div
        ref={contentRef}
        className={cn(
          "flex flex-col flex-1 min-w-0 min-h-0 chat-sidebar-content-shift",
          desktop && (expanded ? "ml-chat-sidebar" : "ml-chat-sidebar-collapsed")
        )}
      >
        <OfflineStatusBar />
        {!desktop && !isChat && (
          <header className="shrink-0 flex items-center h-12 px-3 border-b border-gemini-border/50 dark:border-gemini-dark-border/50">
            <Tooltip content="เปิดเมนูนำทาง">
              <button
                type="button"
                onClick={() => setMobileOpen(true)}
                className="h-11 w-11 touch-target flex items-center justify-center rounded-full hover:bg-gemini-hover text-gemini-muted gemini-focus-ring"
                aria-label="เปิดเมนู"
              >
                <Menu className="h-4 w-4" />
              </button>
            </Tooltip>
            <span className="ml-2 text-sm font-semibold text-gemini-text dark:text-gemini-dark-text truncate">
              {pageTitle}
            </span>
          </header>
        )}
        <div
          className={cn(
            "flex-1 min-h-0",
            isChat
              ? "overflow-hidden flex flex-col"
              : "overflow-y-auto gemini-scrollbar"
          )}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
