"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

function retryDelay(attemptIndex: number) {
  return Math.min(1000 * 2 ** attemptIndex, 10000);
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: true,
            retry: 2,
            retryDelay,
            staleTime: 30_000,
          },
          mutations: {
            retry: 1,
            retryDelay,
          },
        },
      })
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
