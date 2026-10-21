"use client";

import {
  DEFAULT_CHAT_SETTINGS,
  loadChatSettings,
  saveChatSettings,
  type ChatSettings,
} from "@/lib/chatSettings";
import { useCallback, useEffect, useState } from "react";

export function useChatSettings() {
  const [settings, setSettingsState] = useState<ChatSettings>(DEFAULT_CHAT_SETTINGS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setSettingsState(loadChatSettings());
    setReady(true);
  }, []);

  const setSettings = useCallback((patch: Partial<ChatSettings>) => {
    setSettingsState((prev) => {
      const next = { ...prev, ...patch };
      if (patch.ragSources) {
        next.ragSources = { ...prev.ragSources, ...patch.ragSources };
      }
      saveChatSettings(next);
      window.dispatchEvent(new CustomEvent("spark-chat-settings-change", { detail: next }));
      return next;
    });
  }, []);

  const toggleRagSource = useCallback((id: string, enabled: boolean) => {
    setSettings({ ragSources: { [id]: enabled } });
  }, [setSettings]);

  return { settings, setSettings, toggleRagSource, ready };
}
