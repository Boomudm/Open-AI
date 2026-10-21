"use client";

import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { ClientPortal } from "@/components/ui/ClientPortal";
import { Input } from "@/components/ui/Input";
import { LoadingState } from "@/components/ui/State";
import { api, type RCAResponse } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { cn } from "@/lib/cn";
import { FileText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

type RCAPanelProps = {
  open: boolean;
  machineId: string | null;
  onClose: () => void;
};

export function RCAPanel({ open, machineId, onClose }: RCAPanelProps) {
  const [symptom, setSymptom] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RCAResponse | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    setLoading(false);
    if (!open) return;
    setSymptom("");
    setError("");
    setResult(null);
  }, [open, machineId]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function onAnalyze() {
    if (!machineId || symptom.trim().length < 3) {
      setError("กรุณาระบุอาการอย่างน้อย 3 ตัวอักษร");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await api.rcaAnalyze(
        {
          machine_id: machineId,
          symptom: symptom.trim(),
        },
        {
          signal: controller.signal,
        }
      );
      if (requestRef.current !== requestId) return;
      setResult(response);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(parseApiError(err));
    } finally {
      if (requestRef.current === requestId) {
        setLoading(false);
      }
    }
  }

  function formatTopCause(cause: RCAResponse["top_causes"][number]) {
    let label = JSON.stringify(cause);
    if (typeof cause.root_cause === "string") {
      label = cause.root_cause;
    } else if (typeof cause.cause === "string") {
      label = cause.cause;
    }
    const pct = typeof cause.pct === "number" ? `${cause.pct}%` : null;
    const count = typeof cause.count === "number" ? `${cause.count}x` : null;
    return [label, pct, count].filter(Boolean).join(" · ");
  }

  if (!open) return null;

  return (
    <ClientPortal>
    <div
      className="fixed inset-0 flex items-end sm:items-center justify-center p-0 sm:p-4"
      style={{ zIndex: Z_OVERLAY_PANEL }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="rca-panel-title"
    >
      <button
        type="button"
        className="absolute inset-0 bg-black/50"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        aria-label="Close RCA panel"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        className={cn(
          "relative w-full sm:max-w-lg max-h-[85vh] overflow-y-auto spark-scrollbar",
          "bg-spark-surface border border-spark-border rounded-t-sm sm:rounded-sm shadow-lg"
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
      >
        <Card padding="md" className="border-0 shadow-none">
          <CardHeader className="mb-0 pb-3">
            <CardTitle id="rca-panel-title">วิเคราะห์สาเหตุ (RCA)</CardTitle>
            <button
              type="button"
              onClick={onClose}
              className="h-8 w-8 flex items-center justify-center rounded-sm text-spark-text-muted hover:bg-spark-hover hover:text-spark-text-primary spark-focus-ring"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </CardHeader>

          <div className="space-y-4 pt-3 border-t border-spark-border">
            <p className="text-xs font-mono text-spark-text-muted">
              Machine:{" "}
              <span className="text-spark-accent">{machineId ?? "—"}</span>
            </p>

            <Input
              label="อาการ / Symptom"
              value={symptom}
              onChange={(e) => setSymptom(e.target.value)}
              placeholder="เช่น ร้อนผิดปกติ, เสียงดัง"
              disabled={loading}
            />

            {error && (
              <p className="text-xs text-spark-critical font-mono" role="alert">
                {error}
              </p>
            )}

            <Button
              variant="primary"
              onClick={onAnalyze}
              loading={loading}
              disabled={!machineId || loading}
              className="w-full sm:w-auto"
            >
              วิเคราะห์
            </Button>

            {loading && <LoadingState message="กำลังวิเคราะห์…" />}

            {result && (
              <div className="space-y-3 pt-2 border-t border-spark-border">
                <div>
                  <p className="text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1">
                    Analysis
                  </p>
                  <p className="text-sm text-spark-text-primary font-sans whitespace-pre-wrap">
                    {result.analysis}
                  </p>
                </div>

                {result.top_causes.length > 0 && (
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1">
                      Top causes
                    </p>
                    <ul className="space-y-1">
                      {result.top_causes.map((cause, i) => (
                        <li
                          key={i}
                          className="text-xs font-sans text-spark-text-secondary border-l-2 border-spark-accent/40 pl-2"
                        >
                          {formatTopCause(cause)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <p className="text-[10px] font-mono text-spark-text-muted">
                  Similar repairs: {result.similar_repairs_count}
                </p>

                {result.manual_sources.length > 0 && (
                  <div>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-spark-text-muted mb-1">
                      Manual sources
                    </p>
                    <ul className="space-y-1">
                      {result.manual_sources.map((s, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-1.5 text-xs text-spark-text-secondary"
                        >
                          <FileText className="h-3 w-3 shrink-0 mt-0.5 text-spark-accent" />
                          <span>
                            {s.source_file ?? s.title ?? s.doc_id ?? "Document"}
                            {s.page != null ? ` · p.${s.page}` : ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
    </ClientPortal>
  );
}
