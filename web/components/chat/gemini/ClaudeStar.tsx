import { cn } from "@/lib/cn";

type ClaudeStarProps = {
  className?: string;
  title?: string;
};

/** Claude-style 8-point asterisk used during pondering / thinking. */
export function ClaudeStar({ className, title }: ClaudeStarProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("h-[1.125rem] w-[1.125rem] shrink-0", className)}
      fill="currentColor"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      <path d="M12 1.6c.28 0 .52.18.6.45l1.55 5.2a1.2 1.2 0 0 0 .72.72l5.2 1.55a.62.62 0 0 1 0 1.2l-5.2 1.55a1.2 1.2 0 0 0-.72.72l-1.55 5.2a.62.62 0 0 1-1.2 0l-1.55-5.2a1.2 1.2 0 0 0-.72-.72l-5.2-1.55a.62.62 0 0 1 0-1.2l5.2-1.55a1.2 1.2 0 0 0 .72-.72l1.55-5.2A.62.62 0 0 1 12 1.6Z" />
    </svg>
  );
}
