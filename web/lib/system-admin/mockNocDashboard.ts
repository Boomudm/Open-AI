import type { SystemAdminDashboard } from "@/lib/api";

export type NocMockMode = "off" | "healthy" | "degraded";

/** Parse mock mode from URL: ?mock=1 (healthy), ?mock=degraded, ?mock=0 (off) */
export function parseNocMockMode(search: string): NocMockMode {
  const params = new URLSearchParams(search);
  const raw = params.get("mock");
  if (raw === "0" || raw === "off" || raw === "false") return "off";
  if (raw === "degraded" || raw === "alert" || raw === "warn") return "degraded";
  if (raw === "1" || raw === "true" || raw === "healthy") return "healthy";
  return "off";
}

function lastNDays(n: number): string[] {
  const out: string[] = [];
  const today = new Date();
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(today.getUTCDate() - i);
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}

function dailySeries(base: number, growth: number, wobble = 0.15): Array<{ date: string; value: number }> {
  return lastNDays(7).map((date, i) => ({
    date,
    value: Math.max(0, Math.round(base + (growth * i) / 6 + Math.sin(i * 1.4) * base * wobble)),
  }));
}

function hourlySeries(base: number, amplitude: number): Array<{ ts: number; label: string; value: number }> {
  const now = new Date();
  now.setUTCMinutes(0, 0, 0);
  const points: Array<{ ts: number; label: string; value: number }> = [];
  for (let i = 23; i >= 0; i--) {
    const h = new Date(now);
    h.setUTCHours(now.getUTCHours() - i);
    const hour = h.getUTCHours();
    // Factory shift pattern: peaks 8–11 and 13–17
    const shift =
      (hour >= 8 && hour <= 11 ? 1.4 : 0) +
      (hour >= 13 && hour <= 17 ? 1.6 : 0) +
      (hour >= 0 && hour <= 5 ? 0.15 : 0.5);
    const value = Math.max(0.01, base * shift + Math.sin(i / 3) * amplitude);
    points.push({
      ts: Math.floor(h.getTime() / 1000),
      label: h.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", hour12: false }),
      value: Math.round(value * 1000) / 1000,
    });
  }
  return points;
}

function tokenSplitFromDaily(
  messages: Array<{ date: string; value: number }>
): Array<{ date: string; prompt: number; completion: number }> {
  return messages.map(({ date, value }) => ({
    date,
    prompt: Math.round(value * 42 * 0.62),
    completion: Math.round(value * 42 * 0.38),
  }));
}

