"use client";

import type { SystemAdminDashboard } from "@/lib/api";
import { cn } from "@/lib/cn";
import { costInThb, fmtThb } from "@/lib/system-admin/nocTooltips";
import { Zap } from "lucide-react";
import { useEffect, useState } from "react";

export type NocHealthLevel = "ok" | "warn" | "critical";

export type NocHealthAssessment = {
  level: NocHealthLevel;
  issues: string[];
  headline: string;
  detail: string;
  /** Contextual tips (abnormal) or interesting reports (healthy). */
  advisories: string[];
};

type ServiceStatus = { name: string; ok: boolean; degraded?: boolean; detail?: string };

function num(v: unknown, fb = 0) {
  return typeof v === "number" && Number.isFinite(v) ? v : fb;
}

function fmtCompact(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 10_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(Math.round(v));
}

function pushUnique(out: string[], msg: string, max = 4) {
  if (msg && !out.includes(msg) && out.length < max) out.push(msg);
}

/** Actionable guidance when degraded, or interesting ops reports when healthy. */
function buildNocAdvisories(
  data: SystemAdminDashboard,
  level: NocHealthLevel,
  issues: string[]
): string[] {
  const users = (data.users ?? {}) as Record<string, unknown>;
  const traffic = data.traffic as Record<string, unknown>;
  const llm = data.llm_usage as Record<string, unknown>;
  const workers = data.workers as Record<string, unknown>;
  const qdrant = data.qdrant as Record<string, unknown>;
  const storage = data.storage as Record<string, unknown>;
  const semanticCache = (data.semantic_cache ?? {}) as Record<string, unknown>;
  const celery = (workers.celery as Record<string, unknown>) ?? {};
  const maintenance = data.maintenance as Record<string, unknown>;
  const agentic = data.agentic_circuit as Record<string, unknown>;
  const rag = (data.rag_circuit ?? {}) as Record<string, unknown>;

  const out: string[] = [];

  if (level === "critical" || level === "warn") {
    const joined = issues.join(" ").toLowerCase();

    if (joined.includes("agentic")) {
      pushUnique(out, "แนะนำ: กด Reset Agentic ใน Actions แล้วตรวจ log routing / canary");
    }
    if (joined.includes("rag cb")) {
      pushUnique(out, "แนะนำ: กด Reset RAG CB — ตรวจ retrieval latency และ error rate ก่อนเปิดวงจร");
    }
    if (joined.includes("celery")) {
      pushUnique(out, "แนะนำ: ตรวจ Celery worker / broker — ingest อาจค้างในคิว");
    }
    if (joined.includes("storage")) {
      pushUnique(out, "แนะนำ: ตรวจพื้นที่ดิสก์ backend และ quota — upload/ingest อาจล้มเหลว");
    }
    if (joined.includes("postgres") || joined.includes("redis") || joined.includes("qdrant")) {
      pushUnique(out, "แนะนำ: ตรวจ connectivity panel — restart service ที่ down ก่อน sync ข้อมูล");
    }
    if (joined.includes("llm") || joined.includes("gateway")) {
      pushUnique(out, "แนะนำ: ตรวจ Ollama / LLM gateway และ embedding model ให้ตอบ 200");
    }
    if (joined.includes("failed jobs")) {
      pushUnique(out, `แนะนำ: มี failed ingest ${num(workers.failed_ingest_jobs)} งาน — ตรวจ logs และ retry จาก admin`);
    }
    if (joined.includes("drift")) {
      pushUnique(out, "แนะนำ: กด Sync Qdrant เพื่อ reconcile chunks กับ vector store");
    }
    if (joined.includes("queue")) {
      pushUnique(out, `แนะนำ: คิว ingest ${num(workers.ingest_queue_backlog)} งาน — เพิ่ม worker หรือชะลอ upload ชั่วคราว`);
    }
    if (joined.includes("maintenance")) {
      pushUnique(out, "แนะนำ: โหมด Maintenance เปิดอยู่ — ผู้ใช้ทั่วไปอ่านอย่างเดียว ปิดเมื่อ deploy เสร็จ");
    }
    if (joined.includes("prometheus")) {
      pushUnique(out, "แนะนำ: Prometheus ไม่พร้อม — traffic/latency ใช้ข้อมูล DB fallback");
    }

    if (out.length === 0) {
      pushUnique(out, "แนะนำ: กด Sync อัปเดต snapshot แล้วตรวจ panel Connectivity + Infrastructure");
    }
    if (level === "critical") {
      pushUnique(out, "ด่วน: แจ้งทีม ops ทันที — อย่าปล่อย circuit breaker เปิดค้าง");
    }
    return out;
  }

  // Healthy — interesting ops reports
  const active15 = num(users.active_users_15m, num(traffic.active_users));
  const active24 = num(users.active_users_24h);
  const messages = num(llm.message_count, num(traffic.messages_24h));
  const tokens =
    num(llm.prompt_tokens_est) + num(llm.completion_tokens_est) + num(llm.embedding_tokens_est);
  const costThb = costInThb(llm).thb;
  const docs = num(storage.document_count);
  const chunks = num(qdrant.postgres_chunks_total);
  const drift = num(qdrant.chunk_drift);
  const hitRate = semanticCache.hit_rate_pct;
  const workerCount = num(celery.workers, 1);
  const sessions = num(users.active_sessions_15m, num(traffic.active_sessions_15m));
  const sse = num(traffic.sse_connections);
  const registered = num(users.total_registered);

  if (active24 > 0 || messages > 0) {
    pushUnique(
      out,
      `📊 24 ชม.: ผู้ใช้ ${active24} คน · ข้อความ ${fmtCompact(messages)} · ออนไลน์ตอนนี้ ${active15} คน`
    );
  }
  if (tokens > 0) {
    pushUnique(
      out,
      `💡 โทเคน ~${fmtCompact(tokens)} (24 ชม.) · ค่าใช้จ่ายประมาณ ฿${fmtThb(costThb)}`
    );
  }
  if (docs > 0 || chunks > 0) {
    pushUnique(
      out,
      `📁 คลังความรู้: เอกสาร ${fmtCompact(docs)} ไฟล์ · chunks ${fmtCompact(chunks)} · drift ${drift}`
    );
  }
  if (typeof hitRate === "number" && num(semanticCache.enabled ? 1 : 0)) {
    pushUnique(out, `⚡ Semantic cache hit ${hitRate.toFixed(0)}% — คำถามซ้ำตอบเร็วขึ้น`);
  }
  if (sessions > 0 || sse > 0) {
    pushUnique(out, `🔗 Session ${sessions} · SSE live ${sse} — แชท real-time ทำงานปกติ`);
  }
  if (workerCount > 0 && celery.ok) {
    pushUnique(out, `✅ Celery ${workerCount} worker · คิว ingest ${num(workers.ingest_queue_backlog)} งาน`);
  }
  if (registered > 0) {
    pushUnique(out, `👥 บัญชีลงทะเบียน ${registered} · super admin ${num(users.super_admins, 1)} คน`);
  }
  if (Boolean(maintenance.enabled)) {
    pushUnique(out, "⚠️ Maintenance เปิดอยู่ — ผู้ใช้เห็นข้อความ read-only");
  }

  if (out.length === 0) {
    pushUnique(out, "ทุกบริการพร้อมใช้งาน — ไม่มี incident ที่ต้องดำเนินการ");
    pushUnique(out, "กด Sync เป็นระยะเพื่อ refresh metrics บนจอ NOC");
  }

  return out;
}

