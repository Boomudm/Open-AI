import type { QueryClient } from "@tanstack/react-query";

/** Drop cached factory-scoped data and refetch active queries. */
export function invalidateFactoryScopedQueries(queryClient: QueryClient): void {
  const keys = [
    ["machines"],
    ["dashboard"],
    ["atRisk"],
    ["repairs"],
    ["spareParts"],
    ["inventoryInsights"],
    ["inventoryStockValue"],
    ["ingestJobs"],
    ["documents"],
    ["handover"],
    ["chatSessions"],
    ["chatMessages"],
  ] as const;
  for (const queryKey of keys) {
    queryClient.resetQueries({ queryKey });
  }
}
