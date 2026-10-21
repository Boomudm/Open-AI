"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  CloudUpload,
  FileText,
  Trash2,
  Wrench,
  Users,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Eye,
  ShieldAlert,
  RotateCcw,
  Clock,
  FileWarning,
  Zap,
  XCircle,
} from "lucide-react";

import { MachineSelector } from "@/components/ui/MachineSelector";
import { IngestPreflightBanner } from "@/components/ingest/IngestPreflightBanner";
import { ReleaseDocumentButton } from "@/components/documents/ReleaseDocumentButton";
import { validateIngestFile } from "@/components/ingest/FileDropZone";
import { useEnsureFactorySelected } from "@/hooks/useEnsureFactorySelected";
import { useUploadUrlState } from "@/hooks/useUploadUrlState";
import { useDocumentTypes } from "@/hooks/useDocumentTypes";
import { useFactoriesQuery } from "@/hooks/useFactoriesQuery";
import { useIngestPreflight } from "@/hooks/useIngestPreflight";
import { useMachinesInfinite } from "@/hooks/useMachinesQuery";
import { useJobPositions } from "@/hooks/useJobPositions";
import { useIngestJobs } from "@/hooks/useIngestJobs";
import { canUploadDocuments } from "@/lib/auth";
import { api, type IngestFileResponse, type JobRow, type JobErrorRow } from "@/lib/api";
import {
  documentTypeLabel,
  documentTypeRecommendsMachine,
  documentTypeRequiresMachine,
  documentTypeShowsMachineField,
} from "@/lib/document-categories";
import { isFileAcceptedForDocumentType } from "@/lib/ingest-upload";
import {
  filterTypesForPipeline,
  guessDocumentTypeFromFilename,
  resolveDefaultDocumentType,
} from "@/lib/ingest-defaults";
import { formatFileSize, truncateFilename } from "@/lib/ingest";
import { parseApiError } from "@/lib/errors";
import { useUiStore } from "@/stores/uiStore";
import { cn } from "@/lib/cn";
import Link from "next/link";

/* ──────────────────── constants ──────────────────── */
type Pipeline = "machinery" | "enterprise";

/* ──────────────────── helpers ──────────────────── */
const inputCls = "w-full h-10 rounded-lg border border-gemini-border dark:border-gemini-dark-border bg-gemini-bg dark:bg-gemini-dark-bg px-3 text-sm text-gemini-text dark:text-gemini-dark-text outline-none focus:ring-2 focus:ring-gemini-blue/30 focus:border-gemini-blue transition-shadow";

function Field({ label, badge, sub, children }: {
  label: string; badge?: string; sub?: string; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline gap-2">
        <span className="text-[13px] font-medium text-gemini-text dark:text-gemini-dark-text">{label}</span>
        {badge && <span className="text-[10px] font-semibold text-amber-500 uppercase tracking-wider">{badge}</span>}
        {sub && <span className="text-[11px] text-gemini-muted ml-auto">{sub}</span>}
      </div>
      {children}
    </div>
  );
}

function statusLabel(s: string) {
  const map: Record<string, string> = {
    queued: "รอคิว", running: "กำลังประมวลผล", completed: "สำเร็จ",
    partial: "สำเร็จบางส่วน", failed: "ล้มเหลว", dlq: "ล้มเหลว",
    pending: "รอดำเนินการ", pending_release: "รอประมวลผลต่อ",
  };
  return map[s.toLowerCase()] ?? s;
}

function errorCodeThai(code: string | null): string | null {
  if (!code) return null;
  const map: Record<string, string> = {
    PII_BLOCKED: "พบข้อมูลส่วนบุคคลที่ต้องปกปิด",
    OCR_FAILED: "อ่านเอกสารสแกนไม่สำเร็จ",
    PARSE_FAILED: "แปลงไฟล์ไม่สำเร็จ — รูปแบบไม่รองรับ",
    EMBED_FAILED: "สร้างข้อมูลค้นหาไม่สำเร็จ",
    STORAGE_UNAVAILABLE: "ระบบจัดเก็บไฟล์ไม่พร้อม",
    TIMEOUT: "ใช้เวลานานเกินกำหนด",
    POLICY_VIOLATION: "พบข้อสังเกตจากการสแกนเนื้อหา",
    QUARANTINED: "รอประมวลผลต่อจากสถานะเดิม",
  };
  return map[code] ?? null;
}