/** Realistic demo snapshot for control-room preview. */
export function buildMockNocDashboard(
  real: SystemAdminDashboard,
  mode: NocMockMode
): SystemAdminDashboard {
  if (mode === "off") return real;

  const now = new Date().toISOString();
  const dailyMessages = dailySeries(48, 35, 0.22);
  const dailyUsers = dailySeries(12, 8, 0.18);
  const dailySessions = dailySeries(22, 14, 0.2);
  const dailyIngest = dailySeries(3, 5, 0.35);
  const dailyTokens = dailyMessages.map(({ date, value }) => ({
    date,
    value: value * 180,
  }));
  const tokenSplit = tokenSplitFromDaily(dailyMessages);
  const hourlyReq = hourlySeries(2.4, 0.8);
  const hourlyMsgs = hourlySeries(18, 6);
  const hourlyUsers = hourlySeries(4, 2);
  const hourlyLat = hourlySeries(120, 35).map((p) => ({ ...p, value: Math.round(p.value) }));

  const degraded = mode === "degraded";

  const connectivity = degraded
    ? [
        { name: "postgres", ok: true, degraded: false },
        { name: "redis", ok: true, degraded: false },
        { name: "qdrant", ok: true, degraded: false },
        { name: "llm", ok: true, degraded: false },
        { name: "storage", ok: false, degraded: false, error: "disk quota warning" },
        { name: "celery", ok: true, degraded: false },
      ]
    : [
        { name: "postgres", ok: true, degraded: false },
        { name: "redis", ok: true, degraded: false },
        { name: "qdrant", ok: true, degraded: false },
        { name: "llm", ok: true, degraded: false },
        { name: "storage", ok: true, degraded: false },
        { name: "celery", ok: true, degraded: false },
      ];

  const promptTotal = tokenSplit.reduce((a, d) => a + d.prompt, 0);
  const complTotal = tokenSplit.reduce((a, d) => a + d.completion, 0);

  return {
    ...real,
    generated_at: now,
    traffic: {
      requests_per_sec: 2.38,
      p95_latency_sec: 0.142,
      prometheus_available: true,
      error_rate_5xx: 0.002,
      sse_connections: degraded ? 6 : 14,
      active_users: 8,
      active_sessions_15m: 12,
      messages_24h: 186,
    },
    llm_usage: {
      window_hours: 24,
      prompt_tokens_est: Math.round(promptTotal * 0.35),
      completion_tokens_est: Math.round(complTotal * 0.35),
      embedding_tokens_est: 12400,
      estimated_cost_usd: 0.0842,
      estimated_cost_thb: 2.7786,
      usd_thb_rate: 33,
      cost_breakdown_usd: { prompt: 0.041, completion: 0.0312, embedding: 0.012 },
      cost_breakdown_thb: { prompt: 1.353, completion: 1.0296, embedding: 0.396 },
      message_count: 186,
    },
    users: {
      total_registered: 47,
      active_accounts: 44,
      super_admins: 2,
      active_users_15m: 8,
      active_users_1h: 14,
      active_users_24h: 23,
      active_sessions_15m: 12,
    },
    timeseries: {
      days: 7,
      daily_active_users: dailyUsers,
      daily_sessions: dailySessions,
      daily_tokens_est: dailyTokens,
      daily_messages: dailyMessages,
      daily_ingest_jobs: dailyIngest,
      daily_token_split: tokenSplit,
      hourly_messages: hourlyMsgs,
      hourly_active_users: hourlyUsers,
      hourly_requests: hourlyReq,
      hourly_latency_ms: hourlyLat,
      ingest_by_status: degraded
        ? [
            { label: "queued", value: 12 },
            { label: "running", value: 3 },
            { label: "completed", value: 128 },
            { label: "failed", value: 2 },
          ]
        : [
            { label: "queued", value: 4 },
            { label: "running", value: 2 },
            { label: "completed", value: 156 },
            { label: "failed", value: 0 },
          ],
    },
    health_summary: {
      status: degraded ? "not_ready" : "ready",
      overall_ok: !degraded,
      http_status: degraded ? 503 : 200,
      connectivity,
      failed_count: degraded ? 1 : 0,
      degraded_count: 0,
    },
    qdrant: {
      available: true,
      host: "localhost:6333",
      shard_strategy: "factory",
      postgres_chunks_total: 18420,
      qdrant_points_total: 18398,
      chunk_drift: degraded ? 22 : 2,
      chunk_drift_alert: degraded,
      collections: [{ name: "spark_docs", points_count: 18398, status: "green" }],
    },
    postgres: {
      pool_size: 10,
      max_overflow: 10,
      pool_capacity: 20,
      pool_checked_out: 3,
      pool_checked_in: 7,
      pool_overflow_in_use: 0,
      pool_status: "Pool size: 10  Connections in pool: 3  Current Overflow: 0",
      locks: degraded
        ? [
            { mode: "AccessShareLock", cnt: 4 },
            { mode: "RowExclusiveLock", cnt: 2 },
          ]
        : [{ mode: "AccessShareLock", cnt: 4 }],
      slow_queries: degraded
        ? [{ query: "SELECT ... FROM chunks", duration_sec: 2.4, pid: 1234 }]
        : [],
    },
    storage: {
      backend: "local",
      document_count: 312,
      document_gib: 2.84,
      health: { ok: !degraded },
    },
    workers: {
      celery: { ok: true, workers: 2, worker_names: ["celery@worker-1", "celery@worker-2"] },
      ingest_queue_backlog: degraded ? 70 : 6,
      celery_broker_queue_depth: degraded ? 3 : 0,
      failed_ingest_jobs: degraded ? 2 : 0,
      ingestion_error_rows: degraded ? 1 : 0,
    },
    agentic_circuit: {
      open: false,
      routing_mode: "legacy",
      canary_pct: 10,
      flag: null,
    },
    rag_circuit: {
      open: false,
      flag: null,
      window_sec: 600,
    },
    llm_gateway: {
      llm_profile: "demo",
      llm_model: "qwen2.5:3b-instruct",
      embed_model: "BAAI/bge-m3",
      healthy: true,
      checks: {
        ollama: { ok: true, status: 200 },
        embedding_dim: { ok: true, qdrant_dim: 1024, profile_dim: 1024 },
      },
    },
    maintenance: { enabled: false },
    semantic_cache: {
      enabled: true,
      hit_rate_pct: 34.2,
      total_cache_entries: 89,
      entries_with_embedding: 76,
    },
    shadow_routing: { active: false, routing_mode: "legacy" },
    otel_tracing: { enabled: false, service_name: "spark-api" },
    eval_quality: degraded
      ? { has_report: true, gate_passed: false, report_path: "reports/ci_eval_report.json" }
      : { has_report: true, gate_passed: true, report_path: "reports/ci_eval_report.json" },
    embed_shadow: { enabled: false },
    incidents: degraded
      ? [
          { severity: "critical", title: "Storage unavailable", detail: "disk quota warning", source: "connectivity", at: now },
          { severity: "warn", title: "Ingest queue backlog: 70", detail: "consider scaling workers", source: "workers", at: now },
          { severity: "warn", title: "Chunk drift: 22", detail: "run Qdrant sync from Actions", source: "qdrant", at: now },
          { severity: "warn", title: "Failed ingest jobs: 2", detail: "inspect ingest logs / admin ingest", source: "workers", at: now },
          { severity: "warn", title: "Eval quality gate FAILED", detail: "see reports/ci_eval_report.json", source: "eval", at: now },
        ]
      : [
          { severity: "info", title: "All systems operational", detail: "6 connectivity checks OK", source: "system", at: now },
        ],
    active_users_window_minutes: 15,
    active_users_since: now,
  };
}
