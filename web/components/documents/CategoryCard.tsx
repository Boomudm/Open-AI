"use client";

import { cn } from "@/lib/cn";
import type { LucideIcon } from "lucide-react";

export type CategoryCardProps = {
  icon: LucideIcon;
  label: string;
  description: string;
  countLabel: string;
  onClick: () => void;
  className?: string;
};

export function CategoryCard({
  icon: Icon,
  label,
  description,
  countLabel,
  onClick,
  className,
}: CategoryCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "text-left p-4 rounded-2xl gemini-theme-transition w-full",
        "border border-gemini-border/70 dark:border-gemini-dark-border/70",
        "bg-gemini-surface dark:bg-gemini-dark-surface",
        "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-gemini-blue/40",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <div className="shrink-0 h-10 w-10 rounded-xl flex items-center justify-center bg-gemini-blue/10 dark:bg-gemini-dark-blue/20 text-gemini-blue dark:text-gemini-dark-blue">
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">
            {label}
          </p>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5 line-clamp-2">
            {description}
          </p>
          <p className="text-[11px] text-gemini-blue dark:text-gemini-dark-blue mt-2 font-medium">
            {countLabel}
          </p>
        </div>
      </div>
    </button>
  );
}
