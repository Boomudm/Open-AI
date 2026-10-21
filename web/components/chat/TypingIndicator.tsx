import { cn } from "@/lib/cn";
import { Loader2 } from "lucide-react";

export function TypingIndicator({ label = "Thinking" }: { label?: string }) {
  return (
    <div className="flex justify-start w-full" aria-live="polite" aria-busy="true">
      <div className="flex items-start gap-2.5 mr-4 max-w-[85%]">
        <div
          className="shrink-0 h-8 w-8 rounded-sm border border-spark-accent/40 bg-spark-accent-muted flex items-center justify-center"
          aria-hidden
        >
          <Loader2 className="h-4 w-4 text-spark-accent animate-spin" />
        </div>
        <div className="spark-ai-bubble border border-spark-border rounded-spark-md px-3.5 py-2.5 min-w-[8rem]">
          <p className="font-mono text-[10px] uppercase tracking-wider text-spark-accent mb-1">
            Neo Chat · AI
          </p>
          <p className="font-mono text-sm text-spark-text-secondary">
            {label}
            <span className="typing-dots" aria-hidden />
          </p>
        </div>
      </div>
    </div>
  );
}

export function SessionInitLoader() {
  return (
    <div className={cn("flex items-center gap-2 font-mono text-xs text-spark-text-secondary")}>
      <Loader2 className="h-3.5 w-3.5 text-spark-accent animate-spin" aria-hidden />
      Initializing session
      <span className="typing-dots" aria-hidden />
    </div>
  );
}
