"use client";

import {
  GrafanaBarChart,
  GrafanaDonut,
  GrafanaIngestBars,
  GrafanaPanel,
  GrafanaStackedBars,
  GrafanaStat,
  GrafanaTimeSeries,
  LegendDot,
  type IngestStatusPoint,
  type SplitPoint,
} from "@/components/system-admin/NocCharts";
import { assessNocHealth, SparkNocGuardian } from "@/components/system-admin/NeoNocGuardian";
import { NocDebugLinks } from "@/components/system-admin/NocDebugLinks";
import { NocIncidentStrip } from "@/components/system-admin/NocIncidentStrip";
import { NocTip, type NocTipContent } from "@/components/system-admin/NocTip";
import { api, type SystemActionResult, type SystemAdminDashboard } from "@/lib/api";
import { buildMockNocDashboard, parseNocMockMode, type NocMockMode } from "@/lib/system-admin/mockNocDashboard";
import { getSystemAdminReturnPath } from "@/lib/system-admin/nocNavigation";
import { buildNocContext, costInThb, fmtThb, NOC_TIPS } from "@/lib/system-admin/nocTooltips";
import { STALE_REALTIME } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, Shield, Tv } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type ServiceStatus = { name: string; ok: boolean; degraded?: boolean; detail?: string };

function num(v: unknown, fb = 0) {
  return typeof v === "number" && Number.isFinite(v) ? v : fb;
}

