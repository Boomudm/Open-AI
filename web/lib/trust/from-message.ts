/**
 * Map ChatMsg / SSE stream parts to OperatorTrustState.
 */

import type { OperatorTrustState } from "./types";
import { requiresOperatorGate } from "./operator-gate";
import type { ChatMsg } from "@/lib/chat";
import type { ChatSseDonePayload, ChatSseSourcesPayload } from "@/lib/chat/sse-types";

/**
 * Derive operator trust state from a fully-resolved ChatMsg.
 * Reads: confidence_tier, citations_verified, retrieval_report,
 *        system_degradation, cache_hit.
 */
export function operatorTrustFromMessage(msg: ChatMsg): OperatorTrustState {
  const degraded = msg.retrieval_report?.degraded ?? false;
  const state = requiresOperatorGate({
    confidence_tier: msg.confidence_tier,
    citations_verified: msg.citations_verified,
    system_degradation: msg.system_degradation ?? degraded,
  });

  return {
    ...state,
    confidence_tier: msg.confidence_tier,
    citations_verified: msg.citations_verified,
    system_degradation: msg.system_degradation ?? degraded,
    cache_hit: msg.cache_hit,
  };
}

/**
 * Build trust state from SSE stream parts that arrive incrementally.
 * Called when done + sources payloads are available.
 */
export function operatorTrustFromStreamParts(
  done: ChatSseDonePayload,
  sources?: ChatSseSourcesPayload | null
): OperatorTrustState {
  const degraded = sources?.retrieval_report?.degraded ?? false;
  const state = requiresOperatorGate({
    confidence_tier: done.confidence_tier,
    citations_verified: (done as Record<string, unknown>).citations_verified as
      | boolean
      | undefined,
    system_degradation: degraded,
  });

  return {
    ...state,
    confidence_tier: done.confidence_tier,
    citations_verified: (done as Record<string, unknown>).citations_verified as
      | boolean
      | undefined,
    system_degradation: degraded,
    cache_hit: done.cache_hit,
  };
}

/**
 * Alias kept for backward-compat — checks if a message needs the operator warning.
 */
export function trustRequiresOperatorWarning(msg: ChatMsg): boolean {
  return operatorTrustFromMessage(msg).requiresGate;
}
