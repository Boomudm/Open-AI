import type { NocTipContent } from "@/components/system-admin/NocTip";
import type { SystemAdminDashboard } from "@/lib/api";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BarChart3,
  Database,
  FileCode,
  HardDrive,
  HeartPulse,
  Search,
} from "lucide-react";

export type NocDebugLink = {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  tip: NocTipContent;
  muted?: boolean;
};

/** Hostname the operator is actually browsing from — consoles run on the same
 * box, so linking to that host works from remote browsers too (hardcoded
 * localhost only worked when browsing on the server itself). */
function consoleHost(): string {
  if (typeof window !== "undefined" && window.location?.hostname) {
    return window.location.hostname;
  }
  return "localhost";
}

function apiOrigin(): string {
  const fromEnv = process.env.NEXT_PUBLIC_SPARK_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  return `http://${consoleHost()}:8000`;
}

function qdrantDashboardUrl(host: unknown): string {
  const raw = String(host ?? `${consoleHost()}:6333`).trim();
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return `${raw.replace(/\/$/, "")}/dashboard`;
  }
  // Backend reports its in-cluster hostname (e.g. "qdrant:6333") which the
  // browser can't resolve — keep the real port but reach it via the page host.
  const port = raw.includes(":") ? raw.split(":").pop() : "6333";
  return `http://${consoleHost()}:${port}/dashboard`;
}

/** External debug / ops consoles for super-admin. */
export function buildNocDebugLinks(data: SystemAdminDashboard, promUp: boolean): NocDebugLink[] {
  const api = apiOrigin();
  const host = consoleHost();
  const qHost = (data.qdrant as Record<string, unknown> | undefined)?.host;
  const otelOn = Boolean((data.otel_tracing as Record<string, unknown> | undefined)?.enabled);
  const qdrantHref = qdrantDashboardUrl(qHost);
  const minioHref = `http://${host}:9001`;
  const promHref = `http://${host}:9090`;
  const grafanaHref = `http://${host}:3001`;
  const jaegerHref = `http://${host}:16686`;

  return [
    {
      id: "qdrant",
      label: "Qdrant",
      href: qdrantHref,
      icon: Database,
      tip: { title: "Qdrant", lines: [qdrantHref, `Backend เชื่อมที่ ${String(qHost ?? "qdrant:6333")}`, "Collections · vectors · cluster"] },
    },
    {
      id: "minio",
      label: "MinIO",
      href: minioHref,
      icon: HardDrive,
      tip: { title: "MinIO Console", lines: [minioHref, "Object storage · S3 buckets"] },
    },
    {
      id: "prometheus",
      label: "Prom",
      href: promHref,
      icon: Activity,
      muted: !promUp,
      tip: {
        title: "Prometheus",
        lines: [promUp ? "Scrape พร้อม" : "อาจยังไม่รัน — docker observability", promHref],
      },
    },
    {
      id: "grafana",
      label: "Grafana",
      href: grafanaHref,
      icon: BarChart3,
      tip: { title: "Grafana", lines: ["RAG SLO / spark dashboards", grafanaHref] },
    },
    {
      id: "jaeger",
      label: "Jaeger",
      href: jaegerHref,
      icon: Search,
      muted: !otelOn,
      tip: {
        title: "Jaeger",
        lines: [otelOn ? "OTEL tracing เปิด" : "Tracing ปิด — ตั้ง OTEL_EXPORTER", jaegerHref],
      },
    },
    {
      id: "api-docs",
      label: "API",
      href: `${api}/docs`,
      icon: FileCode,
      tip: { title: "Swagger", lines: ["OpenAPI UI", `${api}/docs`] },
    },
    {
      id: "readyz",
      label: "Ready",
      href: `${api}/readyz`,
      icon: HeartPulse,
      tip: { title: "/readyz", lines: ["DB · Redis · Celery · LLM probe", `${api}/readyz`] },
    },
  ];
}