function fmt(v: unknown, d = 0) {
  const n = num(v, NaN);
  if (!Number.isFinite(n)) return "0";
  const decimals = Math.min(20, Math.max(0, Math.trunc(d)));
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(Math.min(1, decimals))}M`;
  if (n >= 10_000) return `${(n / 1_000).toFixed(Math.min(1, decimals))}k`;
  return decimals === 0 ? String(Math.round(n)) : n.toFixed(decimals);
}

function fmtPct(v: unknown) {
  const n = num(v, NaN);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function completedDailyDeltaPct(
  series: Array<{ date?: string; value: number }>,
  generatedAt: string
): number | null {
  const today = generatedAt.slice(0, 10);
  const completed = series.filter((point) => !point.date || point.date < today);
  if (completed.length < 2) return null;
  const prev = completed[completed.length - 2]?.value ?? 0;
  const cur = completed[completed.length - 1]?.value ?? 0;
  if (prev === 0) return cur > 0 ? 100 : 0;
  return ((cur - prev) / prev) * 100;
}

function buildServices(data: SystemAdminDashboard): ServiceStatus[] {
  const health = (data.health_summary ?? {}) as Record<string, unknown>;
  const gateway = data.llm_gateway as Record<string, unknown>;
  const workers = data.workers as Record<string, unknown>;
  const storage = data.storage as Record<string, unknown>;
  const traffic = data.traffic as Record<string, unknown>;
  const qdrant = data.qdrant as Record<string, unknown>;
  const postgres = (data.postgres ?? {}) as Record<string, unknown>;

  const fromHealth =
    (health.connectivity as Array<{ name: string; ok: boolean; degraded?: boolean; error?: string }>) ?? [];
  if (fromHealth.length > 0) {
    return fromHealth.map((c) => ({
      name: c.name,
      ok: c.ok,
      degraded: c.degraded,
      detail: c.error ? String(c.error).slice(0, 28) : c.ok ? "OK" : "Down",
    }));
  }
  // /readyz probe unreachable — derive each tile from the section that really
  // ran, and mark anything without a live probe as "no data" instead of
  // inventing an OK.
  const checks = (gateway.checks as Record<string, Record<string, unknown>>) ?? {};
  const celery = (workers.celery as Record<string, unknown>) ?? {};
  const sh = (storage.health as Record<string, unknown>) ?? {};
  return [
    { name: "postgres", ok: !postgres.error, degraded: Boolean(postgres.error), detail: postgres.error ? "probe failed" : "DB" },
    { name: "redis", ok: false, degraded: true, detail: "no data (readyz down)" },
    { name: "qdrant", ok: qdrant.available === true, degraded: qdrant.available !== true, detail: qdrant.available === true ? "Vector" : "no data" },
    { name: "llm", ok: Boolean(checks.llm?.ok), degraded: !checks.llm?.ok, detail: "LLM" },
    { name: "embedding", ok: checks.embedding_dim?.ok === true, degraded: checks.embedding_dim?.ok !== true, detail: "Embed" },
    { name: "celery", ok: Boolean(celery.ok), detail: celery.ok ? `${celery.workers ?? 1}w` : "Down" },
    { name: "storage", ok: sh.ok === true, degraded: sh.ok == null, detail: sh.ok == null ? "no data" : String(storage.backend ?? "local") },
    { name: "prometheus", ok: Boolean(traffic.prometheus_available), degraded: !traffic.prometheus_available, detail: "Metrics" },
  ];
}

function LiveClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <time className="grafana-clock">
      {now.toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
    </time>
  );
}

function Cell({
  label,
  value,
  warn,
  bad,
  tip,
}: {
  label: string;
  value: string;
  warn?: boolean;
  bad?: boolean;
  tip?: NocTipContent;
}) {
  const cell = (
    <div className="grafana-stat-cell">
      <p className="grafana-stat-cell-label">{label}</p>
      <p className={`grafana-stat-cell-value ${warn ? "warn" : bad ? "bad" : ""}`}>{value}</p>
    </div>
  );
  if (!tip) return cell;
  return <NocTip content={tip}>{cell}</NocTip>;
}

export function SystemAdminDashboardView() {
  const qc = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();
  const mockMode: NocMockMode = parseNocMockMode(searchParams.toString());
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [maintMsg, setMaintMsg] = useState("ปิดปรับปรุงชั่วคราว — อ่านอย่างเดียว");
  const [tvMode, setTvMode] = useState(false);
  const [returnPath, setReturnPath] = useState("/chat");

  useEffect(() => {
    setReturnPath(getSystemAdminReturnPath("/chat"));
  }, []);

  const handleBack = useCallback(() => {
    router.push(returnPath);
  }, [router, returnPath]);

  const { data: rawData, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: queryKeys.systemAdminDashboard(),
    queryFn: () => api.getDashboard(),
    staleTime: STALE_REALTIME,
    refetchInterval: mockMode === "off" ? 15_000 : false,
  });

  const data = rawData ? buildMockNocDashboard(rawData, mockMode) : undefined;

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: queryKeys.systemAdminDashboard() });
  }, [qc]);

  const runAction = useMutation({
    mutationFn: async (action: string): Promise<SystemActionResult> => {
      switch (action) {
        case "clear-cache": return api.clearCache();
        case "qdrant-sync": return api.forceQdrantSync();
        case "reset-agentic": return api.resetAgenticCircuit();
        case "reset-rag": return api.resetRagCircuit();
        case "maint-on": return api.toggleMaintenance(true, maintMsg);
        case "maint-off": return api.toggleMaintenance(false);
        default: throw new Error("unknown action");
      }
    },
    onSuccess: (res) => { setActionMsg(`${res.action} ✓`); invalidate(); },
    onError: (e: Error) => setActionMsg(e.message),
  });

  if (isLoading) {
    return <div className="noc-root flex h-[100dvh] items-center justify-center">กำลังโหลด…</div>;
  }
  if (isError || !data) {
    return (
      <div className="noc-root flex h-[100dvh] flex-col items-center justify-center gap-3">
        โหลดไม่สำเร็จ
        <button type="button" className="grafana-action-btn" onClick={() => void refetch()}>Retry</button>
      </div>
    );
  }

  return (
    <NocBody
      data={data}
      mockMode={mockMode}
      isFetching={isFetching}
      onRefresh={() => void refetch()}
      actionMsg={actionMsg}
      maintMsg={maintMsg}
      setMaintMsg={setMaintMsg}
      runAction={runAction}
      tvMode={tvMode}
      setTvMode={setTvMode}
      returnPath={returnPath}
      onBack={handleBack}
    />
  );
}

function NocBody({
  data,
  mockMode,
  isFetching,
  onRefresh,
  actionMsg,
  maintMsg,
  setMaintMsg,
  runAction,
  tvMode,
  setTvMode,
  returnPath,
  onBack,
}: {
  data: SystemAdminDashboard;
  mockMode: NocMockMode;
  isFetching: boolean;
  onRefresh: () => void;
  actionMsg: string | null;
  maintMsg: string;
  setMaintMsg: (v: string) => void;
  runAction: { mutate: (a: string) => void; isPending: boolean };
  tvMode: boolean;
  setTvMode: Dispatch<SetStateAction<boolean>>;
  returnPath: string;
  onBack: () => void;
}) {
  const health = (data.health_summary ?? {}) as Record<string, unknown>;
  const users = (data.users ?? {}) as Record<string, unknown>;
  const ts = (data.timeseries ?? {}) as Record<string, unknown>;
  const traffic = data.traffic as Record<string, unknown>;
  const llm = data.llm_usage as Record<string, unknown>;
  const qdrant = data.qdrant as Record<string, unknown>;
  const storage = data.storage as Record<string, unknown>;
  const workers = data.workers as Record<string, unknown>;
  const rag = (data.rag_circuit ?? {}) as Record<string, unknown>;
  const gateway = data.llm_gateway as Record<string, unknown>;
  const maintenance = data.maintenance as Record<string, unknown>;
  const postgres = (data.postgres ?? {}) as Record<string, unknown>;
  const incidents = data.incidents ?? [];
  const celery = (workers.celery as Record<string, unknown>) ?? {};
  const maintOn = Boolean(maintenance.enabled);

  const services = buildServices(data);
  const okCount = services.filter((s) => s.ok).length;
  const neoHealth = assessNocHealth(data, services);

  const dailyUsers = (ts.daily_active_users as Array<{ date: string; value: number }>) ?? [];
  const dailyMsgs = (ts.daily_messages as Array<{ date: string; value: number }>) ?? [];
  const dailySessions = (ts.daily_sessions as Array<{ date: string; value: number }>) ?? [];
  const dailyIngest = (ts.daily_ingest_jobs as Array<{ date: string; value: number }>) ?? [];
  const dailyIngestByStatus = (ts.daily_ingest_by_status as IngestStatusPoint[]) ?? [];
  const tokenSplit = (ts.daily_token_split as SplitPoint[]) ?? [];
  const hourlyMsgs = (ts.hourly_messages as Array<{ label: string; value: number }>) ?? [];
  const hourlyReq = (ts.hourly_requests as Array<{ label: string; value: number }>) ?? [];
  const hourlyLat = (ts.hourly_latency_ms as Array<{ label: string; value: number }>) ?? [];
  const ingestSlices = (ts.ingest_by_status as Array<{ label: string; value: number }>) ?? [];

  const promUp = Boolean(traffic.prometheus_available);
  // Prometheus needs a couple of populated hourly buckets before the request-rate
  // series is worth showing over the DB-backed message count fallback (a freshly
  // started Prometheus only has 1 point, which can't draw a line).
  const usingHttpReq = promUp && hourlyReq.length >= 2;
  const trafficSeries = usingHttpReq ? hourlyReq : hourlyMsgs;
  const trafficTitle = usingHttpReq ? "HTTP Requests / sec" : "Messages / hour";
  const trafficSub = promUp ? "Prometheus 24h" : "DB fallback 24h";

  const dailyTokens = (ts.daily_tokens_est as Array<{ date: string; value: number }>) ?? [];
  const activeNow = num(users.active_users_1h, num(traffic.active_users));
  const tokens24h = num(llm.prompt_tokens_est) + num(llm.completion_tokens_est);
  const errRate = num(traffic.error_rate_5xx, NaN);
  const errBad = Number.isFinite(errRate) && errRate > 0.005;
  const ctx = buildNocContext(data, promUp, activeNow, tokens24h);
  const completedTokensDelta = completedDailyDeltaPct(dailyTokens, data.generated_at);
  const completedMessagesDelta = completedDailyDeltaPct(dailyMsgs, data.generated_at);

  const toggleTv = useCallback(() => {
    setTvMode((prev) => {
      const next = !prev;
      if (next && typeof document !== "undefined") {
        void document.documentElement.requestFullscreen?.().catch(() => undefined);
      } else if (!next && typeof document !== "undefined" && document.fullscreenElement) {
        void document.exitFullscreen?.().catch(() => undefined);
      }
      return next;
    });
  }, [setTvMode]);

  return (
    <div className={`noc-root noc-shell ${tvMode ? "noc-tv-mode" : ""} ${neoHealth.level === "critical" ? "noc-shell-critical" : neoHealth.level === "warn" ? "noc-shell-warn" : ""}`}>
      {mockMode !== "off" ? (
        <div className="noc-mock-banner">
          <span>
            Demo data
            {mockMode === "degraded" ? " (degraded)" : " (healthy)"}
          </span>
          <span className="noc-mock-banner-hint">
            <Link href="/system-admin?mock=0" replace>real</Link>
            {" · "}
            <Link href="/system-admin?mock=1" replace>healthy</Link>
            {" · "}
            <Link href="/system-admin?mock=degraded" replace>alert</Link>
          </span>
        </div>
      ) : null}
      <header className="noc-topbar">
        <div className="noc-topbar-brand">
          <Shield className="h-5 w-5 shrink-0" style={{ color: "var(--gf-orange)" }} />
          <div>
            <h1 className="grafana-header-title">Spark Ops Control Room</h1>
            <p className="grafana-header-sub">
              {new Date(data.generated_at).toLocaleString("th-TH")} · {okCount}/{services.length} services
            </p>
          </div>
        </div>
        <LiveClock />
        <NocTip
          content={{
            title: neoHealth.headline,
            lines: [neoHealth.detail, ...neoHealth.advisories.slice(0, 3)],
          }}
          className="noc-topbar-neo-wrap"
        >
          <SparkNocGuardian assessment={neoHealth} className="noc-topbar-neo" />
        </NocTip>
        <div className="noc-topbar-actions">
          <button type="button" className="grafana-sync-btn shrink-0" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" />
            กลับ
          </button>
          {maintOn ? <span className="grafana-status warn shrink-0">Maint</span> : null}
          <button type="button" className="grafana-sync-btn shrink-0" onClick={toggleTv} title="TV / Fullscreen mode">
            <Tv className={`h-4 w-4 ${tvMode ? "text-[var(--noc-cyan)]" : ""}`} />
          </button>
          <button type="button" className="grafana-sync-btn shrink-0" onClick={onRefresh}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            Sync
          </button>
        </div>
      </header>

      <NocIncidentStrip incidents={incidents} />

      <div className="grafana-stat-row noc-kpi-row">
        <GrafanaStat label="Online" value={fmt(activeNow)} color="var(--noc-cyan)" tip={NOC_TIPS.kpiOnline(ctx)} />
        <GrafanaStat label="Sessions" value={fmt(num(users.active_sessions_1h, num(traffic.active_sessions_15m)))} tip={NOC_TIPS.kpiSessions(ctx)} />
        <GrafanaStat label="Tokens 24h" value={fmt(tokens24h)} color="var(--noc-violet)" tip={NOC_TIPS.kpiTokens(ctx)}
          delta={completedTokensDelta != null ? { pct: completedTokensDelta, label: "วันเต็มล่าสุด" } : null} />
        <GrafanaStat label="Messages" value={fmt(num(llm.message_count, num(traffic.messages_24h)))} color="var(--gf-green)" tip={NOC_TIPS.kpiMessages(ctx)}
          delta={completedMessagesDelta != null ? { pct: completedMessagesDelta, label: "วันเต็มล่าสุด" } : null} />
        <GrafanaStat label="5xx Error" value={fmtPct(traffic.error_rate_5xx)} color={errBad ? "var(--gf-red)" : "var(--gf-green)"} tip={NOC_TIPS.kpiError(ctx)} />
        <GrafanaStat label="Cost" value={`฿${fmtThb(costInThb(llm).thb)}`} color="var(--gf-yellow)" tip={NOC_TIPS.kpiCost(ctx)} />
        <GrafanaStat
          label="Ingest Q"
          value={fmt(workers.ingest_queue_backlog)}
          color={num(workers.ingest_queue_backlog) > 20 ? "var(--gf-orange)" : undefined}
          tip={NOC_TIPS.kpiIngest(ctx)}
        />
        <GrafanaStat
          label="Requests/s"
          value={promUp && traffic.requests_per_sec != null ? num(traffic.requests_per_sec).toFixed(2) : "—"}
          color={num(traffic.p95_latency_sec) > 0.3 ? "var(--gf-orange)" : undefined}
          secondary={{
            label: "p95 latency",
            value: promUp && traffic.p95_latency_sec != null ? `${num(traffic.p95_latency_sec).toFixed(3)}s` : "—",
          }}
          tip={NOC_TIPS.requestsPerSec(ctx)}
        />
      </div>

      <div className="noc-dashboard-grid">
        <GrafanaPanel className="noc-cell-tokens" title="Token Usage" subtitle="7 days · prompt + completion"
          tip={NOC_TIPS.tokens(ctx)}
          legend={<><LegendDot color="#5794f2" label="Prompt" /><LegendDot color="#b877d9" label="Compl" /></>}>
          <GrafanaStackedBars points={tokenSplit.length ? tokenSplit : dailyUsers.map((d) => ({ date: d.date, prompt: 0, completion: 0 }))} />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-users" title="Active Users" subtitle="7 days" tip={NOC_TIPS.users(ctx)}>
          <GrafanaBarChart points={dailyUsers} color="#73bf69" />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-msgs" title="Messages" subtitle="7 days" tip={NOC_TIPS.messages(ctx)}>
          <GrafanaBarChart points={dailyMsgs} color="#5794f2" />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-traffic" title={trafficTitle} subtitle={trafficSub} tip={NOC_TIPS.traffic(ctx, trafficTitle)}>
          <GrafanaTimeSeries points={trafficSeries} color={usingHttpReq ? "#ff9830" : "#5794f2"} unit={usingHttpReq ? "/s" : ""} fallbackLabel="No traffic data" />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-sessions" title="Sessions" subtitle="7 days created" tip={NOC_TIPS.sessions(ctx)}>
          <GrafanaBarChart points={dailySessions} color="#fade2a" />
        </GrafanaPanel>

        <GrafanaPanel
          className="noc-cell-ingest"
          title="Ingest Jobs"
          subtitle="7 days"
          tip={NOC_TIPS.ingestJobs(ctx)}
          legend={
            <>
              <LegendDot color="#73bf69" label="Completed" />
              <LegendDot color="#fade2a" label="Queued" />
              <LegendDot color="#ff9830" label="รอต่อคิวเดิม" />
              <LegendDot color="#f2495c" label="Failed" />
              <LegendDot color="#b877d9" label="Deleted" />
            </>
          }
        >
          <GrafanaIngestBars
            points={
              dailyIngestByStatus.length
                ? dailyIngestByStatus
                : dailyIngest.map((d) => ({
                    date: d.date,
                    completed: 0,
                    queued: 0,
                    failed: 0,
                    deleted: 0,
                    pending_review: 0,
                  }))
            }
          />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-connectivity" title="Connectivity" subtitle={`${okCount}/${services.length} OK`}
          tip={NOC_TIPS.connectivity(ctx, okCount, services.length)}>
          <div className="noc-panel-fill">
            <div className="grafana-service-grid noc-service-compact">
              {services.map((s) => {
                const st = s.ok ? "ok" : s.degraded ? "warn" : "down";
                const tile = (
                  <div className={`grafana-service ${st}`}>
                    <span className="grafana-service-name">{s.name}</span>
                    <span className={`grafana-service-badge ${st}`}>{s.ok ? "OK" : s.degraded ? "!" : "X"}</span>
                  </div>
                );
                return (
                  <NocTip key={s.name} content={NOC_TIPS.service(s.name, s.ok, s.degraded, s.detail)}>
                    {tile}
                  </NocTip>
                );
              })}
            </div>
          </div>
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-latency" title="Latency p95" subtitle={promUp ? "ms · 24h" : "Prometheus off"} tip={NOC_TIPS.latency(ctx)}>
          <GrafanaTimeSeries points={hourlyLat} color="#f2495c" unit="ms" fallbackLabel="No latency data" />
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-infra" title="Infrastructure" alert={Boolean(qdrant.chunk_drift_alert)} tip={NOC_TIPS.infra(ctx)}>
          <div className="noc-stat-grid noc-stat-grid-5x2">
            <Cell label="Chunks" value={fmt(qdrant.postgres_chunks_total)} tip={NOC_TIPS.cellChunks(ctx)} />
            <Cell label="Vectors" value={fmt(qdrant.qdrant_points_total)} tip={NOC_TIPS.cellVectors(ctx)} />
            <Cell label="Drift" value={fmt(qdrant.chunk_drift)} warn={Boolean(qdrant.chunk_drift_alert)} tip={NOC_TIPS.cellDrift(ctx)} />
            <Cell label="Docs" value={fmt(storage.document_count)} tip={NOC_TIPS.cellDocs(ctx)} />
            <Cell label="Qdrant" value={storage.qdrant_gib_estimate != null ? `~${fmt(storage.qdrant_gib_estimate, 2)}G` : "—"} tip={NOC_TIPS.cellStorageQdrant(ctx)} />
            <Cell label="MinIO" value={`${fmt(storage.document_gib, 1)}G`} tip={NOC_TIPS.cellStorageMinio(ctx)} />
            <Cell label="Postgres" value={`${fmt(storage.postgres_gib, 2)}G`} tip={NOC_TIPS.cellStoragePostgres(ctx)} />
            <Cell label="Failed" value={fmt(workers.failed_ingest_jobs)} bad={num(workers.failed_ingest_jobs) > 0} tip={NOC_TIPS.cellFailed(ctx)} />
            <Cell label="Errors" value={fmt(workers.ingestion_error_rows)} tip={NOC_TIPS.cellDlq(ctx)} />
            <Cell label="Celery" value={celery.ok ? fmt(celery.workers) : "DOWN"} bad={!celery.ok} tip={NOC_TIPS.cellCelery(ctx)} />
          </div>
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-ai" title="AI Answer Quality" alert={Boolean(rag.open)}
          subtitle={`24h · ${fmt(llm.answer_count)} answers`} tip={NOC_TIPS.ai(ctx)}>
          <div className="noc-stat-grid noc-stat-grid-6x1">
            <Cell
              label="Cited"
              value={llm.cited_answer_rate_pct != null ? `${fmt(llm.cited_answer_rate_pct, 1)}%` : "—"}
              warn={llm.cited_answer_rate_pct != null && num(llm.cited_answer_rate_pct) < 70}
              tip={{ title: "คำตอบพร้อมหลักฐาน", lines: ["สัดส่วนคำตอบ AI ที่มีเอกสารอ้างอิงใน 24 ชั่วโมง", "ค่ายิ่งสูงยิ่งตรวจสอบย้อนกลับได้"] }}
            />
            <Cell label="RAG CB" value={rag.open ? "OPEN" : "OK"} warn={Boolean(rag.open)} tip={NOC_TIPS.cellRag(ctx)} />
            <Cell
              label="No data"
              value={llm.no_data_rate_pct != null ? `${fmt(llm.no_data_rate_pct, 1)}%` : "—"}
              warn={llm.no_data_rate_pct != null && num(llm.no_data_rate_pct) > 30}
              tip={{ title: "อัตราหาคำตอบไม่พบ", lines: ["สัดส่วนคำตอบที่ไม่มีหลักฐานเพียงพอ", "ค่าสูงอาจหมายถึงเอกสารยังไม่ครอบคลุม หรือผู้ใช้เลือกเครื่องผิด"] }}
            />
            <Cell
              label="High conf"
              value={llm.high_confidence_rate_pct != null ? `${fmt(llm.high_confidence_rate_pct, 1)}%` : "—"}
              tip={{ title: "คำตอบความมั่นใจสูง", lines: ["สัดส่วนคำตอบระดับ high confidence ใน 24 ชั่วโมง", "ควรดูคู่กับ Cited และ feedback ไม่ควรใช้เดี่ยว ๆ"] }}
            />
            <Cell
              label="Cache hit"
              value={llm.cache_hit_rate_pct != null ? `${fmt(llm.cache_hit_rate_pct, 1)}%` : "—"}
              tip={{ title: "คำตอบจากแคช", lines: ["คำถามซ้ำที่ตอบได้โดยไม่รัน pipeline ใหม่", "ช่วยลดเวลาและค่าใช้จ่าย"] }}
            />
            <Cell
              label="Model"
              value={String(gateway.llm_profile ?? "—")}
              tip={{ title: "AI profile", lines: ["ชุดโมเดล chat, embedding และ reranker ที่กำลังใช้งาน"] }}
            />
          </div>
        </GrafanaPanel>

        <GrafanaPanel
          className="noc-cell-postgres"
          title="PostgreSQL"
          subtitle={
            postgres.pool_checked_out != null
              ? `pool ${fmt(postgres.pool_checked_out)}/${fmt(postgres.pool_capacity, 0)} in use`
              : `pool ${fmt(postgres.pool_size)}`
          }
          tip={NOC_TIPS.postgres(ctx)}
        >
          <div className="noc-stat-grid noc-stat-grid-2x2">
            <Cell
              label="In use"
              value={
                postgres.pool_checked_out != null
                  ? `${fmt(postgres.pool_checked_out)}/${fmt(postgres.pool_capacity, 0)}`
                  : "—"
              }
              tip={NOC_TIPS.pgPool(ctx)}
            />
            <Cell
              label="Idle"
              value={postgres.pool_checked_in != null ? fmt(postgres.pool_checked_in) : "—"}
              tip={NOC_TIPS.pgIdle(ctx)}
            />
            <Cell label="Locks" value={fmt((postgres.locks as unknown[])?.length ?? 0)} tip={NOC_TIPS.pgLocks(ctx)} />
            <Cell label="Slow Q" value={fmt((postgres.slow_queries as unknown[])?.length ?? 0)} warn={((postgres.slow_queries as unknown[])?.length ?? 0) > 0} tip={NOC_TIPS.pgSlow(ctx)} />
          </div>
        </GrafanaPanel>

        <GrafanaPanel className="noc-cell-ingest-status" title="Ingest Status" tip={NOC_TIPS.ingestDonut(ctx, ingestSlices)}>
          <GrafanaDonut slices={ingestSlices} fill />
        </GrafanaPanel>
      </div>

      <div className="noc-footer-bar">
        <GrafanaPanel className="noc-debug-panel" title="Debug" subtitle="consoles · เปิดแท็บใหม่">
          <NocDebugLinks data={data} promUp={promUp} />
        </GrafanaPanel>

        <GrafanaPanel className="noc-actions-bar" title="ดำเนินการ" subtitle="ผู้ดูแลระบบ" tip={NOC_TIPS.actions(ctx)}>
          <div className="noc-actions-toolbar">
            <input
              value={maintMsg}
              onChange={(e) => setMaintMsg(e.target.value)}
              className="noc-action-input"
              placeholder="ข้อความแจ้งผู้ใช้ (โหมดบำรุงรักษา)"
            />
            <div className="noc-actions-btns">
              {(
                [
                  ["clear-cache", "ล้างแคช", true, NOC_TIPS.actionClear()],
                  ["qdrant-sync", "ซิงก์ Qdrant", false, NOC_TIPS.actionSync()],
                  [maintOn ? "maint-off" : "maint-on", maintOn ? "ปิดบำรุงรักษา" : "เปิดบำรุงรักษา", true, NOC_TIPS.actionMaint(maintOn)],
                  ["reset-agentic", "รีเซ็ต Agentic", false, NOC_TIPS.actionAgentic()],
                  ["reset-rag", "รีเซ็ต RAG", false, NOC_TIPS.actionRag()],
                ] as const
              ).map(([id, label, danger, tip]) => (
                <NocTip key={id} content={tip}>
                  <button type="button" disabled={runAction.isPending}
                    className={`grafana-action-btn ${danger ? "danger" : ""}`}
                    onClick={() => runAction.mutate(id)}>
                    {label}
                  </button>
                </NocTip>
              ))}
            </div>
            <p className="noc-action-status">
              {actionMsg ??
                `Live ${promUp && traffic.sse_connections != null ? fmt(traffic.sse_connections) : "—"} · Metrics ${promUp ? "พร้อม" : "ไม่พร้อม"}`}
            </p>
          </div>
        </GrafanaPanel>
      </div>

      <footer className="noc-footer">
        <NocTip
          content={{
            title: "Storage health",
            lines: [
              (storage.health as Record<string, unknown>)?.ok ? "ตรวจ backend แล้ว: เขียน/อ่านได้ปกติ" : "ตรวจ backend ล้มเหลว — เช็คดิสก์/สิทธิ์",
              `Backend: ${String(storage.backend ?? "local")} · ${fmt(storage.document_count)} ไฟล์`,
            ],
          }}
        >
          <span>Storage {(storage.health as Record<string, unknown>)?.ok ? "OK" : "FAIL"}</span>
        </NocTip>
        <NocTip
          content={{
            title: "OpenTelemetry tracing",
            lines: [
              (data.otel_tracing as Record<string, unknown> | undefined)?.enabled
                ? `ส่ง trace ไปที่ ${String((data.otel_tracing as Record<string, unknown>)?.endpoint ?? "")}`
                : "ปิดอยู่ — ตั้ง OTEL_EXPORTER_OTLP_ENDPOINT เพื่อเปิด",
            ],
          }}
        >
          <span>· Tracing {(data.otel_tracing as Record<string, unknown> | undefined)?.enabled ? "ON" : "OFF"}</span>
        </NocTip>
        <NocTip
          content={{
            title: "Qdrant host",
            lines: [
              `เชื่อมต่อ ${String(qdrant.host ?? "qdrant")} · ${qdrant.available === true ? "พร้อมใช้งาน" : "เชื่อมต่อไม่ได้"}`,
              `Vectors ${fmt(qdrant.qdrant_points_total)} จุด ใน ${((qdrant.collections as unknown[]) ?? []).length} collections`,
            ],
          }}
        >
          <span>· {String(qdrant.host ?? "qdrant")}</span>
        </NocTip>
        <span>· Spark Ops Control Room · Cyber NOC</span>
      </footer>
    </div>
  );
}
