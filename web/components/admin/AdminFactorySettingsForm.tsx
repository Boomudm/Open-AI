"use client";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { api, type FactorySettingsResponse } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

type Props = {
  factoryId: string;
  onClose: () => void;
};

export function AdminFactorySettingsForm({ factoryId, onClose }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error: loadError } = useQuery({
    queryKey: queryKeys.adminFactorySettings(factoryId),
    queryFn: () => api.adminGetFactorySettings(factoryId),
  });

  const [topK, setTopK] = useState("6");
  const [minScore, setMinScore] = useState("");
  const [ingestBackend, setIngestBackend] = useState("auto");
  const [chunkStrategy, setChunkStrategy] = useState("recursive");
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [timezone, setTimezone] = useState("Asia/Bangkok");
  const [predictiveBackend, setPredictiveBackend] = useState("hybrid");
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (!data) return;
    const rag = (data.effective.rag ?? {}) as {
      top_k_default?: number;
      min_max_score?: number | null;
    };
    const ingest = (data.effective.ingest ?? {}) as {
      backend?: string;
      chunking_strategy?: string;
    };
    const notifications = (data.effective.notifications ?? {}) as {
      enabled?: boolean;
      channels?: Array<{ type?: string; url?: string }>;
    };
    setTopK(String(rag.top_k_default ?? 6));
    setMinScore(rag.min_max_score != null ? String(rag.min_max_score) : "");
    setIngestBackend(String(ingest.backend ?? "auto"));
    setChunkStrategy(String(ingest.chunking_strategy ?? "recursive"));
    setNotificationsEnabled(Boolean(notifications.enabled));
    setTimezone(String(data.effective.timezone ?? "Asia/Bangkok"));
    setPredictiveBackend(String(data.effective.predictive_backend ?? "hybrid"));
    const channels = (notifications.channels ?? []) as Array<{ type?: string; url?: string }>;
    const webhook = channels.find((ch) => ch.type === "webhook");
    setWebhookUrl(webhook?.url ?? "");
  }, [data]);

  const saveSettings = useMutation({
    mutationFn: () => {
      const rag: Record<string, unknown> = {
        top_k_default: Number(topK),
      };
      if (minScore.trim()) {
        rag.min_max_score = Number(minScore);
      }
      const notifications: Record<string, unknown> = {
        enabled: notificationsEnabled,
      };
      if (webhookUrl.trim()) {
        notifications.channels = [{ type: "webhook", url: webhookUrl.trim() }];
      }
      return api.adminPatchFactorySettings(factoryId, {
        rag,
        ingest: {
          backend: ingestBackend as "native",
          chunking_strategy: chunkStrategy as "recursive" | "semantic",
        },
        notifications,
        timezone: timezone.trim() || "Asia/Bangkok",
        predictive_backend: predictiveBackend as "heuristic" | "mcp" | "hybrid",
      });
    },
    onSuccess: () => {
      setSaveError("");
      void qc.invalidateQueries({ queryKey: queryKeys.adminFactorySettings(factoryId) });
    },
    onError: (err: Error) => {
      setSaveError(parseApiError(err) || "บันทึกการตั้งค่าไม่สำเร็จ");
    },
  });

  if (isLoading) {
    return <p className="text-sm text-gemini-muted px-3 py-4">กำลังโหลดการตั้งค่า…</p>;
  }

  if (isError || !data) {
    return (
      <div className="px-3 py-4 text-sm text-red-600 dark:text-red-400">
        {parseApiError(loadError) || "โหลดการตั้งค่าไม่สำเร็จ"}
      </div>
    );
  }

  return (
    <div className="border-t border-gemini-border/50 bg-gemini-surface/40 px-3 py-4 space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h4 className="text-sm font-medium">ตั้งค่าโรงงาน {factoryId}</h4>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          ปิด
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Input
          label="RAG top_k (1–20)"
          type="number"
          min={1}
          max={20}
          value={topK}
          onChange={(e) => setTopK(e.target.value)}
        />
        <Input
          label="RAG min_max_score (0–1, ว่าง = default)"
          type="number"
          min={0}
          max={1}
          step={0.01}
          value={minScore}
          onChange={(e) => setMinScore(e.target.value)}
        />
        <label className="block text-sm">
          <span className="mb-1 block text-gemini-muted">Ingest backend</span>
          <select
            className="w-full rounded-lg border border-gemini-border bg-gemini-bg px-3 py-2"
            value="native"
            disabled
            title="Native Spark is the sole production ingest spine"
          >
            <option value="native">native</option>
          </select>
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-gemini-muted">Chunking strategy</span>
          <select
            className="w-full rounded-lg border border-gemini-border bg-gemini-bg px-3 py-2"
            value={chunkStrategy}
            onChange={(e) => setChunkStrategy(e.target.value)}
          >
            <option value="recursive">recursive</option>
            <option value="semantic">semantic</option>
          </select>
        </label>
        <Input
          label="Timezone"
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
        />
        <label className="block text-sm">
          <span className="mb-1 block text-gemini-muted">Predictive backend</span>
          <select
            className="w-full rounded-lg border border-gemini-border bg-gemini-bg px-3 py-2"
            value={predictiveBackend}
            onChange={(e) => setPredictiveBackend(e.target.value)}
          >
            <option value="hybrid">hybrid (แนะนำ production)</option>
            <option value="heuristic">heuristic</option>
            <option value="mcp">mcp</option>
          </select>
        </label>
        <Input
          label="Webhook URL (แจ้งเตือน)"
          value={webhookUrl}
          onChange={(e) => setWebhookUrl(e.target.value)}
          placeholder="https://hooks.example.com/..."
        />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={notificationsEnabled}
          onChange={(e) => setNotificationsEnabled(e.target.checked)}
        />
        เปิดการแจ้งเตือน outbound (ingest ล้ม / insights hotness)
      </label>

      <EffectiveSummary data={data} />

      {saveError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {saveError}
        </p>
      )}

      <Button
        type="button"
        variant="primary"
        loading={saveSettings.isPending}
        onClick={() => saveSettings.mutate()}
      >
        บันทึกการตั้งค่า
      </Button>
    </div>
  );
}

function EffectiveSummary({ data }: { data: FactorySettingsResponse }) {
  const rag = (data.effective.rag ?? {}) as {
    top_k_default?: number;
    min_max_score?: number | null;
  };
  const ingest = (data.effective.ingest ?? {}) as { backend?: string };
  return (
    <p className="text-xs text-gemini-muted">
      ค่าที่ใช้งานจริง: top_k={String(rag.top_k_default ?? "—")}, min_score=
      {rag.min_max_score != null ? String(rag.min_max_score) : "default"}, backend=
      {String(ingest.backend ?? "auto")}
    </p>
  );
}
