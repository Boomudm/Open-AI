import { cn } from "@/lib/cn";

/** Google Gemini four-point star mark */
export function GeminiSparkle({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cn("h-6 w-6 shrink-0", className)}
      aria-hidden
    >
      <defs>
        <linearGradient id="gemini-sparkle-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#4285f4" />
          <stop offset="35%" stopColor="#34a853" />
          <stop offset="65%" stopColor="#fbbc04" />
          <stop offset="100%" stopColor="#ea4335" />
        </linearGradient>
      </defs>
      <path
        fill="url(#gemini-sparkle-grad)"
        d="M12 2.2 14.1 9.4 21.3 11.5 14.1 13.6 12 20.8 9.9 13.6 2.7 11.5 9.9 9.4z"
      />
    </svg>
  );
}
