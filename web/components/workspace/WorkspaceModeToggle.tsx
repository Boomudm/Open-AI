"use client";

import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { LayoutDashboard, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

type WorkspaceModeToggleProps = {
  showLabel?: boolean;
  collapsed?: boolean;
  className?: string;
  onNavigate?: () => void;
};

/** Switch between AI chat and monitor dashboard (write users) or back to chat (read users). */
export function WorkspaceModeToggle({
  showLabel = true,
  collapsed = false,
  className,
  onNavigate,
}: WorkspaceModeToggleProps) {
  const pathname = usePathname();
  const canWrite = canWriteFactory(null);
  const onChat = pathname.startsWith("/chat");

  if (!canWrite) {
    if (onChat) return null;
    const label = "แชท AI";
    const hint = "เปิดแชท AI ถาม-ตอบ";
    return (
      <Tooltip content={hint} side="right" disabled={showLabel}>
        <Link
          href="/chat"
          onClick={() => {
            window.dispatchEvent(new CustomEvent("spark:dismiss-overlays"));
            onNavigate?.();
          }}
          aria-label={label}
        className={cn(
          "gemini-theme-transition gemini-focus-ring",
          showLabel
            ? "flex items-center gap-3 w-full h-10 px-3 rounded-xl text-sm font-medium"
            : "flex items-center justify-center h-10 w-10 mx-auto rounded-xl",
          "text-gemini-text dark:text-gemini-dark-text",
          "border border-gemini-border/50 dark:border-gemini-dark-border/50",
          "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
          className
        )}
      >
        <MessageSquare className="h-[18px] w-[18px] shrink-0 text-gemini-muted" strokeWidth={1.75} />
        {showLabel && <span className="truncate flex-1 text-left">{label}</span>}
      </Link>
      </Tooltip>
    );
  }

  const href = onChat ? "/dashboard" : "/chat";
  const label = onChat ? "Dashboard" : "แชท AI";
  const hint = onChat ? "ไปหน้าแดชบอร์ดวิเคราะห์โรงงาน" : "เปิดแชท AI ถาม-ตอบ";
  const Icon = onChat ? LayoutDashboard : MessageSquare;

  return (
    <Tooltip content={hint} side="right" disabled={showLabel}>
      <Link
        href={href}
        onClick={() => {
          window.dispatchEvent(new CustomEvent("spark:dismiss-overlays"));
          onNavigate?.();
        }}
        aria-label={label}
      className={cn(
        "gemini-theme-transition gemini-focus-ring",
        showLabel
          ? "flex items-center gap-3 w-full h-10 px-3 rounded-xl text-sm font-medium"
          : "flex items-center justify-center h-10 w-10 mx-auto rounded-xl",
        "text-gemini-text dark:text-gemini-dark-text",
        "border border-gemini-border/50 dark:border-gemini-dark-border/50",
        "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
        className
      )}
    >
      <Icon className="h-[18px] w-[18px] shrink-0 text-gemini-muted" strokeWidth={1.75} />
      {showLabel && <span className="truncate flex-1 text-left">{label}</span>}
    </Link>
    </Tooltip>
  );
}
