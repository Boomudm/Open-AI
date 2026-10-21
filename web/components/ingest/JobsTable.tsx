"use client";

import {
  DataTable,
  type DataTableColumn,
} from "@/components/ui/DataTable";
import { Select } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Tooltip } from "@/components/ui/Tooltip";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useIngestJobs } from "@/hooks/useIngestJobs";
import { useIngestJobStream } from "@/hooks/useIngestJobStream";
import { api, type JobErrorRow, type JobRow } from "@/lib/api";
import { formatFileSize, truncateFilename } from "@/lib/ingest";
import type { JobStatusFilter } from "@/hooks/useIngestPageFilters";
import { DEFAULT_PAGE_SIZE } from "@/lib/types/pagination";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useCallback, useMemo, useState } from "react";

const STATUS_OPTIONS: { value: JobStatusFilter; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "partial", label: "Partial" },
  { value: "failed", label: "Failed" },
];

function jobStatusBadge(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "completed" || normalized === "done") return "OK";
  if (normalized === "failed" || normalized === "error" || normalized === "dlq") return "CRITICAL";
  // pending_release: legacy hold state from older ingest jobs, distinct from
  // "running", but not just generic info either.
  if (normalized === "running" || normalized === "partial" || normalized === "pending_release") return "WARNING";
  return "INFO";
}

function jobStatusLabel(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "dlq") return "failed";
  if (normalized === "pending_release") return "pending";
  return status;
}

function formatTs(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("th-TH", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return value;
  }
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const mins = Math.floor(seconds / 60);
  const rem = Math.round(seconds % 60);
  return `${mins}m ${rem}s`;
}

function jobErrorSummary(row: JobRow): { code: string | null; detail: string | null } {
  if (row.last_error_code || row.last_error_detail) {
    return {
      code: row.last_error_code,
      detail: row.last_error_detail,
    };
  }
  if (!row.error_message) {
    return { code: null, detail: null };
  }
  const [code, ...rest] = row.error_message.split(":");
  return {
    code: rest.length ? code.trim() : null,
    detail: rest.length ? rest.join(":").trim() : row.error_message,
  };
}

