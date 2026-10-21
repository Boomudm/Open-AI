"use client";

import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Tooltip } from "@/components/ui/Tooltip";
import { api, type PolicyFinding } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ShieldAlert } from "lucide-react";
import { useState } from "react";

export type ReleaseDocumentButtonProps = {
  docId: string;
  factoryId?: string | null;
  compact?: boolean;
  className?: string;
};

const SEVERITY_STYLE: Record<string, string> = {
  high: "text-red-600 dark:text-red-400 border-red-500/40 bg-red-500/10",
  medium: "text-amber-700 dark:text-amber-400 border-amber-500/40 bg-amber-500/10",
  low: "text-gemini-muted border-gemini-border/50 bg-gemini-hover/40",
};

function FindingRow({ finding }: { finding: PolicyFinding }) {
  const style = SEVERITY_STYLE[finding.severity.toLowerCase()] ?? SEVERITY_STYLE.low;
  return (
    <li className={cn("rounded-lg border px-3 py-2 text-xs space-y-1", style)}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono font-medium">{finding.rule_id}</span>
        <span className="uppercase text-[10px] tracking-wide">{finding.severity}</span>
      </div>
      <p>{finding.message}</p>
      {finding.matched_text && (
        <p className="font-mono text-[10px] text-gemini-muted truncate">“{finding.matched_text}”</p>
      )}
    </li>
  );
}

/** Review + release a document quarantined by the content-safety scanner (ingest_status: quarantined/pending_release). */
export function ReleaseDocumentButton({ docId, factoryId, compact = false, className }: ReleaseDocumentButtonProps) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [releasing, setReleasing] = useState(false);
  const [releaseError, setReleaseError] = useState("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: queryKeys.documentPolicyFindings(docId),
    queryFn: () => api.getDocumentPolicyFindings(docId),
    enabled: open,
  });

  if (!canWriteFactory(factoryId)) {
    return null;
  }

  async function handleRelease() {
    setReleasing(true);
    setReleaseError("");
    try {
      await api.releaseDocument(docId);
      await qc.invalidateQueries({ queryKey: queryKeys.documents() });
      setOpen(false);
    } catch (err) {
      setReleaseError(parseApiError(err));
    } finally {
      setReleasing(false);
    }
  }

  return (
    <>
      <Tooltip content="รอตรวจสอบเนื้อหา — ดูสาเหตุ/ปล่อยเอกสาร" disabled={!compact}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
          aria-label="ดูสาเหตุกักเอกสารและปล่อยเอกสาร"
          className={cn(
            "inline-flex items-center gap-1 gemini-theme-transition gemini-focus-ring",
            compact
              ? "h-8 w-8 justify-center rounded-full text-amber-600 dark:text-amber-400 hover:bg-amber-500/10"
              : "text-xs px-2.5 py-1 rounded-full border border-amber-500/40 text-amber-700 dark:text-amber-400 hover:bg-amber-500/10",
            className
          )}
        >
          <ShieldAlert className={compact ? "h-4 w-4" : "h-3.5 w-3.5"} />
          {!compact && <span>รอตรวจสอบ</span>}
        </button>
      </Tooltip>

      <Modal open={open} onClose={() => setOpen(false)} title="เอกสารรอตรวจสอบเนื้อหา">
        <div className="space-y-3">
          <p className="text-xs text-gemini-muted">
            ระบบ content-safety scanner กักเอกสารนี้ไว้อัตโนมัติ ต้องมีผู้ดูแลรีวิวก่อนจึงจะใช้ค้นหาได้
            (ผู้ที่อัปโหลดเอกสารเองปล่อยเอกสารตัวเองไม่ได้ — ต้องเป็นผู้ดูแลอีกคนรีวิว)
          </p>

          {isLoading && <p className="text-xs text-gemini-muted">กำลังโหลดสาเหตุ…</p>}
          {isError && <p className="text-xs text-red-500">{parseApiError(error)}</p>}

          {data && (
            <>
              <div className="flex items-center gap-2 text-xs">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <span>
                  Risk score: <span className="font-mono">{data.content_risk_score?.toFixed(2) ?? "—"}</span>
                  {" · "}
                  {data.findings.length} finding{data.findings.length === 1 ? "" : "s"}
                </span>
              </div>
              {data.findings.length > 0 ? (
                <ul className="space-y-1.5 max-h-64 overflow-y-auto gemini-scrollbar">
                  {data.findings.map((f, i) => (
                    <FindingRow key={`${f.rule_id}-${i}`} finding={f} />
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-gemini-muted">ไม่มีรายละเอียด finding เพิ่มเติม</p>
              )}
            </>
          )}

          {releaseError && <p className="text-xs text-red-500">{releaseError}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="secondary" size="sm" onClick={() => setOpen(false)}>
              ปิด
            </Button>
            <Button type="button" variant="primary" size="sm" loading={releasing} onClick={() => void handleRelease()}>
              ปล่อยเอกสาร (อนุมัติ)
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
