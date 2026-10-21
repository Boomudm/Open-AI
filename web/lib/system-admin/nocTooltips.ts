import type { NocTipContent } from "@/components/system-admin/NocTip";
import type { SystemAdminDashboard } from "@/lib/api";

function n(v: unknown, fb = 0) {
  return typeof v === "number" && Number.isFinite(v) ? v : fb;
}

function fmt(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 10_000) return `${(v / 1_000).toFixed(1)}k`;
  return String(Math.round(v));
}

/** Estimated 24h AI cost in THB — prefers backend-converted figure, falls back
 * to converting the USD estimate with the reported (or default) rate. */
export function costInThb(llm: Record<string, unknown>): { thb: number; usd: number; rate: number } {
  const rate = n(llm.usd_thb_rate, 33);
  const usd = n(llm.estimated_cost_usd);
  const thb = n(llm.estimated_cost_thb, usd * rate);
  return { thb, usd, rate };
}

/** Baht formatter — small estimates need extra precision to not render as 0.00. */
export function fmtThb(v: number): string {
  return v >= 1 ? v.toFixed(2) : v.toFixed(3);
}

type Ctx = {
  data: SystemAdminDashboard;
  users: Record<string, unknown>;
  traffic: Record<string, unknown>;
  llm: Record<string, unknown>;
  workers: Record<string, unknown>;
  qdrant: Record<string, unknown>;
  storage: Record<string, unknown>;
  gateway: Record<string, unknown>;
  agentic: Record<string, unknown>;
  rag: Record<string, unknown>;
  semanticCache: Record<string, unknown>;
  promUp: boolean;
  tokens24h: number;
  activeNow: number;
};

export function buildNocContext(data: SystemAdminDashboard, promUp: boolean, activeNow: number, tokens24h: number): Ctx {
  return {
    data,
    users: (data.users ?? {}) as Record<string, unknown>,
    traffic: data.traffic as Record<string, unknown>,
    llm: data.llm_usage as Record<string, unknown>,
    workers: data.workers as Record<string, unknown>,
    qdrant: data.qdrant as Record<string, unknown>,
    storage: data.storage as Record<string, unknown>,
    gateway: data.llm_gateway as Record<string, unknown>,
    agentic: data.agentic_circuit as Record<string, unknown>,
    rag: (data.rag_circuit ?? {}) as Record<string, unknown>,
    semanticCache: (data.semantic_cache ?? {}) as Record<string, unknown>,
    promUp,
    tokens24h,
    activeNow,
  };
}