/** Derive control-room health from dashboard snapshot. */
export function assessNocHealth(
  data: SystemAdminDashboard,
  services: ServiceStatus[]
): NocHealthAssessment {
  const issues: string[] = [];
  const agentic = data.agentic_circuit as Record<string, unknown>;
  const rag = (data.rag_circuit ?? {}) as Record<string, unknown>;
  const workers = data.workers as Record<string, unknown>;
  const qdrant = data.qdrant as Record<string, unknown>;
  const storage = data.storage as Record<string, unknown>;
  const gateway = data.llm_gateway as Record<string, unknown>;
  const maintenance = data.maintenance as Record<string, unknown>;
  const celery = (workers.celery as Record<string, unknown>) ?? {};
  const storageOk = (storage.health as Record<string, unknown>)?.ok !== false;

  if (Boolean(agentic.open)) issues.push("Agentic CB เปิด");
  if (Boolean(rag.open)) issues.push("RAG CB เปิด");
  if (!celery.ok) issues.push("Celery down");
  if (!storageOk) issues.push("Storage FAIL");

  for (const s of services) {
    if (!s.ok && !s.degraded) issues.push(`${s.name} DOWN`);
    else if (s.degraded) issues.push(`${s.name} warn`);
  }

  if (num(workers.failed_ingest_jobs) > 0) {
    issues.push(`Failed jobs ${num(workers.failed_ingest_jobs)}`);
  }

  const warnOnly: string[] = [];
  if (Boolean(maintenance.enabled)) warnOnly.push("Maintenance ON");
  if (Boolean(qdrant.chunk_drift_alert)) warnOnly.push(`Drift ${num(qdrant.chunk_drift)}`);
  if (num(workers.ingest_queue_backlog) > 20) {
    warnOnly.push(`Queue ${num(workers.ingest_queue_backlog)}`);
  }
  if (gateway.healthy === false && issues.length === 0) {
    warnOnly.push("Gateway unhealthy");
  }

  const hasCritical =
    Boolean(agentic.open) ||
    Boolean(rag.open) ||
    !celery.ok ||
    !storageOk ||
    services.some((s) => !s.ok && !s.degraded) ||
    num(workers.failed_ingest_jobs) > 0;

  if (hasCritical) {
    const all = [...issues, ...warnOnly];
    return {
      level: "critical",
      issues: all,
      headline: "ระบบผิดปกติ",
      detail: issues[0] ?? "ต้องแก้ไขด่วน",
      advisories: buildNocAdvisories(data, "critical", all),
    };
  }

  if (warnOnly.length > 0 || issues.length > 0) {
    const all = [...issues, ...warnOnly];
    return {
      level: "warn",
      issues: all,
      headline: "มีสัญญาณเตือน",
      detail: all[0] ?? "ควรตรวจสอบ",
      advisories: buildNocAdvisories(data, "warn", all),
    };
  }

  return {
    level: "ok",
    issues: [],
    headline: "ระบบปกติ",
    detail: "ทุกบริการพร้อมใช้งาน",
    advisories: buildNocAdvisories(data, "ok", []),
  };
}

