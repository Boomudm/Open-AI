"use client";

import { Tooltip } from "@/components/ui/Tooltip";
import { Menu } from "lucide-react";

const headerIconBtn =
  "h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover hover:text-gemini-text dark:hover:text-gemini-dark-text";

export type ChatHeaderProps = {
  desktop: boolean;
  machineId: string | null;
  onOpenSidebar: () => void;
  onOpenRca?: () => void;
  emptyChat?: boolean;
};

export function ChatHeader({ desktop, onOpenSidebar }: ChatHeaderProps) {
  if (desktop) {
    return <header className="relative z-[2] h-12 shrink-0" aria-hidden />;
  }

  return (
    <header className="relative z-[2] flex h-12 shrink-0 items-center gap-2 px-3 gemini-theme-transition">
      <Tooltip content="เปิดรายการแชท">
        <button
          type="button"
          onClick={onOpenSidebar}
          className={headerIconBtn}
          aria-label="เปิดเมนู"
        >
          <Menu className="h-4 w-4" />
        </button>
      </Tooltip>
    </header>
  );
}