export const NOC_TIPS = {
  kpiOnline(c: Ctx): NocTipContent {
    return {
      title: "ผู้ใช้ออนไลน์",
      lines: [
        `ตัวเลขใหญ่ = ผู้ใช้ที่ active ใน 1 ชม. ล่าสุด (${c.activeNow} คน)`,
        `15 นาที: ${n(c.users.active_users_15m, n(c.traffic.active_users))} คน · 24 ชม.: ${n(c.users.active_users_24h)} คน`,
        `บัญชีทั้งหมด ${n(c.users.total_registered)} คน`,
        "นับ unique user จาก chat session ที่มี activity (PostgreSQL)",
      ],
    };
  },
  kpiSessions(c: Ctx): NocTipContent {
    return {
      title: "Sessions",
      lines: [
        `Active sessions (ทุก 1 ชั่วโมง): ${n(c.users.active_sessions_1h, n(c.traffic.active_sessions_15m))}`,
        "เซสชันแชทที่มี activity ล่าสุด",
      ],
    };
  },
  kpiTokens(c: Ctx): NocTipContent {
    const bd = c.llm.cost_breakdown_usd as Record<string, number> | undefined;
    const fromProvider = String(c.llm.usage_source ?? "estimated") === "provider";
    return {
      title: "โทเคน 24 ชม.",
      lines: [
        `Prompt ${n(c.llm.prompt_tokens_est).toLocaleString()} · Completion ${n(c.llm.completion_tokens_est).toLocaleString()}`,
        `Embedding ~${n(c.llm.embedding_tokens_est).toLocaleString()} (ประมาณจากจำนวน chunk)`,
        fromProvider
          ? `ที่มา: ตัวเลขจริงจาก LLM provider (${n(c.llm.usage_request_count)} คำตอบ)`
          : "ที่มา: นับด้วย token counter จากข้อความจริงใน DB (ยังไม่มีเลขจาก provider)",
        bd
          ? `Cost split: P ฿${fmtThb(n(bd.prompt) * costInThb(c.llm).rate)} / C ฿${fmtThb(n(bd.completion) * costInThb(c.llm).rate)}`
          : undefined,
      ].filter(Boolean) as string[],
    };
  },
  kpiMessages(c: Ctx): NocTipContent {
    return {
      title: "ข้อความ 24 ชม.",
      lines: [
        `${fmt(n(c.llm.message_count, n(c.traffic.messages_24h)))} messages`,
        `Window ${n(c.llm.window_hours, 24)} ชม.`,
        c.promUp ? `Req/s ปัจจุบัน: ${n(c.traffic.requests_per_sec).toFixed(2) || "—"}` : "ใช้ข้อมูลจาก DB",
      ],
    };
  },
  kpiCost(c: Ctx): NocTipContent {
    const { thb, usd, rate } = costInThb(c.llm);
    const bdThb = c.llm.cost_breakdown_thb as Record<string, number> | undefined;
    const bdUsd = c.llm.cost_breakdown_usd as Record<string, number> | undefined;
    const bd =
      bdThb ??
      (bdUsd
        ? { prompt: n(bdUsd.prompt) * rate, completion: n(bdUsd.completion) * rate, embedding: n(bdUsd.embedding) * rate }
        : undefined);
    return {
      title: "ค่าใช้จ่าย AI (ค่าประมาณ)",
      lines: [
        `รวม ~฿${fmtThb(thb)} (≈$${usd.toFixed(4)}) / 24 ชม. — คำนวณจากโทเคนจริง × อัตราคงที่ ไม่ใช่บิลจริง`,
        bd
          ? `Prompt ฿${fmtThb(n(bd.prompt))} · Completion ฿${fmtThb(n(bd.completion))} · Embed ฿${fmtThb(n(bd.embedding))}`
          : undefined,
        "อัตรา: $0.00015/1k prompt · $0.0006/1k completion · $0.00002/1k embed",
        `แปลงเป็นบาทที่ 1 USD = ฿${rate.toFixed(2)} (ค่าคงที่ ตั้งได้ผ่าน env USD_THB_RATE)`,
        `Model: ${String(c.gateway.llm_model ?? "—")} · Embed: ${String(c.gateway.embed_model ?? "—")}`,
      ].filter(Boolean) as string[],
    };
  },
  kpiIngest(c: Ctx): NocTipContent {
    return {
      title: "คิว Ingest",
      lines: [
        `Backlog ${n(c.workers.ingest_queue_backlog)} งาน`,
        `Failed ${n(c.workers.failed_ingest_jobs)} · Row errors ${n(c.workers.ingestion_error_rows)}`,
        n(c.workers.ingest_queue_backlog) > 20 ? "⚠ สูง — ควรเพิ่ม worker" : "✓ ระดับปกติ",
      ],
    };
  },
  kpiError(c: Ctx): NocTipContent {
    const rate = n(c.traffic.error_rate_5xx);
    return {
      title: "HTTP 5xx Error Rate",
      lines: [
        `อัตรา ${(rate * 100).toFixed(2)}% ใน 24 ชม.`,
        rate > 0.005 ? "⚠ เกิน 0.5% — ตรวจ API logs" : "✓ อยู่ในเกณฑ์",
        c.promUp ? "จาก Prometheus" : "จาก DB / fallback",
      ],
    };
  },
  tokens(c: Ctx): NocTipContent {
    return {
      title: "Token Usage",
      lines: ["Prompt + Completion 7 วัน", `รวม ~${fmt(c.tokens24h)} โทเคน (24 ชม.)`, "สีน้ำเงิน = prompt · ม่วง = completion"],
    };
  },
  users(c: Ctx): NocTipContent {
    return { title: "Active Users", lines: ["ผู้ใช้ที่ login/ใช้งานรายวัน 7 วัน", `Peak ล่าสุดในกราฟ = แนวโน้มการใช้งาน`] };
  },
  messages(c: Ctx): NocTipContent {
    return { title: "Messages", lines: ["จำนวนข้อความแชทต่อวัน", "รวม user + assistant messages"] };
  },
  connectivity(c: Ctx, ok: number, total: number): NocTipContent {
    return {
      title: "Connectivity",
      lines: [`${ok}/${total} services พร้อม`, "ชี้เมาส์ที่แต่ละ service เพื่อดูรายละเอียด", c.promUp ? "Prometheus: UP" : "Prometheus: DOWN / fallback"],
    };
  },
  service(name: string, ok: boolean, degraded?: boolean, detail?: string): NocTipContent {
    const status = ok ? (degraded ? "Degraded" : "OK") : degraded ? "Degraded / ไม่มีข้อมูล" : "DOWN";
    return {
      title: name.toUpperCase(),
      lines: [
        `สถานะ: ${status} (จาก /readyz probe จริง)`,
        detail ? `รายละเอียด: ${detail}` : undefined,
        ok ? "เชื่อมต่อและตอบสนองปกติ" : degraded ? "ตรวจสอบไม่ได้ครบ — ดูรายละเอียดด้านบน" : "ต้องตรวจสอบ / restart",
      ].filter(Boolean) as string[],
    };
  },
  traffic(c: Ctx, title: string): NocTipContent {
    return {
      title,
      lines: [
        c.promUp ? "ข้อมูลจาก Prometheus scrape 24 ชม." : "Prometheus ไม่พร้อม — ใช้ hourly messages",
        c.traffic.error ? `Error: ${String(c.traffic.error).slice(0, 60)}` : `Error rate 5xx: ${(n(c.traffic.error_rate_5xx) * 100).toFixed(2)}%`,
        `SSE connections: ${n(c.traffic.sse_connections)}`,
      ],
    };
  },
  sessions(c: Ctx): NocTipContent {
    return { title: "Sessions Created", lines: ["เซสชันแชทที่สร้างใหม่ต่อวัน 7 วัน", `Active now: ${n(c.users.active_sessions_15m)}`] };
  },
  ingestJobs(c: Ctx): NocTipContent {
    return { title: "Ingest Jobs", lines: ["งาน ingest เอกสารต่อวัน", `Queue ปัจจุบัน: ${n(c.workers.ingest_queue_backlog)}`] };
  },
  requestsPerSec(c: Ctx): NocTipContent {
    return {
      title: "Requests/s · p95 latency",
      lines: [
        c.promUp ? "sum(rate(spark_http_requests_total[1m])) — เหมือน Grafana" : "ต้องเปิด Prometheus เพื่อดูค่านี้",
        c.traffic.requests_per_sec != null ? `ปัจจุบัน ${n(c.traffic.requests_per_sec).toFixed(2)} req/s` : "ไม่มี snapshot ล่าสุด",
        c.promUp ? "histogram_quantile(0.95, ...) — เหมือน Grafana" : "ต้องเปิด Prometheus เพื่อดู latency",
        c.traffic.p95_latency_sec != null ? `p95 ปัจจุบัน ~${n(c.traffic.p95_latency_sec).toFixed(3)} s` : "ไม่มี snapshot ล่าสุด",
      ],
    };
  },
  latency(c: Ctx): NocTipContent {
    return {
      title: "p95 latency (s)",
      lines: [
        c.promUp ? "histogram_quantile(0.95, ...) — เหมือน Grafana" : "ต้องเปิด Prometheus เพื่อดู latency",
        c.traffic.p95_latency_sec != null ? `p95 ปัจจุบัน ~${n(c.traffic.p95_latency_sec).toFixed(3)} s` : "ไม่มี snapshot ล่าสุด",
      ],
    };
  },
  infra(c: Ctx): NocTipContent {
    return {
      title: "Infrastructure",
      lines: [
        `PG chunks ${n(c.qdrant.postgres_chunks_total).toLocaleString()} · Qdrant ${n(c.qdrant.qdrant_points_total).toLocaleString()}`,
        `Drift ${n(c.qdrant.chunk_drift)} ${c.qdrant.chunk_drift_alert ? "⚠" : ""}`,
        `Storage ${n(c.storage.document_gib).toFixed(1)} GiB · ${n(c.storage.document_count)} docs`,
        `Host: ${String(c.qdrant.host ?? "—")}`,
      ],
    };
  },
  cellChunks(c: Ctx): NocTipContent {
    return {
      title: "Chunks (Postgres)",
      lines: [`${n(c.qdrant.postgres_chunks_total).toLocaleString()} chunks ใน PostgreSQL (ค่าจริง ณ ตอนโหลด)`, "แหล่งความจริงของ chunk metadata"],
    };
  },
  cellVectors(c: Ctx): NocTipContent {
    return {
      title: "Vectors (Qdrant)",
      lines: [`${n(c.qdrant.qdrant_points_total).toLocaleString()} points (นับจริงจากทุก collection)`, `Strategy: ${String(c.qdrant.shard_strategy ?? "—")}`],
    };
  },
  cellDrift(c: Ctx): NocTipContent {
    return {
      title: "Chunk Drift",
      lines: [`ต่างกัน ${n(c.qdrant.chunk_drift)} รายการ`, c.qdrant.chunk_drift_alert ? "⚠ เกิน threshold — กดซิงก์ Qdrant" : "✓ อยู่ในเกณฑ์"],
    };
  },
  cellDocs(c: Ctx): NocTipContent {
    return { title: "Documents", lines: [`${n(c.storage.document_count)} ไฟล์`, `Backend: ${String(c.storage.backend ?? "local")}`] };
  },
  cellStorageQdrant(c: Ctx): NocTipContent {
    const est = c.storage.qdrant_gib_estimate;
    return {
      title: "Storage — Qdrant",
      lines: [
        est != null ? `~${n(est).toFixed(2)} GiB (ประมาณจากจำนวน vector)` : "ไม่มีข้อมูล",
        "Qdrant ไม่มี API บอกขนาดจริงบนดิสก์ ค่านี้เป็นค่าประมาณ ไม่ใช่ค่าจริง",
      ],
    };
  },
  cellStorageMinio(c: Ctx): NocTipContent {
    const h = (c.storage.health as Record<string, unknown>) ?? {};
    return {
      title: "Storage — MinIO / Object Storage",
      lines: [`${n(c.storage.document_gib).toFixed(2)} GiB (ไฟล์เอกสารต้นฉบับ)`, h.ok === false ? "⚠ Storage มีปัญหา" : "✓ Storage OK"],
    };
  },
  cellStoragePostgres(c: Ctx): NocTipContent {
    return {
      title: "Storage — PostgreSQL",
      lines: [`${n(c.storage.postgres_gib).toFixed(2)} GiB`, "ขนาดจริงของฐานข้อมูลทั้งหมด (pg_database_size)"],
    };
  },
  cellFailed(c: Ctx): NocTipContent {
    return {
      title: "Failed Ingest",
      lines: [`${n(c.workers.failed_ingest_jobs)} งานล้มเหลวใน 7 วันล่าสุด`, "งานเก่ากว่านั้นไม่นับ (ดูประวัติเต็มใน admin ingest)"],
    };
  },
  cellDlq(c: Ctx): NocTipContent {
    return {
      title: "Ingest Row Errors",
      lines: [`${n(c.workers.ingestion_error_rows)} rows ใน 7 วันล่าสุด`, "บันทึกข้อผิดพลาดรายแถวจากงาน ingest"],
    };
  },
  cellCelery(c: Ctx): NocTipContent {
    const celery = (c.workers.celery as Record<string, unknown>) ?? {};
    return {
      title: "Celery Workers",
      lines: [
        celery.ok ? `${n(celery.workers)} worker online` : "⚠ Worker down",
        Array.isArray(celery.worker_names) ? String((celery.worker_names as string[]).join(", ")).slice(0, 50) : "",
      ].filter(Boolean),
    };
  },
  ai(c: Ctx): NocTipContent {
    return {
      title: "AI & RAG",
      lines: [
        `LLM: ${String(c.gateway.llm_model ?? "—")}`,
        `Profile: ${String(c.gateway.llm_profile ?? "—")}`,
        `Agentic ${c.agentic.open ? "OPEN ⚠" : "closed"} · RAG ${c.rag.open ? "OPEN ⚠" : "closed"}`,
      ],
    };
  },
  cellAgentic(c: Ctx): NocTipContent {
    if (c.agentic.enabled === false) {
      return {
        title: "Agentic Circuit",
        lines: [
          "OFF — agentic routing ไม่ได้เปิดใช้ในบิลด์นี้ จึงไม่มี circuit ทำงานจริง",
          "ทุก request ใช้เส้นทาง RAG ปกติ (legacy)",
        ],
      };
    }
    return {
      title: "Agentic Circuit",
      lines: [c.agentic.open ? "⚠ เปิดอยู่ — routing อาจ fallback" : "✓ ปิด · ปกติ", `Mode: ${String(c.agentic.routing_mode ?? "—")}`, `Canary: ${n(c.agentic.canary_pct)}%`],
    };
  },
  cellRag(c: Ctx): NocTipContent {
    return {
      title: "RAG Circuit Breaker",
      lines: [
        c.rag.open ? "⚠ เปิด — retrieval ถูก block" : "✓ ปิด · ปกติ (สถานะจริงจาก breaker)",
        `Window ${n(c.rag.window_sec, 600)}s`,
      ],
    };
  },
  cellRoute(c: Ctx): NocTipContent {
    return {
      title: "Routing Mode",
      lines: [
        `${String(c.agentic.routing_mode ?? "legacy")}`,
        c.agentic.enabled === false ? "คงที่ที่ legacy — agentic routing ปิดใช้งาน" : "legacy / canary / agentic",
      ],
    };
  },
  cellCache(c: Ctx): NocTipContent {
    if (c.semanticCache.enabled === false) {
      return { title: "Semantic Cache", lines: ["ปิดใช้งาน (SEMANTIC_CACHE_ENABLED)", `Entries ในตาราง ${n(c.semanticCache.total_cache_entries)}`] };
    }
    return {
      title: "Semantic Cache",
      lines: [
        c.semanticCache.hit_rate_pct != null
          ? `Hit rate ${n(c.semanticCache.hit_rate_pct).toFixed(0)}% (hits ${n(c.semanticCache.hits_total)} / misses ${n(c.semanticCache.misses_total)})`
          : "ยังไม่มีสถิติ hit/miss จาก Prometheus",
        `Entries ${n(c.semanticCache.total_cache_entries)} · มี embedding ${n(c.semanticCache.entries_with_embedding)}`,
      ],
    };
  },
  cellUsers(c: Ctx): NocTipContent {
    return { title: "Registered Users", lines: [`${n(c.users.total_registered)} บัญชี`, `Super admin ${n(c.users.super_admins)} คน`] };
  },
  cellUsers24h(c: Ctx): NocTipContent {
    return { title: "Active 24h", lines: [`${n(c.users.active_users_24h)} ผู้ใช้`, "unique users ใน 24 ชม."] };
  },
  ingestDonut(c: Ctx, slices: Array<{ label: string; value: number }>): NocTipContent {
    const total = slices.reduce((a, s) => a + s.value, 0);
    return {
      title: "Ingest by Status",
      lines: slices.map((s) => `${s.label}: ${s.value} (${total ? ((s.value / total) * 100).toFixed(0) : 0}%)`),
    };
  },
  actions(c: Ctx): NocTipContent {
    return { title: "ดำเนินการระบบ", lines: ["Super admin only", "ชี้ที่ปุ่มแต่ละอันเพื่อดูคำอธิบาย", `Live SSE: ${n(c.traffic.sse_connections)}`] };
  },
  actionClear(): NocTipContent {
    return { title: "ล้างแคช", lines: ["ล้าง Redis / semantic cache", "ใช้เมื่อข้อมูล stale หรือหลัง deploy"] };
  },
  actionSync(): NocTipContent {
    return { title: "ซิงก์ Qdrant", lines: ["Reconcile chunks กับ vector store", "แก้ drift ระหว่าง PG ↔ Qdrant"] };
  },
  actionMaint(on: boolean): NocTipContent {
    return on
      ? { title: "ปิดบำรุงรักษา", lines: ["เปิดใช้งานแชท/อัปโหลดตามปกติ", "ผู้ใช้กลับมาใช้งานได้เต็มรูปแบบ"] }
      : { title: "เปิดบำรุงรักษา", lines: ["Read-only สำหรับผู้ใช้ทั่วไป", "แสดงข้อความที่กำหนดในช่องด้านบน"] };
  },
  actionAgentic(): NocTipContent {
    return { title: "รีเซ็ต Agentic CB", lines: ["ปิด agentic circuit breaker", "หลังแก้ root cause แล้วเท่านั้น"] };
  },
  actionRag(): NocTipContent {
    return { title: "รีเซ็ต RAG CB", lines: ["ปิด RAG circuit breaker", "ใช้เมื่อ retrieval errors หายแล้ว"] };
  },
  postgres(c: Ctx): NocTipContent {
    const pg = (c.data.postgres ?? {}) as Record<string, unknown>;
    const locks = (pg.locks as unknown[]) ?? [];
    const slow = (pg.slow_queries as unknown[]) ?? [];
    return {
      title: "PostgreSQL",
      lines: [
        pg.pool_checked_out != null
          ? `Connection ใช้งานอยู่ ${n(pg.pool_checked_out)} / ${n(pg.pool_capacity)} (pool ${n(pg.pool_size)} + overflow ${n(pg.max_overflow)})`
          : `Pool size ${n(pg.pool_size)}`,
        `${locks.length} lock types · ${slow.length} slow queries (จาก pg_locks / pg_stat_activity)`,
      ],
    };
  },
  pgPool(c: Ctx): NocTipContent {
    const pg = (c.data.postgres ?? {}) as Record<string, unknown>;
    return {
      title: "Connections in use",
      lines: [
        pg.pool_checked_out != null
          ? `เช็คเอาต์อยู่ ${n(pg.pool_checked_out)} จากเพดาน ${n(pg.pool_capacity)} (pool ${n(pg.pool_size)} + overflow สูงสุด ${n(pg.max_overflow)})`
          : "pool ไม่รายงานตัวเลข (ไม่ใช่ QueuePool)",
        n(pg.pool_overflow_in_use) > 0 ? `⚠ ใช้ overflow อยู่ ${n(pg.pool_overflow_in_use)} connection` : "✓ ยังไม่แตะ overflow",
        `สถานะดิบ: ${String(pg.pool_status ?? "—").slice(0, 80)}`,
      ],
    };
  },
  pgIdle(c: Ctx): NocTipContent {
    const pg = (c.data.postgres ?? {}) as Record<string, unknown>;
    return {
      title: "Idle connections",
      lines: [
        pg.pool_checked_in != null
          ? `${n(pg.pool_checked_in)} connection ว่างอยู่ใน pool พร้อมให้ request ถัดไปใช้`
          : "pool ไม่รายงานตัวเลข",
        "ตัวเลขจริงจาก SQLAlchemy pool ของโปรเซส API",
      ],
    };
  },
  pgLocks(c: Ctx): NocTipContent {
    const locks = ((c.data.postgres ?? {}) as Record<string, unknown>).locks as Array<{ mode?: string; cnt?: number }> | undefined;
    return {
      title: "Active Locks",
      lines: locks?.length
        ? locks.map((l) => `${l.mode ?? "?"}: ${n(l.cnt)}`)
        : ["ไม่มี lock ที่รายงาน"],
    };
  },
  pgSlow(c: Ctx): NocTipContent {
    const slow = ((c.data.postgres ?? {}) as Record<string, unknown>).slow_queries as Array<{ duration_sec?: number; query?: string }> | undefined;
    return {
      title: "Slow Queries",
      lines: slow?.length
        ? slow.slice(0, 3).map((q) => `~${n(q.duration_sec)}s ${String(q.query ?? "").slice(0, 40)}`)
        : ["ไม่มี slow query ที่ active"],
    };
  },
  eval(c: Ctx): NocTipContent {
    const eq = (c.data.eval_quality ?? {}) as Record<string, unknown>;
    return {
      title: "Eval Quality Gate",
      lines: [
        eq.has_report ? "มี CI eval report" : "ยังไม่มี report",
        eq.gate_passed === false ? "⚠ Gate FAILED" : eq.gate_passed ? "✓ Gate passed" : "—",
        eq.report_path ? String(eq.report_path) : "",
      ].filter(Boolean),
    };
  },
  evalReport(c: Ctx): NocTipContent {
    const eq = (c.data.eval_quality ?? {}) as Record<string, unknown>;
    return { title: "Eval Report", lines: [eq.has_report ? "พบ report ล่าสุด" : "ไม่พบ report", String(eq.report_path ?? "—")] };
  },
  evalGate(c: Ctx): NocTipContent {
    const eq = (c.data.eval_quality ?? {}) as Record<string, unknown>;
    return {
      title: "Quality Gate",
      lines: [
        !eq.has_report ? "รอ CI eval run" : eq.gate_passed ? "ผ่านเกณฑ์คุณภาพ" : "ไม่ผ่าน — ตรวจ metrics ใน report",
      ],
    };
  },
  otel(c: Ctx): NocTipContent {
    const ot = (c.data.otel_tracing ?? {}) as Record<string, unknown>;
    return {
      title: "OpenTelemetry",
      lines: [
        ot.enabled ? "Tracing เปิดอยู่" : "Tracing ปิด",
        ot.service_name ? `Service: ${String(ot.service_name)}` : "ตั้ง OTEL_EXPORTER ใน .env",
        ot.enabled ? "ดู trace ใน Jaeger / Tempo" : "",
      ].filter(Boolean),
    };
  },
};
