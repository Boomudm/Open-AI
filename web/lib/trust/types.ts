/**
 * Trust-layer types shared across operator gate and message mapping.
 */

export type OperatorTrustState = {
  requiresGate: boolean;
  reason?: string;
  confidence_tier?: "high" | "medium" | "low";
  citations_verified?: boolean;
  system_degradation?: boolean;
  cache_hit?: boolean;
};
