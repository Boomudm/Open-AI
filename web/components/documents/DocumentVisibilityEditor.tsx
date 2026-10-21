"use client";

import { Button } from "@/components/ui/Button";
import { useJobPositions } from "@/hooks/useJobPositions";
import { api } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export type DocumentVisibilityEditorProps = {
  docId: string;
  factoryId?: string | null;
  initialPositionIds?: string[];
  className?: string;
};

export function DocumentVisibilityEditor({
  docId,
  factoryId,
  initialPositionIds = [],
  className,
}: DocumentVisibilityEditorProps) {
  const queryClient = useQueryClient();
  const { data: jobPositions = [], isLoading } = useJobPositions();
  const [selected, setSelected] = useState<string[]>(initialPositionIds);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setSelected(initialPositionIds);
  }, [docId, initialPositionIds]);

  if (!canWriteFactory(factoryId)) {
    return null;
  }

  function togglePosition(id: string) {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
    setMessage("");
    setError("");
  }

  async function handleSave() {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await api.patchDocumentVisibility(docId, selected);
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      setMessage("บันทึกสิทธิการมองเห็นแล้ว");
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setSaving(false);
    }
  }

  const dirty =
    selected.length !== initialPositionIds.length ||
    selected.some((id) => !initialPositionIds.includes(id));

  return (
    <div
      className={cn(
        "rounded-lg border border-gemini-border/60 dark:border-gemini-dark-border/60",
        "bg-gemini-surface/40 dark:bg-gemini-dark-surface/40 px-3 py-2 space-y-2",
        className
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-gemini-text dark:text-gemini-dark-text">
          ตำแหน่งที่เห็นเอกสารได้
        </p>
        <Button
          type="button"
          variant="secondary"
          loading={saving}
          disabled={!dirty}
          onClick={() => void handleSave()}
          className="h-7 text-xs px-2"
        >
          บันทึก
        </Button>
      </div>
      <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted">
        ไม่เลือก = ทุกตำแหน่งในโรงงาน
      </p>
      {isLoading ? (
        <p className="text-xs text-gemini-muted">กำลังโหลดตำแหน่ง…</p>
      ) : (
        <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
          {jobPositions.map((pos) => (
            <label
              key={pos.position_id}
              className="inline-flex items-center gap-1 rounded-md border border-gemini-border dark:border-gemini-dark-border px-2 py-0.5 text-[11px] cursor-pointer"
            >
              <input
                type="checkbox"
                checked={selected.includes(pos.position_id)}
                onChange={() => togglePosition(pos.position_id)}
                className="rounded"
              />
              {pos.name_th}
            </label>
          ))}
        </div>
      )}
      {message && <p className="text-[11px] text-spark-success">{message}</p>}
      {error && (
        <p className="text-[11px] text-spark-critical" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
