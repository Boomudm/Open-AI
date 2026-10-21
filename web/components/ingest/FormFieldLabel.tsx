"use client";

import { cn } from "@/lib/cn";

type FormFieldLabelProps = {
  children: React.ReactNode;
  required?: boolean;
  htmlFor?: string;
  className?: string;
};

/** Label row with a consistent required / optional badge. */
export function FormFieldLabel({
  children,
  required = false,
  htmlFor,
  className,
}: FormFieldLabelProps) {
  return (
    <div className={cn("flex items-center justify-between gap-2", className)}>
      <span
        {...(htmlFor ? { id: `${htmlFor}-label` } : {})}
        className="text-sm text-gemini-muted dark:text-gemini-dark-muted"
      >
        {children}
      </span>
      <RequirementBadge required={required} />
    </div>
  );
}

export function RequirementBadge({ required }: { required: boolean }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-none",
        required
          ? "bg-amber-500/15 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
          : "bg-gemini-surface/80 text-gemini-muted dark:bg-gemini-dark-surface/80 dark:text-gemini-dark-muted"
      )}
      aria-hidden
    >
      {required ? "บังคับ" : "ไม่บังคับ"}
    </span>
  );
}
