export type KpiDelta = {
  value: number;
  direction: "up" | "down" | "neutral";
};

/** Controls whether an increase is good, bad, or neutral for delta badge color. */
export type KpiMetricKind = "repairs" | "downtime" | "stock_value" | "cost";

export type KpiDeltaFormat = "count" | "hours" | "currency";

export function buildKpiDelta(current: number, prior: number | null | undefined): KpiDelta | undefined {
  if (prior == null || !Number.isFinite(prior) || !Number.isFinite(current)) {
    return undefined;
  }

  const diff = current - prior;
  const direction: KpiDelta["direction"] =
    diff > 0 ? "up" : diff < 0 ? "down" : "neutral";

  return { value: diff, direction };
}

export function deltaTone(
  delta: KpiDelta,
  metric: KpiMetricKind
): "good" | "bad" | "neutral" {
  if (metric === "stock_value" || metric === "cost") return "neutral";
  if (delta.direction === "neutral") return "neutral";

  const increaseIsBad = metric === "repairs" || metric === "downtime";
  if (delta.direction === "up") {
    return increaseIsBad ? "bad" : "good";
  }
  return increaseIsBad ? "good" : "bad";
}

export function formatDeltaLabel(
  delta: KpiDelta,
  format: KpiDeltaFormat,
  options?: { suffix?: string }
): string {
  const arrow = delta.direction === "up" ? "↑" : delta.direction === "down" ? "↓" : "→";
  const suffix = options?.suffix ?? " vs last month";

  if (format === "hours") {
    if (delta.value === 0) return `${arrow} 0h${suffix}`;
    const signed = `${delta.value > 0 ? "+" : ""}${delta.value.toFixed(1)}h`;
    return `${arrow} ${signed}${suffix}`;
  }

  if (format === "currency") {
    if (delta.value === 0) return `${arrow} ฿0${suffix}`;
    const formatted = Math.abs(delta.value).toLocaleString("th-TH", {
      maximumFractionDigits: 0,
    });
    const signed = `${delta.value > 0 ? "+" : "-"}฿${formatted}`;
    return `${arrow} ${signed}${suffix}`;
  }

  if (delta.value === 0) return `${arrow} 0${suffix}`;
  const signed = `${delta.value > 0 ? "+" : ""}${Math.round(delta.value)}`;
  return `${arrow} ${signed}${suffix}`;
}

export function deltaBadgeClass(tone: "good" | "bad" | "neutral"): string {
  if (tone === "good") return "text-spark-success";
  if (tone === "bad") return "text-spark-critical";
  return "text-spark-text-muted";
}

/** ISO date (YYYY-MM-DD) for N days ago from today (UTC calendar day). */
export function daysAgoIso(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export const REPAIR_PERIOD_WINDOWS = {
  current: { date_from: daysAgoIso(30), date_to: todayIso() },
  prior: { date_from: daysAgoIso(60), date_to: daysAgoIso(30) },
} as const;
