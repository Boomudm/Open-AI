/**
 * Web Vitals reporting — sends Core Web Vitals to the backend metrics endpoint.
 * Lazy-loaded in layout to avoid blocking initial render.
 */

type Metric = {
  name: string;
  value: number;
  rating: "good" | "needs-improvement" | "poor";
  id: string;
};

const VITALS_ENDPOINT = "/api/v1/observability/web-vitals";

function sendMetric(metric: Metric) {
  const body = JSON.stringify({
    name: metric.name,
    value: Math.round(metric.name === "CLS" ? metric.value * 1000 : metric.value),
    rating: metric.rating,
    page: typeof window !== "undefined" ? window.location.pathname : "",
  });

  if (typeof navigator !== "undefined" && navigator.sendBeacon) {
    navigator.sendBeacon(VITALS_ENDPOINT, body);
  } else {
    fetch(VITALS_ENDPOINT, {
      method: "POST",
      body,
      headers: { "Content-Type": "application/json" },
      keepalive: true,
    }).catch(() => {});
  }
}

export async function reportWebVitals() {
  try {
    const moduleName = "web-vitals";
    // Dynamic import with variable to bypass TypeScript module resolution
    const mod = await (Function("m", "return import(m)")(moduleName) as Promise<Record<string, unknown>>);
    const bind = (fn: unknown) => {
      if (typeof fn === "function") fn(sendMetric);
    };
    bind(mod.onCLS);
    bind(mod.onFID);
    bind(mod.onLCP);
    bind(mod.onFCP);
    bind(mod.onTTFB);
  } catch {
    // web-vitals not installed — graceful no-op
  }
}
