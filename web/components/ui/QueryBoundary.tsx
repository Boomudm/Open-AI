"use client";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui/State";
import { parseApiError } from "@/lib/errors";
import {
  MSG_FAILED_TO_LOAD,
  MSG_LOADING_DATA,
  MSG_NO_DATA,
  MSG_UNEXPECTED_ERROR,
} from "@/lib/messages.th";
import type { ReactNode } from "react";

type QueryBoundaryProps<T> = {
  query: {
    isLoading: boolean;
    isError: boolean;
    error: Error | null;
    refetch?: () => void | Promise<unknown>;
    data: T | undefined;
  };
  loadingMessage?: string;
  errorTitle?: string;
  emptyTitle?: string;
  emptyMessage?: string;
  /** When false, skip empty-state check (e.g. paginated lists that use [] as valid data). */
  treatEmptyArrayAsEmpty?: boolean;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
  className?: string;
};

function isEmptyData<T>(data: T, treatEmptyArrayAsEmpty: boolean): boolean {
  if (data === undefined || data === null) return true;
  if (treatEmptyArrayAsEmpty && Array.isArray(data) && data.length === 0) return true;
  return false;
}

/** Consistent loading, error, and empty states for React Query results. */
export function QueryBoundary<T>({
  query,
  loadingMessage = MSG_LOADING_DATA,
  errorTitle = MSG_FAILED_TO_LOAD,
  emptyTitle = MSG_NO_DATA,
  emptyMessage,
  treatEmptyArrayAsEmpty = false,
  onRetry,
  children,
  className,
}: QueryBoundaryProps<T>) {
  if (query.isLoading) {
    return <LoadingState message={loadingMessage} className={className} />;
  }
  if (query.isError) {
    const message =
      query.error instanceof Error ? parseApiError(query.error) : MSG_UNEXPECTED_ERROR;
    return (
      <ErrorState
        title={errorTitle}
        message={message}
        onRetry={onRetry ?? (() => void query.refetch?.())}
        className={className}
      />
    );
  }
  if (isEmptyData(query.data, treatEmptyArrayAsEmpty)) {
    return (
      <EmptyState title={emptyTitle} message={emptyMessage} className={className} />
    );
  }
  return <>{children(query.data as T)}</>;
}