function AdvisoryTicker({ messages, level }: { messages: string[]; level: NocHealthLevel }) {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    setIdx(0);
  }, [messages]);

  useEffect(() => {
    if (messages.length <= 1) return;
    const id = setInterval(() => setIdx((i) => (i + 1) % messages.length), 6000);
    return () => clearInterval(id);
  }, [messages]);

  if (messages.length === 0) return null;

  const label =
    level === "ok" ? "รายงาน" : level === "warn" ? "คำแนะนำ" : "ดำเนินการ";

  return (
    <div className="neo-noc-advisory" aria-live="polite">
      <span className={cn("neo-noc-advisory-label", level !== "ok" && "neo-noc-advisory-label-alert")}>
        {label}
      </span>
      <p key={idx} className="neo-noc-advisory-text">
        {messages[idx]}
      </p>
      {messages.length > 1 ? (
        <span className="neo-noc-advisory-dots" aria-hidden>
          {messages.map((_, i) => (
            <span key={i} className={cn("neo-noc-advisory-dot", i === idx && "active")} />
          ))}
        </span>
      ) : null}
    </div>
  );
}

export function SparkNocGuardian({
  assessment,
  className,
}: {
  assessment: NocHealthAssessment;
  className?: string;
}) {
  const { level, issues, headline, detail, advisories } = assessment;
  const isCritical = level === "critical";
  const isWarn = level === "warn";

  return (
    <section
      className={cn(
        "neo-noc-strip",
        level === "ok" && "neo-noc-strip-ok",
        isWarn && "neo-noc-strip-warn",
        isCritical && "neo-noc-strip-critical",
        className
      )}
      role="status"
      aria-live="polite"
      aria-label={`Spark Ops: ${headline}`}
    >
      <div
        className={cn(
          "neo-noc-strip-avatar",
          isCritical && "neo-noc-avatar-shake",
          isWarn && "neo-noc-avatar-wobble"
        )}
      >
        {isCritical ? <div className="neo-noc-alert-ring" aria-hidden /> : null}
        <div
          className={cn(
            "spark-noc-mark",
            isWarn && "spark-noc-mark-warn",
            isCritical && "spark-noc-mark-critical"
          )}
          aria-hidden
        >
          <Zap className="h-6 w-6" strokeWidth={2.5} />
        </div>
      </div>

      <div className="neo-noc-strip-body min-w-0 flex-1">
        <div className="neo-noc-strip-head">
          <div className="neo-noc-strip-text min-w-0">
            <p className="neo-noc-strip-title">{headline}</p>
            <p className="neo-noc-strip-detail">{detail}</p>
          </div>

          {issues.length > 0 ? (
            <ul className="neo-noc-strip-chips">
              {issues.slice(0, 3).map((issue) => (
                <li key={issue} className="neo-noc-issue-chip">
                  {issue}
                </li>
              ))}
              {issues.length > 3 ? (
                <li className="neo-noc-issue-chip">+{issues.length - 3}</li>
              ) : null}
            </ul>
          ) : (
            <span className="neo-noc-strip-ok-badge">OK</span>
          )}
        </div>

        <AdvisoryTicker messages={advisories} level={level} />
      </div>
    </section>
  );
}
