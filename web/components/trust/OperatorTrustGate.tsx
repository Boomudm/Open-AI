"use client";

import { requiresOperatorGate } from "@/lib/trust/operator-gate";
import type { ReactNode } from "react";

type OperatorTrustGateProps = {
  confidence_tier?: "high" | "medium" | "low";
  intent?: string;
  citations_verified?: boolean;
  system_degradation?: boolean;
  children: ReactNode;
  fallback?: ReactNode;
};

/**
 * Wraps content that should only render when operator trust requirements are met.
 * When the gate triggers, shows the fallback (a warning banner) instead of the children.
 */
export function OperatorTrustGate({
  confidence_tier,
  intent,
  citations_verified,
  system_degradation,
  children,
  fallback,
}: OperatorTrustGateProps) {
  const trust = requiresOperatorGate({
    confidence_tier,
    intent,
    citations_verified,
    system_degradation,
  });

  if (trust.requiresGate && fallback) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
