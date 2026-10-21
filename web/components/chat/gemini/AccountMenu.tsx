"use client";

import { ClientPortal } from "@/components/ui/ClientPortal";
import { getUserEmail, getUserFullName, getUserPictureUrl, logoutSession } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import {
  formatUserDisplayName,
  resolveUserEmail,
  userInitials,
} from "@/lib/userDisplay";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

export type AccountMenuProps = {
  username: string;
  /** Sidebar shows text labels when expanded */
  showLabel?: boolean;
  /** Collapsed icon-only sidebar — popover opens to the right */
  collapsed?: boolean;
};

type MenuCoords = {
  left: number;
  top?: number;
  bottom?: number;
  maxHeight?: number;
};

export function AccountMenu({
  username,
  showLabel = true,
  collapsed = false,
}: AccountMenuProps) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [coords, setCoords] = useState<MenuCoords | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const displayName = getUserFullName() || formatUserDisplayName(username);
  const email = resolveUserEmail(getUserEmail());
  const pictureUrl = getUserPictureUrl();
  const initials = userInitials(displayName || username);

  const close = useCallback(() => setOpen(false), []);

  const updateCoords = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const panelWidth = Math.min(320, window.innerWidth - 16);
    const margin = 8;

    if (collapsed) {
      setCoords({
        left: Math.min(r.right + margin, window.innerWidth - panelWidth - margin),
        bottom: Math.max(margin, window.innerHeight - r.bottom),
      });
      return;
    }

    const spaceAbove = r.top - margin;
    const spaceBelow = window.innerHeight - r.bottom - margin;
    const preferAbove = spaceAbove >= spaceBelow;
    const left = Math.min(Math.max(margin, r.left), window.innerWidth - panelWidth - margin);

    if (preferAbove) {
      setCoords({
        left,
        bottom: window.innerHeight - r.top + margin,
        maxHeight: Math.max(160, spaceAbove - margin),
      });
    } else {
      setCoords({
        left,
        top: r.bottom + margin,
        maxHeight: Math.max(160, spaceBelow - margin),
      });
    }
  }, [collapsed]);

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
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  useEffect(() => {
    if (!open) return;
    const dismiss = () => close();
    window.addEventListener("spark:dismiss-overlays", dismiss);
    return () => window.removeEventListener("spark:dismiss-overlays", dismiss);
  }, [open, close]);

  const signOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    setOpen(false);
    try {
      await logoutSession(queryClient);
      window.location.assign("/login");
    } catch {
      window.location.assign("/login");
    }
  };

  const toggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next) {
        requestAnimationFrame(updateCoords);
      }
      return next;
    });
  };

  return (
    <div className="relative w-full">
      <button
        ref={triggerRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="เมนูบัญชี"
        className={cn(
          "gemini-theme-transition gemini-focus-ring w-full",
          showLabel
            ? "flex items-center gap-3 px-2 py-2 rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
            : "flex items-center justify-center h-10 w-10 mx-auto rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
        )}
      >
        <UserAvatar initials={initials} pictureUrl={pictureUrl} size={showLabel ? "md" : "sm"} />
        {showLabel && (
          <span className="flex-1 min-w-0 text-left">
            <span className="block text-sm font-medium text-gemini-text dark:text-gemini-dark-text truncate">
              {displayName}
            </span>
            {email && (
              <span className="block text-xs text-gemini-muted dark:text-gemini-dark-muted truncate">
                {email}
              </span>
            )}
          </span>
        )}
      </button>

      {open && coords && (
        <ClientPortal>
          <button
            type="button"
            aria-label="ปิดเมนูบัญชี"
            className="fixed inset-0 bg-transparent"
            style={{ zIndex: Z_OVERLAY_BACKDROP }}
            onClick={close}
          />
          <div
            role="dialog"
            aria-label="บัญชี"
            className={cn(
              "fixed w-[min(calc(100vw-2rem),320px)] gemini-theme-transition overflow-y-auto gemini-scrollbar",
              "transition-all duration-200 ease-out opacity-100 scale-100"
            )}
            style={{
              zIndex: Z_OVERLAY_PANEL,
              left: coords.left,
              top: coords.top,
              bottom: coords.bottom,
              maxHeight: coords.maxHeight,
            }}
          >
            <div
              className={cn(
                "rounded-3xl overflow-hidden shadow-xl",
                "bg-gemini-bg dark:bg-gemini-dark-surface",
                "border border-gemini-border/70 dark:border-gemini-dark-border/70"
              )}
            >
              <div className="flex flex-col items-center px-6 pt-7 pb-5 text-center">
                <UserAvatar initials={initials} pictureUrl={pictureUrl} size="lg" className="mb-4" />
                <p className="text-base font-medium text-gemini-text dark:text-gemini-dark-text">
                  {displayName}
                </p>
                {email && (
                  <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted mt-1 break-all">
                    {email}
                  </p>
                )}
              </div>

              <div className="border-t border-gemini-border/60 dark:border-gemini-dark-border/60" />

              <div className="p-4 space-y-2">
                <Link
                  href="/account"
                  onClick={close}
                  className={cn(
                    "flex items-center justify-center gap-2 w-full h-11 px-4 rounded-full",
                    "text-sm font-medium gemini-theme-transition gemini-focus-ring",
                    "border border-gemini-border dark:border-gemini-dark-border",
                    "text-gemini-text dark:text-gemini-dark-text",
                    "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
                  )}
                >
                  <UserRound className="h-4 w-4 shrink-0" aria-hidden />
                  ข้อมูลส่วนตัว
                </Link>
                <Link
                  href="/"
                  onClick={close}
                  className={cn(
                    "flex items-center justify-center gap-2 w-full h-11 px-4 rounded-full",
                    "text-sm font-medium gemini-theme-transition gemini-focus-ring",
                    "border border-gemini-border dark:border-gemini-dark-border",
                    "text-gemini-text dark:text-gemini-dark-text",
                    "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
                  )}
                >
                  ดูเว็บไซต์ Neo
                </Link>
                <Link
                  href="/login?switch=1"
                  onClick={close}
                  className={cn(
                    "flex items-center justify-center gap-2 w-full h-11 px-4 rounded-full",
                    "text-sm font-medium gemini-theme-transition gemini-focus-ring",
                    "border border-gemini-border dark:border-gemini-dark-border",
                    "text-gemini-text dark:text-gemini-dark-text",
                    "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
                  )}
                >
                  <UserRound className="h-4 w-4 shrink-0" aria-hidden />
                  เปลี่ยนบัญชี
                </Link>
                <button
                  type="button"
                  onClick={() => void signOut()}
                  disabled={signingOut}
                  className={cn(
                    "flex items-center justify-center gap-2 w-full h-11 px-4 rounded-full",
                    "text-sm font-medium gemini-theme-transition gemini-focus-ring",
                    "border border-gemini-border dark:border-gemini-dark-border",
                    "text-gemini-text dark:text-gemini-dark-text",
                    "hover:bg-red-50 dark:hover:bg-red-950/30 hover:text-red-600 dark:hover:text-red-400",
                    "hover:border-red-200 dark:hover:border-red-900/50",
                    "disabled:opacity-60 disabled:cursor-wait"
                  )}
                >
                  {signingOut ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin" aria-hidden />
                  ) : (
                    <LogOut className="h-4 w-4 shrink-0" aria-hidden />
                  )}
                  {signingOut ? "กำลังออกจากระบบ…" : "ออกจากระบบ"}
                </button>
              </div>
            </div>
          </div>
        </ClientPortal>
      )}
    </div>
  );
}

function UserAvatar({
  initials,
  pictureUrl,
  size = "md",
  className,
}: {
  initials: string;
  pictureUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const sizeClass =
    size === "lg" ? "h-16 w-16 text-xl" : size === "md" ? "h-9 w-9 text-sm" : "h-8 w-8 text-xs";

  if (pictureUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={pictureUrl}
        alt=""
        referrerPolicy="no-referrer"
        className={cn(
          "inline-flex shrink-0 rounded-full object-cover",
          "ring-2 ring-gemini-bg dark:ring-gemini-dark-sidebar shadow-sm",
          sizeClass,
          className
        )}
      />
    );
  }

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-medium text-white",
        "bg-gradient-to-br from-[#4285f4] via-[#a855f7] to-[#ec4899]",
        "ring-2 ring-gemini-bg dark:ring-gemini-dark-sidebar shadow-sm",
        sizeClass,
        className
      )}
      aria-hidden
    >
      {initials}
    </span>
  );
}