function estimateRemaining(job: JobRow): string | null {
  if (!job.started_at || job.progress_percent <= 0 || job.progress_percent >= 100) return null;
  const elapsed = (Date.now() - new Date(job.started_at).getTime()) / 1000;
  if (elapsed < 2) return null;
  const total = elapsed / (job.progress_percent / 100);
  const remaining = Math.max(0, total - elapsed);
  if (remaining < 60) return `~${Math.ceil(remaining)} วินาที`;
  return `~${Math.ceil(remaining / 60)} นาที`;
}

function fmtDuration(sec: number | null): string {
  if (sec == null) return "—";
  if (sec < 60) return `${sec.toFixed(sec < 10 ? 1 : 0)} วินาที`;
  const m = Math.floor(sec / 60); const r = Math.round(sec % 60);
  return `${m} นาที ${r} วินาที`;
}

function fmtTime(v: string | null): string {
  if (!v) return "—";
  try { return new Date(v).toLocaleString("th-TH", { dateStyle: "short", timeStyle: "short" }); }
  catch { return v; }
}

/* ──────────────────── Job Card ──────────────────── */
function JobCard({ job, onRetried }: { job: JobRow; onRetried: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [errors, setErrors] = useState<JobErrorRow[] | null>(null);
  const [loadingErrors, setLoadingErrors] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const status = job.status.toLowerCase();
  const isFailed = status === "failed" || status === "dlq";
  const isActive = status === "queued" || status === "running" || status === "pending";
  const isDone = status === "completed";
  const isPendingReview = status === "pending_release" || job.document_ingest_status === "quarantined";
  const est = isActive ? estimateRemaining(job) : null;

  async function loadErrors() {
    if (errors !== null) return;
    setLoadingErrors(true);
    try {
      const rows = await api.jobErrors(job.job_id, { limit: 30 });
      setErrors(rows);
    } catch { setErrors([]); }
    finally { setLoadingErrors(false); }
  }

  async function retry() {
    setRetrying(true);
    try {
      await api.retryJob(job.job_id);
      onRetried();
    } catch { /* silent */ }
    finally { setRetrying(false); }
  }

  useEffect(() => {
    if (!expanded || !isFailed || errors !== null) return;
    setLoadingErrors(true);
    api
      .jobErrors(job.job_id, { limit: 30 })
      .then(setErrors)
      .catch(() => setErrors([]))
      .finally(() => setLoadingErrors(false));
  }, [expanded, isFailed, errors, job.job_id]);

  return (
    <div className={cn(
      "rounded-xl border transition-all",
      isFailed ? "border-red-500/30 bg-red-500/[0.03]" :
      isPendingReview ? "border-amber-500/40 bg-amber-500/[0.04]" :
      isDone ? "border-emerald-500/30 bg-emerald-500/[0.03]" :
      isActive ? "border-sky-500/30 bg-sky-500/[0.03]" :
      "border-gemini-border/50 dark:border-gemini-dark-border/50"
    )}>
      {/* header */}
      <button type="button" onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left">
        <span className={cn("h-2.5 w-2.5 rounded-full shrink-0",
          isDone ? "bg-emerald-500" : isFailed ? "bg-red-500" : isPendingReview ? "bg-amber-500" : isActive ? "bg-sky-500 animate-pulse" : "bg-gemini-muted"
        )} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text truncate">
            {job.original_filename ? truncateFilename(job.original_filename, 40) : "ไม่ระบุชื่อไฟล์"}
          </p>
          <p className="text-xs text-gemini-muted mt-0.5 flex items-center gap-2 flex-wrap">
            <span>{documentTypeLabel(job.document_type)}</span>
            {job.machine_id && <span>· {job.machine_id}</span>}
            <span className={isPendingReview ? "text-amber-600 dark:text-amber-400 font-medium" : undefined}>
              · {isPendingReview ? "รอประมวลผลต่อ" : statusLabel(job.status)}
            </span>
          </p>
        </div>
        <div className="text-right shrink-0">
          {isPendingReview && <ShieldAlert className="h-5 w-5 text-amber-500" />}
          {isActive && (
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-sky-600 dark:text-sky-400 tabular-nums">
                {Math.round(job.progress_percent)}%
              </span>
              {est && (
                <span className="text-[10px] text-gemini-muted flex items-center gap-0.5">
                  <Clock className="h-3 w-3" /> {est}
                </span>
              )}
            </div>
          )}
          {isDone && <CheckCircle2 className="h-5 w-5 text-emerald-500" />}
          {isFailed && <XCircle className="h-5 w-5 text-red-500" />}
        </div>
        {expanded ? <ChevronDown className="h-4 w-4 text-gemini-muted shrink-0" /> : <ChevronRight className="h-4 w-4 text-gemini-muted shrink-0" />}
      </button>

      {/* progress bar */}
      {isActive && (
        <div className="px-4 pb-3">
          <div className="h-1.5 rounded-full bg-gemini-border/50 dark:bg-gemini-dark-border/50 overflow-hidden">
            <div className="h-full bg-sky-500 transition-all duration-500 rounded-full"
              style={{ width: `${Math.max(2, Math.min(100, job.progress_percent))}%` }} />
          </div>
        </div>
      )}

      {/* expanded detail */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gemini-border/30 dark:border-gemini-dark-border/30 pt-3">
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <p className="text-gemini-muted">ขนาดไฟล์</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text">{formatFileSize(job.file_size_bytes)}</p>
            </div>
            <div>
              <p className="text-gemini-muted">จำนวนส่วนย่อย</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text">{job.chunks_count} ส่วน{job.page_count != null ? ` · ${job.page_count} หน้า` : ""}</p>
            </div>
            <div>
              <p className="text-gemini-muted">ใช้เวลา</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text">{fmtDuration(job.duration_seconds)}</p>
            </div>
            <div>
              <p className="text-gemini-muted">เริ่มเมื่อ</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text">{fmtTime(job.started_at)}</p>
            </div>
            <div>
              <p className="text-gemini-muted">โรงงาน</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text">{job.factory_id ?? "—"}</p>
            </div>
            <div>
              <p className="text-gemini-muted">ประมวลผล</p>
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text tabular-nums">สำเร็จ {job.rows_ok} / {job.rows_total} รายการ{job.rows_skipped > 0 ? ` · ข้ามไป ${job.rows_skipped} รายการ` : ""}</p>
            </div>
          </div>

          {/* legacy pending release */}
          {isPendingReview && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                <ShieldAlert className="h-3.5 w-3.5" />
                รอประมวลผลต่อ
              </div>
              <p className="text-xs text-gemini-text dark:text-gemini-dark-text">
                เอกสารนี้อยู่ในสถานะรอปล่อยใช้งานจากงาน ingest เดิม สามารถปล่อยต่อเพื่อให้ค้นหาได้
              </p>
              {job.doc_id && (
                <ReleaseDocumentButton docId={job.doc_id} factoryId={job.factory_id} />
              )}
            </div>
          )}

          {/* error info */}
          {isFailed && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-red-600 dark:text-red-400">
                <FileWarning className="h-3.5 w-3.5" />
                สาเหตุที่ล้มเหลว
              </div>
              {job.last_error_code && (
                <p className="text-xs font-medium text-red-500">
                  {errorCodeThai(job.last_error_code) ?? job.last_error_code}
                </p>
              )}
              {(job.last_error_detail || job.error_message) && (
                <p className="text-xs text-gemini-text dark:text-gemini-dark-text">
                  {job.last_error_detail || job.error_message}
                </p>
              )}
              {loadingErrors && <p className="text-xs text-gemini-muted">กำลังโหลดรายละเอียด...</p>}
              {errors && errors.length > 0 && (
                <div className="space-y-1 max-h-32 overflow-y-auto gemini-scrollbar mt-2">
                  {errors.map((e) => (
                    <div key={e.error_id} className="text-[11px] border-l-2 border-red-400/40 pl-2 text-gemini-muted">
                      {e.reason_code && <span className="text-red-500 font-medium">{errorCodeThai(e.reason_code) ?? e.reason_code}: </span>}
                      {e.reason_detail ?? "—"}
                      {e.row_number != null && <span className="opacity-60"> · บรรทัดที่ {e.row_number}</span>}
                    </div>
                  ))}
                </div>
              )}
              <button type="button" onClick={retry} disabled={retrying}
                className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 hover:bg-red-500/10 disabled:opacity-50 mt-1">
                <RotateCcw className={cn("h-3.5 w-3.5", retrying && "animate-spin")} />
                {retrying ? "กำลังลองใหม่..." : "ลองอัปโหลดอีกครั้ง"}
              </button>
            </div>
          )}

          {isDone && job.error_count > 0 && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 text-xs">
              <p className="text-amber-700 dark:text-amber-400 font-medium">
                สำเร็จ แต่มี {job.error_count} รายการที่ข้ามไป
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ──────────────────── Main Page ──────────────────── */
function UploadContent() {
  useEnsureFactorySelected();
  const qc = useQueryClient();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const { machineId: urlMachineId } = useUploadUrlState();
  const canUpload = canUploadDocuments(selectedFactoryId);

  const [pipeline, setPipeline] = useState<Pipeline>("machinery");
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("");
  const [machineId, setMachineId] = useState(urlMachineId ?? "");
  const [machineSearch, setMachineSearch] = useState("");
  const [title, setTitle] = useState("");
  const [visiblePositionIds, setVisiblePositionIds] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IngestFileResponse | null>(null);
  const [suggestedType, setSuggestedType] = useState<string | null>(null);
  const [userOverrodeType, setUserOverrodeType] = useState(false);
  const lockRef = useRef(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const userPickedTypeRef = useRef(false);
  const { result: preflight, loading: preflightLoading, error: preflightError, run: runPreflight, reset: resetPreflight } =
    useIngestPreflight();

  const { documentTypes: allDocTypes } = useDocumentTypes();
  const { data: factories = [] } = useFactoriesQuery();
  const { data: jobPositions = [], isLoading: positionsLoading } = useJobPositions();
  const factoryId = selectedFactoryId ?? (factories.length === 1 ? factories[0].factory_id : "");

  const filteredDocTypes = useMemo(
    () => filterTypesForPipeline(allDocTypes, pipeline),
    [allDocTypes, pipeline]
  );

  const showMachine = pipeline === "machinery" && (Boolean(urlMachineId) || documentTypeShowsMachineField(docType));
  const machineRequired = documentTypeRequiresMachine(docType);
  const showMachineSuggestion = showMachine && !machineRequired && !machineId && documentTypeRecommendsMachine(docType);
  const { machines, isLoading: machinesLoading, hasMore, loadMore } =
    useMachinesInfinite(machineSearch, { enabled: Boolean(factoryId) && showMachine, factoryId: factoryId || null });

  const { jobs, refresh: refreshJobs } = useIngestJobs({ page: 1, pageSize: 20 });

  useEffect(() => {
    if (filteredDocTypes.length === 0) return;
    if (docType && filteredDocTypes.includes(docType)) return;
    const next = resolveDefaultDocumentType({
      pipeline,
      defaultMachineId: urlMachineId ?? undefined,
      availableTypes: filteredDocTypes,
    });
    setDocType(next);
  }, [filteredDocTypes, docType, pipeline, urlMachineId]);

  useEffect(() => {
    if (file && docType && !isFileAcceptedForDocumentType(file, docType)) {
      setFile(null);
      resetPreflight();
      setSuggestedType(null);
      setError("รูปแบบไฟล์ไม่ตรงกับประเภทเอกสาร");
    }
  }, [docType, file, resetPreflight]);

  const triggerPreflight = useCallback(
    (nextFile: File) => {
      if (!factoryId) return;
      runPreflight({
        file: nextFile,
        factoryId,
        machineId: machineId || undefined,
        documentType: userPickedTypeRef.current ? docType : undefined,
      });
    },
    [factoryId, machineId, docType, runPreflight]
  );

  useEffect(() => {
    if (!file || !factoryId) return;
    triggerPreflight(file);
  }, [file, factoryId, docType, machineId, triggerPreflight]);

  useEffect(() => {
    if (!preflight?.document_type || !file || userPickedTypeRef.current) return;
    const t = preflight.document_type;
    if (filteredDocTypes.includes(t) && t !== docType) {
      setDocType(t);
      setSuggestedType(t);
    }
  }, [preflight?.document_type, file, filteredDocTypes, docType]);

  const switchPipeline = useCallback((p: Pipeline) => {
    setPipeline(p);
    setFile(null);
    setDocType("");
    setMachineId(urlMachineId ?? "");
    setTitle("");
    setVisiblePositionIds([]);
    setError("");
    setResult(null);
    setSuggestedType(null);
    userPickedTypeRef.current = false;
    setUserOverrodeType(false);
    resetPreflight();
  }, [urlMachineId, resetPreflight]);

  const applyFile = useCallback((f: File | null) => {
    if (!f) {
      setFile(null);
      setError("");
      resetPreflight();
      setSuggestedType(null);
      userPickedTypeRef.current = false;
      setUserOverrodeType(false);
      return;
    }
    const err = validateIngestFile(f);
    if (err) {
      setError(err);
      return;
    }
    setFile(f);
    setError("");
    userPickedTypeRef.current = false;
    setUserOverrodeType(false);
    const guessed = guessDocumentTypeFromFilename(f.name, filteredDocTypes);
    if (guessed) {
      setDocType(guessed);
      setSuggestedType(guessed);
    }
    triggerPreflight(f);
  }, [filteredDocTypes, resetPreflight, triggerPreflight]);

  async function submit() {
    if (loading || lockRef.current) return;
    if (!file) { setError("กรุณาเลือกไฟล์"); return; }
    if (!factoryId) { setError("กรุณาเลือกโรงงาน"); return; }
    if (machineRequired && !machineId) { setError("เอกสารประเภทนี้ต้องเลือกเครื่องจักร"); return; }
    if (!preflight?.accepted) {
      setError(preflight?.reasons?.[0] ?? "ไฟล์ยังไม่ผ่านการตรวจสอบ");
      return;
    }
    setError(""); setResult(null); setLoading(true); lockRef.current = true;
    try {
      const fd = new FormData();
      fd.append("file", file); fd.append("factory_id", factoryId);
      if (docType) fd.append("document_type", docType);
      if (machineId) fd.append("machine_id", machineId);
      if (title.trim()) fd.append("title", title.trim());
      if (visiblePositionIds.length > 0) fd.append("visible_position_ids", JSON.stringify(visiblePositionIds));
      const res = await api.ingestFile(fd);
      setResult(res); setFile(null); setTitle(""); setVisiblePositionIds([]);
      qc.invalidateQueries({ queryKey: ["ingestJobs"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
    } catch (err) { setError(parseApiError(err)); }
    finally { setLoading(false); lockRef.current = false; }
  }

  if (!canUpload) {
    return (
      <div className="flex items-center justify-center h-full p-8">
        <div className="text-center space-y-3">
          <ShieldAlert className="h-12 w-12 text-gemini-muted mx-auto" />
          <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">ไม่มีสิทธิ์อัปโหลดเอกสาร</p>
          <p className="text-xs text-gemini-muted">สิทธิ์นี้จำกัดเฉพาะ Admin และ Operator</p>
          <Link href="/chat" className="text-xs text-gemini-blue hover:underline inline-block mt-2">กลับหน้าแชท</Link>
        </div>
      </div>
    );
  }

  const isMachinery = pipeline === "machinery";
  const formatHint = "PDF · XLSX · DOCX";
  const canSubmit = Boolean(file) && !loading && !preflightLoading && (preflight?.accepted ?? false);

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* top bar */}
      <div className="shrink-0 border-b border-gemini-border/40 dark:border-gemini-dark-border/40 px-6 py-3 flex items-center justify-between gap-4">
        <h1 className="text-base font-bold text-gemini-text dark:text-gemini-dark-text">อัปโหลดเอกสาร</h1>
        <div
          className="flex rounded-lg border border-gemini-border dark:border-gemini-dark-border overflow-hidden text-xs font-medium"
          aria-label="ประเภทเอกสาร"
        >
          {(["machinery","enterprise"] as const).map((p) => {
            const active = pipeline === p;
            const Ic = p === "machinery" ? Wrench : Users;
            return (
              <button key={p} type="button" onClick={() => switchPipeline(p)} className={cn(
                "flex items-center gap-1.5 px-4 py-2 transition-colors",
                active ? (p === "machinery" ? "bg-sky-500/15 text-sky-600 dark:text-sky-400" : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400")
                  : "text-gemini-muted hover:bg-gemini-surface dark:hover:bg-gemini-dark-surface"
              )}>
                <Ic className="h-3.5 w-3.5" />{p === "machinery" ? "เอกสารเครื่องจักร" : "เอกสารองค์กร / HR"}
              </button>
            );
          })}
        </div>
      </div>

      {/* main area */}
      <div className="flex-1 min-h-0 overflow-y-auto gemini-scrollbar">
        <div className="max-w-6xl mx-auto px-6 py-6 space-y-6">
          {/* upload row: dropzone left, fields right */}
          <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-6" data-testid="upload-form">
            {/* LEFT — drop zone */}
            <div className="space-y-2">
              <p className="text-[13px] font-medium text-gemini-text dark:text-gemini-dark-text">
                ไฟล์เอกสาร <span className="text-[10px] font-semibold text-amber-500 uppercase ml-1">จำเป็น</span>
              </p>
              <input ref={fileRef} type="file"
                accept=".pdf,.xlsx,.docx"
                className="sr-only"
                id="ingest-file"
                onChange={(e) => { applyFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
              <button type="button" onClick={() => fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); applyFile(e.dataTransfer.files?.[0] ?? null); }}
	                disabled={loading}
	                className={cn(
	                  "w-full aspect-[4/3] rounded-2xl border-2 border-dashed transition-all cursor-pointer",
	                  "flex flex-col items-center justify-center text-center gap-3 px-6",
	                  "disabled:opacity-50 disabled:cursor-not-allowed",
	                  file ? (isMachinery ? "border-sky-500/40 bg-sky-500/5" : "border-emerald-500/40 bg-emerald-500/5")
	                    : dragOver ? "border-gemini-blue bg-gemini-blue/5"
	                    : "border-gemini-border/60 dark:border-gemini-dark-border/60 hover:border-gemini-blue/40"
	                )}>
	                {file ? (
	                  <>
	                    <FileText className={cn("h-12 w-12", isMachinery ? "text-sky-500" : "text-emerald-500")} />
                    <div>
                      <p className="text-sm font-semibold text-gemini-text dark:text-gemini-dark-text break-all">{file.name}</p>
                      <p className="text-xs text-gemini-muted mt-1">{formatFileSize(file.size)}</p>
                    </div>
                    <span onClick={(e) => { e.stopPropagation(); setFile(null); }}
                      className="inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-600 cursor-pointer mt-2 border border-red-500/30 rounded-lg px-3 py-1.5 hover:bg-red-500/10 transition-colors">
                      <Trash2 className="h-3 w-3" /> ลบไฟล์
                    </span>
                  </>
                ) : (
                  <>
                    <CloudUpload className="h-12 w-12 text-gemini-muted/40" />
                    <div>
                      <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">คลิกเลือกไฟล์ หรือลากมาวาง</p>
                      <p className="text-xs text-gemini-muted mt-1">รองรับ {formatHint} · สูงสุด 50 MB</p>
                    </div>
                  </>
                )}
              </button>
            </div>

            {/* RIGHT — fields */}
            <div className="space-y-4">
              {file && (
                <IngestPreflightBanner
                  result={preflight}
                  loading={preflightLoading}
                  error={preflightError}
                  suggestedType={suggestedType}
                  userOverrodeType={userOverrodeType}
                />
              )}

              <Field label="ประเภทเอกสาร" badge="จำเป็น">
                <select
                  value={docType}
                  onChange={(e) => {
                    userPickedTypeRef.current = true;
                    setUserOverrodeType(true);
                    setSuggestedType(null);
                    setDocType(e.target.value);
                  }}
                  className={inputCls}
                >
                  {filteredDocTypes.map((t) => <option key={t} value={t}>{documentTypeLabel(t)}</option>)}
                </select>
              </Field>

              {showMachine && (
                <Field
                  label="ผูกกับเครื่องจักร"
	                  badge={machineRequired ? "จำเป็น" : undefined}
	                  sub={machineRequired ? undefined : "เว้นว่าง = เอกสารกลาง"}
	                >
	                  <MachineSelector machines={machines} value={machineId || null}
	                    onChange={(id) => setMachineId(id ?? "")} isLoading={machinesLoading}
	                    hasMore={hasMore} onLoadMore={() => loadMore()} placeholder="เลือกเครื่องจักร..."
	                    serverSearch searchQuery={machineSearch} onSearchQueryChange={setMachineSearch} />
	                  {showMachineSuggestion && (
	                    <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
	                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
	                      <p>
	                        เอกสารประเภทนี้มักเป็นของเครื่องใดเครื่องหนึ่ง ถ้าเป็นเอกสารเฉพาะเครื่อง แนะนำให้เลือกเครื่องก่อนอัปโหลด
	                      </p>
	                    </div>
	                  )}
	                </Field>
	              )}

              <Field label="ชื่อเอกสาร" sub="เว้นว่าง = ใช้ชื่อไฟล์">
                <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="ตั้งชื่อเอกสาร..." className={inputCls} />
              </Field>

              {/* access control */}
              <Field label="สิทธิ์เข้าถึง" sub="ไม่เลือก = ทุกตำแหน่ง">
                <div className="rounded-lg border border-gemini-border/60 dark:border-gemini-dark-border/60 p-3 space-y-2">
                  <p className="text-[11px] text-gemini-muted flex items-center gap-1"><Eye className="h-3 w-3" /> เลือกตำแหน่งที่เห็นเอกสารนี้ได้</p>
                  {positionsLoading ? <p className="text-xs text-gemini-muted py-1">โหลดตำแหน่ง...</p>
                  : jobPositions.length === 0 ? <p className="text-xs text-gemini-muted py-1">ไม่มีตำแหน่งในระบบ — ทุกคนเห็นได้</p>
                  : (
                    <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto gemini-scrollbar">
                      {jobPositions.map((pos) => {
                        const on = visiblePositionIds.includes(pos.position_id);
                        return (
                          <button key={pos.position_id} type="button"
                            onClick={() => setVisiblePositionIds((p) => on ? p.filter((x) => x !== pos.position_id) : [...p, pos.position_id])}
                            className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors",
                              on ? "border-gemini-blue/50 bg-gemini-blue/10 text-gemini-blue dark:text-gemini-dark-blue font-medium"
                                : "border-gemini-border dark:border-gemini-dark-border text-gemini-muted hover:bg-gemini-surface/60 dark:hover:bg-gemini-dark-surface/60")}>
                            {on && <CheckCircle2 className="h-3 w-3" />}{pos.name_th}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              </Field>

              {/* messages */}
              {error && (
                <div className="flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5">
                  <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-600 dark:text-red-400">{error}</p>
                </div>
              )}
              {result && (
                <div className="flex items-start gap-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                  <p className="text-xs text-emerald-700 dark:text-emerald-400 font-medium">อัปโหลดสำเร็จ — ดูสถานะด้านล่าง</p>
                </div>
              )}

              {/* submit */}
              <button type="button" onClick={submit} disabled={!canSubmit}
                className={cn(
                  "w-full h-11 rounded-xl text-sm font-semibold transition-all flex items-center justify-center gap-2",
                  "disabled:opacity-40 disabled:cursor-not-allowed",
                  file && !loading
                    ? isMachinery ? "bg-sky-500 hover:bg-sky-600 text-white shadow-lg shadow-sky-500/20"
                      : "bg-emerald-500 hover:bg-emerald-600 text-white shadow-lg shadow-emerald-500/20"
                    : "bg-gemini-surface dark:bg-gemini-dark-surface text-gemini-muted border border-gemini-border dark:border-gemini-dark-border"
                )}>
                {loading ? <><Loader2 className="h-4 w-4 animate-spin" /> กำลังอัปโหลด...</>
                  : preflightLoading ? <><Loader2 className="h-4 w-4 animate-spin" /> กำลังตรวจสอบ...</>
                  : <><CloudUpload className="h-4 w-4" /> อัปโหลดเอกสาร</>}
              </button>
            </div>
          </div>

          {/* ── Job Tracker ── */}
          <div id="jobs" className="border-t border-gemini-border/40 dark:border-gemini-dark-border/40 pt-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-sm font-bold text-gemini-text dark:text-gemini-dark-text">สถานะการประมวลผล</h2>
                <p className="text-xs text-gemini-muted mt-0.5">ติดตามความคืบหน้าเอกสารที่อัปโหลด</p>
              </div>
              <button type="button" onClick={() => refreshJobs()}
                className="text-xs text-gemini-muted hover:text-gemini-blue flex items-center gap-1 transition-colors">
                <RotateCcw className="h-3 w-3" /> รีเฟรช
              </button>
            </div>

            {jobs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gemini-border/60 dark:border-gemini-dark-border/60 py-12 text-center">
                <Zap className="h-8 w-8 text-gemini-muted/40 mx-auto mb-2" />
                <p className="text-sm text-gemini-muted">ยังไม่มีงานนำเข้า</p>
                <p className="text-xs text-gemini-muted/70 mt-0.5">อัปโหลดเอกสารด้านบนเพื่อเริ่มต้น</p>
              </div>
            ) : (
              <div className="space-y-2">
                {jobs.map((job) => (
                  <JobCard key={job.job_id} job={job} onRetried={() => refreshJobs()} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function UploadPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-full text-sm text-gemini-muted">กำลังโหลด…</div>}>
      <UploadContent />
    </Suspense>
  );
}
