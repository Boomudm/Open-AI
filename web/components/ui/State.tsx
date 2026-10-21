import {
  LABEL_RETRY,
  MSG_FAILED_TO_LOAD,
  MSG_LOADING,
  MSG_LOADING_DATA,
  MSG_NO_DATA,
} from "@/lib/messages.th";
import { cn } from "@/lib/cn";
import { AlertTriangle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export function Spinner({ className, label = MSG_LOADING }: { className?: string; label?: string }) {
  return (
    <div
      className={cn("flex items-center justify-center gap-2", className)}
      role="status"
      aria-label={label}
    >
      <RefreshCw className="h-4 w-4 text-spark-accent animate-spin" aria-hidden />
      <span className="font-mono text-xs text-spark-text-secondary typing-dots">
        {label}
      </span>
    </div>
  );
}

export function LoadingState({
  message = MSG_LOADING_DATA,
  className,
}: {
  message?: string;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-12",
        "border border-spark-border rounded-sm bg-spark-surface",
        className
      )}
    >
      <Spinner label={message} />
    </div>
  );
}

export function ErrorState({
  title = MSG_FAILED_TO_LOAD,
  message,
  onRetry,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-12 px-6 text-center",
        "border border-spark-critical/30 rounded-sm bg-spark-critical-muted/20",
        className
      )}
      role="alert"
    >
      <AlertTriangle className="h-5 w-5 text-spark-critical" aria-hidden />
      <div>
        <p className="font-mono text-sm font-semibold text-spark-text-primary">{title}</p>
        {message && (
          <p className="text-xs text-spark-text-secondary mt-1 font-sans max-w-md">
            {message}
          </p>
        )}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} leftIcon={<RefreshCw className="h-3 w-3" />}>
          {LABEL_RETRY}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title = MSG_NO_DATA,
  message,
  className,
  children,
}: {
  title?: string;
  message?: string;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 py-10 px-6 text-center",
        "border border-dashed border-spark-border rounded-sm",
        className
      )}
    >
      <p className="font-mono text-sm text-spark-text-secondary">{title}</p>
      {message && (
        <p className="text-xs text-spark-text-muted font-sans">{message}</p>
      )}
      {children}
    </div>
  );
}