function JobErrorsList({ jobId }: { jobId: string }) {
  const [errors, setErrors] = useState<JobErrorRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    if (loaded) return;
    setLoading(true);
    try {
      const rows = await api.jobErrors(jobId, { limit: 20 });
      setErrors(rows);
      setLoaded(true);
    } catch {
      setErrors([]);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }, [jobId, loaded]);

  if (!loaded && !loading) {
    void load();
  }

  if (loading) {
    return (
      <p className="text-xs font-mono text-spark-text-muted py-1">Loading errors…</p>
    );
  }

  if (!errors?.length) {
    return (
      <p className="text-xs font-sans text-spark-text-muted py-1">
        ไม่มี row-level errors
      </p>
    );
  }

  return (
    <ul className="space-y-1 max-h-40 overflow-y-auto spark-scrollbar">
      {errors.map((e) => (
        <li
          key={e.error_id}
          className="text-xs font-mono border-l-2 border-spark-danger/40 pl-2 text-spark-text-secondary"
        >
          {e.reason_code && (
            <span className="text-spark-danger">{e.reason_code}: </span>
          )}
          {e.reason_detail ?? "—"}
          {e.row_number != null && (
            <span className="text-spark-text-muted"> · row {e.row_number}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "pending"]);

function jobDisplayProgress(
  row: JobRow,
  stream: { percent: number; rows_ok: number; rows_total: number; stage: string } | null
) {
  if (stream) {
    // SSE and the polled row can briefly disagree — never let the bar move
    // backward when switching between the two sources.
    return { ...stream, percent: Math.max(stream.percent, row.progress_percent) };
  }
  return {
    percent: row.progress_percent,
    rows_ok: row.rows_ok,
    rows_total: row.rows_total,
    stage: "",
  };
}

function JobDetailPanel({
  job,
  streamStage,
}: {
  job: JobRow;
  streamStage?: string | null;
}) {
  const filename = job.original_filename ?? "—";
  const errorSummary = jobErrorSummary(job);

  return (
    <div className="rounded-sm border border-spark-border bg-spark-bg/50 px-3 py-3 space-y-3">
      <p className="font-mono text-[10px] uppercase tracking-wider text-spark-text-muted">
        Job details · {job.job_id.slice(0, 8)}…
        {streamStage ? ` · ${streamStage}` : ""}
      </p>
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2 text-xs font-mono">
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">File</dt>
          <dd className="text-spark-text-primary break-all">{filename}</dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Size</dt>
          <dd className="text-spark-text-primary tabular-nums">
            {formatFileSize(job.file_size_bytes)}
          </dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Factory</dt>
          <dd className="text-spark-text-primary">{job.factory_id ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Machine</dt>
          <dd className="text-spark-text-primary">{job.machine_id ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Indexed</dt>
          <dd className="text-spark-text-primary tabular-nums">
            {job.chunks_count} chunks{job.page_count != null ? ` · ${job.page_count} pages` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Duration</dt>
          <dd className="text-spark-text-primary tabular-nums">
            {formatDuration(job.duration_seconds)}
          </dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Document</dt>
          <dd className="text-spark-text-primary">{job.document_ingest_status ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-spark-text-muted text-[10px] uppercase tracking-wider">Errors</dt>
          <dd className="text-spark-text-primary tabular-nums">{job.error_count}</dd>
        </div>
      </dl>
      {(errorSummary.code || errorSummary.detail) && (
        <div className="rounded-sm border border-spark-danger/30 bg-spark-danger/5 px-2 py-2">
          <p className="font-mono text-[10px] uppercase tracking-wider text-spark-danger">
            {errorSummary.code ?? "ingest_error"}
          </p>
          <p className="text-xs text-spark-text-secondary mt-1 line-clamp-3">
            {errorSummary.detail}
          </p>
        </div>
      )}
      <div>
        <p className="font-mono text-[10px] uppercase tracking-wider text-spark-text-muted mb-1">
          Row errors
        </p>
        <JobErrorsList jobId={job.job_id} />
      </div>
    </div>
  );
}

type JobsTableProps = {
  statusFilter: JobStatusFilter;
  onStatusFilterChange: (status: JobStatusFilter) => void;
  page: number;
  onPageChange: (page: number) => void;
  /** Hide toolbar refresh when the page header owns refresh */
  hideRefresh?: boolean;
};

export function JobsTable({
  statusFilter,
  onStatusFilterChange,
  page,
  onPageChange,
  hideRefresh = false,
}: JobsTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const { jobs, isLoading, isFetching, error, refresh, hasNextPage, pageSize } =
    useIngestJobs({ status: statusFilter || undefined, page, expandedJobId: expandedId });

  const expandedJob = useMemo(
    () => jobs.find((j) => j.job_id === expandedId) ?? null,
    [jobs, expandedId]
  );

  const streamEnabled = Boolean(
    expandedJob && ACTIVE_JOB_STATUSES.has(expandedJob.status.toLowerCase())
  );
  const { progress: streamProgress } = useIngestJobStream(
    streamEnabled ? expandedId : null,
    streamEnabled
  );

  const streamForExpanded =
    streamProgress && expandedId && streamProgress.job_id === expandedId
      ? {
          percent: streamProgress.percent,
          rows_ok: streamProgress.rows_ok,
          rows_total: streamProgress.rows_total,
          stage: streamProgress.stage,
        }
      : null;

  const columns: DataTableColumn<JobRow>[] = [
    {
      id: "expand",
      header: "",
      accessor: (row) => (
        <Tooltip
          content={
            expandedId === row.job_id ? "ซ่อนรายละเอียดงาน" : "ดูรายละเอียดงานนำเข้า"
          }
        >
          <button
            type="button"
            aria-label={expandedId === row.job_id ? "ซ่อนรายละเอียด" : "ดูรายละเอียดงาน"}
            aria-expanded={expandedId === row.job_id}
            onClick={(e) => {
              e.stopPropagation();
              setExpandedId((id) => (id === row.job_id ? null : row.job_id));
            }}
            className="p-0.5 text-spark-text-muted hover:text-spark-accent spark-focus-ring rounded-sm"
          >
            {expandedId === row.job_id ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        </Tooltip>
      ),
      width: "32px",
    },
    {
      id: "job_id",
      header: "Job ID",
      accessor: (row) => (
        <span className="font-mono text-xs text-spark-text-secondary" title={row.job_id}>
          {row.job_id.slice(0, 8)}…
        </span>
      ),
      width: "100px",
    },
    {
      id: "original_filename",
      header: "File",
      accessor: (row) => {
        const name = row.original_filename;
        if (!name) {
          return <span className="text-spark-text-muted">—</span>;
        }
        return (
          <span
            className="font-mono text-xs text-spark-text-primary truncate max-w-[140px] inline-block"
            title={name}
          >
            {truncateFilename(name, 20)}
          </span>
        );
      },
    },
    {
      id: "document_type",
      header: "Type",
      accessor: (row) => (
        <span className="font-mono text-xs">{row.document_type}</span>
      ),
    },
    {
      id: "status",
      header: "Status",
      accessor: (row) => (
        <div className="flex items-center gap-1.5">
          <StatusBadge status={jobStatusBadge(row.status)} size="sm" />
          <span className="font-mono text-[10px] uppercase text-spark-text-muted">
            {jobStatusLabel(row.status)}
          </span>
        </div>
      ),
    },
    {
      id: "progress",
      header: "Progress",
      accessor: (row) => {
        const live =
          row.job_id === expandedId ? jobDisplayProgress(row, streamForExpanded) : null;
        const prog = live ?? jobDisplayProgress(row, null);
        return (
        <div className="space-y-1 min-w-[110px]">
          <div className="h-1.5 rounded-full bg-spark-border overflow-hidden">
            <div
              className="h-full bg-spark-accent"
              style={{ width: `${Math.max(0, Math.min(100, prog.percent))}%` }}
            />
          </div>
          <span className="font-mono text-[10px] tabular-nums text-spark-text-muted">
            {prog.rows_ok}/{prog.rows_total} rows
            {row.rows_skipped > 0 ? ` · ${row.rows_skipped} skip` : ""}
            {prog.stage ? ` · ${prog.stage}` : ""}
          </span>
        </div>
        );
      },
    },
    {
      id: "indexed",
      header: "Indexed",
      accessor: (row) => (
        <span className="font-mono text-xs tabular-nums text-spark-text-secondary">
          {row.chunks_count} chunks
          {row.page_count != null ? ` · ${row.page_count}p` : ""}
        </span>
      ),
    },
    {
      id: "started_at",
      header: "Started",
      accessor: (row) => (
        <span className="font-mono text-xs text-spark-text-muted">
          {formatTs(row.started_at)}
        </span>
      ),
    },
    {
      id: "finished_at",
      header: "Runtime",
      accessor: (row) => (
        <div className="flex flex-col">
          <span className="font-mono text-xs text-spark-text-secondary tabular-nums">
            {formatDuration(row.duration_seconds)}
          </span>
          <span className="font-mono text-[10px] text-spark-text-muted">
            {formatTs(row.finished_at)}
          </span>
        </div>
      ),
    },
    {
      id: "error",
      header: "Error",
      accessor: (row) => {
        const summary = jobErrorSummary(row);
        if (!summary.code && !summary.detail) {
          return <span className="text-spark-text-muted">—</span>;
        }
        return (
          <div className="max-w-[220px]">
            {summary.code && (
              <span className="font-mono text-[10px] uppercase text-spark-danger">
                {summary.code}
              </span>
            )}
            <p className="text-xs text-spark-critical font-sans line-clamp-2">
              {summary.detail}
            </p>
          </div>
        );
      },
      defaultVisible: true,
    },
  ];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Select
          label="Status"
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value as JobStatusFilter)}
          options={STATUS_OPTIONS}
          className="min-w-[160px]"
        />
        {!hideRefresh && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refresh()}
            loading={isFetching && !isLoading}
            tooltip="รีเฟรชสถานะงานนำเข้า"
          >
            Refresh
          </Button>
        )}
      </div>

      <DataTable
        columns={columns}
        data={{
          items: jobs,
          total: hasNextPage ? page * pageSize + 1 : (page - 1) * pageSize + jobs.length,
          page,
          page_size: pageSize,
        }}
        isLoading={isLoading}
        isError={!!error && jobs.length === 0}
        errorMessage={error ?? undefined}
        onRetry={refresh}
        page={page}
        pageSize={pageSize}
        onPageChange={onPageChange}
        rowKey={(row) => row.job_id}
        emptyTitle="No ingestion jobs yet"
        emptyMessage="Upload a document in the panel beside this table, or run python scripts/seed_demo_docs.py for demo PDFs"
      />

      {expandedJob && (
        <JobDetailPanel job={expandedJob} streamStage={streamForExpanded?.stage} />
      )}
    </div>
  );
}
