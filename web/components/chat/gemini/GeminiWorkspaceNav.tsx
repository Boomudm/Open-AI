"use client";

import { canWriteFactory, isAdminUser } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";
import { FolderOpen, LayoutDashboard, MessageSquare, Shield } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense } from "react";

type GeminiWorkspaceNavProps = {
  className?: string;
  compact?: boolean;
  onNavigate?: () => void;
};

const tabClass = cn(
  "inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium gemini-theme-transition gemini-focus-ring",
  "text-gemini-muted dark:text-gemini-dark-muted",
  "hover:text-gemini-text dark:hover:text-gemini-dark-text hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
);

const activeTabClass =
  "bg-gemini-blue dark:bg-gemini-dark-blue text-white hover:text-white hover:bg-gemini-blue dark:hover:bg-gemini-dark-blue";

export function GeminiWorkspaceNav(props: GeminiWorkspaceNavProps) {
  return (
    <Suspense
      fallback={
        <div
          className={cn(
            "h-8 w-28 rounded-xl bg-gemini-hover/50 dark:bg-gemini-dark-hover/50 animate-pulse",
            props.className
          )}
          aria-hidden
        />
      }
    >
      <GeminiWorkspaceNavInner {...props} />
    </Suspense>
  );
}

function GeminiWorkspaceNavInner({
  className,
  compact = false,
  onNavigate,
}: GeminiWorkspaceNavProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const canWrite = canWriteFactory(selectedFactoryId) || isAdminUser();

  const onChat = pathname.startsWith("/chat") && searchParams.get("view") !== "feedback";
  const onDashboard = pathname.startsWith("/dashboard");
  const onAdmin = pathname.startsWith("/admin");

  return (
    <nav
      className={cn(
        "inline-flex rounded-xl border border-gemini-border/60 dark:border-gemini-dark-border/60 overflow-hidden",
        className
      )}
      aria-label="สลับหน้างาน"
    >
      {canWrite && (
        <Link
          href="/dashboard"
          onClick={onNavigate}
          className={cn(tabClass, onDashboard && activeTabClass, compact && "px-2.5")}
          aria-current={onDashboard ? "page" : undefined}
        >
          <LayoutDashboard className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {!compact && "แนวโน้มปัญหา"}
        </Link>
      )}
      <Link
        href="/chat"
        onClick={onNavigate}
        className={cn(tabClass, onChat && activeTabClass, compact && "px-2.5")}
        aria-current={onChat ? "page" : undefined}
      >
        <MessageSquare className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {!compact && "แชท AI"}
      </Link>
      <Link
        href="/documents"
        onClick={onNavigate}
        className={cn(tabClass, pathname.startsWith("/documents") && activeTabClass, compact && "px-2.5")}
        aria-current={pathname.startsWith("/documents") ? "page" : undefined}
      >
        <FolderOpen className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {!compact && "เอกสาร"}
      </Link>
      {isAdminUser() && (
        <Link
          href="/admin"
          onClick={onNavigate}
          className={cn(tabClass, onAdmin && activeTabClass, compact && "px-2.5")}
          aria-current={onAdmin ? "page" : undefined}
        >
          <Shield className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {!compact && "ผู้ดูแล"}
        </Link>
      )}
    </nav>
  );
}
