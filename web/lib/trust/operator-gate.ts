/**
 * Operator gate — determines whether a message requires operator review
 * before being shown as trusted output.
 */

import type { OperatorTrustState } from "./types";

/** Intents that always trigger the operator gate. */
export const SAFETY_INTENTS: ReadonlySet<string> = new Set([
  "lockout_tagout",
  "chemical_handling",
  "confined_space",
  "electrical_safety",
  "high_voltage",
]);

/**
 * Check whether provisional (unverified) tokens are present in the stream,
 * meaning the response has not yet been citation-verified.
 */
export function hasProvisionalTokens(
  citationsVerified: boolean | undefined
): boolean {
  return citationsVerified === false;
}

/**
 * Evaluate whether a message requires an operator trust gate based on
 * confidence tier, intent, and citation verification status.
 */
export function requiresOperatorGate(opts: {
  confidence_tier?: "high" | "medium" | "low";
  intent?: string;
  citations_verified?: boolean;
  system_degradation?: boolean;
}): OperatorTrustState {
  const { confidence_tier, intent, citations_verified, system_degradation } =
    opts;

  // Safety intents always require operator gate
  if (intent && SAFETY_INTENTS.has(intent)) {
    return { requiresGate: true, reason: "safety_intent" };
  }

  // Degraded system always requires gate
  if (system_degradation) {
    return { requiresGate: true, reason: "system_degradation" };
  }

  // Low confidence requires gate
  if (confidence_tier === "low") {
    return { requiresGate: true, reason: "low_confidence" };
  }

  // Unverified citations require gate
  if (hasProvisionalTokens(citations_verified)) {
    return { requiresGate: true, reason: "unverified_citations" };
  }

  return { requiresGate: false };
}
