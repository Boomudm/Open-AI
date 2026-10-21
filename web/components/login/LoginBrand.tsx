import { Zap } from "lucide-react";

export function LoginBrand() {
  return (
    <div className="text-center space-y-3">
      <div className="inline-flex items-center justify-center h-14 w-14 rounded-spark-lg border border-spark-border bg-spark-surface">
        <Zap className="h-7 w-7 text-spark-accent" aria-hidden />
      </div>
      <div>
        <h1 className="font-mono text-2xl font-bold text-spark-text-primary tracking-tight">
          Neo Chat
        </h1>
        <p className="mt-1 text-[10px] font-mono text-spark-text-muted uppercase tracking-[0.2em]">
          Plant Operations
        </p>
      </div>
      <p className="text-xs font-sans text-spark-text-secondary max-w-xs mx-auto">
        Industrial AI — manuals, repair history, maintenance risk
      </p>
    </div>
  );
}
