export type LlmModelChoice = "fast" | "advanced";

export type ThemePreference = "light" | "dark" | "system";

export type RagSourceDefinition = {
  id: string;
  label: string;
  description: string;
  documentType: string;
};

export const RAG_SOURCE_DEFINITIONS: RagSourceDefinition[] = [
  {
    id: "manuals",
    label: "คู่มือเครื่องจักร",
    description: "คู่มือเทคนิคและเอกสารอุปกรณ์",
    documentType: "machine_manual",
  },
  {
    id: "repairs",
    label: "ประวัติการซ่อม",
    description: "Log การบำรุงรักษาและบันทึกความล้มเหลว",
    documentType: "repair_history",
  },
  {
    id: "sop",
    label: "ขั้นตอนการทำงานและ SOP",
    description: "ขั้นตอนมาตรฐานและคำสั่งงาน",
    documentType: "sop",
  },
  {
    id: "near_miss",
    label: "รายงาน Near-miss",
    description: "ฐานความรู้ด้านความปลอดภัยและเหตุการณ์ใกล้เคียงอุบัติเหตุ",
    documentType: "near_miss",
  },
];

export type ChatSettings = {
  model: LlmModelChoice;
  ragSources: Record<string, boolean>;
  saveChatHistory: boolean;
};

export const CHAT_SETTINGS_KEY = "spark_chat_settings";

export const DEFAULT_CHAT_SETTINGS: ChatSettings = {
  model: "fast",
  ragSources: Object.fromEntries(RAG_SOURCE_DEFINITIONS.map((s) => [s.id, true])),
  saveChatHistory: true,
};

export function loadChatSettings(): ChatSettings {
  if (typeof window === "undefined") return DEFAULT_CHAT_SETTINGS;
  try {
    const raw = localStorage.getItem(CHAT_SETTINGS_KEY);
    if (!raw) return DEFAULT_CHAT_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<ChatSettings>;
    return {
      model: parsed.model === "advanced" ? "advanced" : "fast",
      ragSources: {
        ...DEFAULT_CHAT_SETTINGS.ragSources,
        ...(parsed.ragSources ?? {}),
      },
      saveChatHistory: parsed.saveChatHistory !== false,
    };
  } catch {
    return DEFAULT_CHAT_SETTINGS;
  }
}

export function saveChatSettings(settings: ChatSettings): void {
  localStorage.setItem(CHAT_SETTINGS_KEY, JSON.stringify(settings));
}

export function topKForModel(model: LlmModelChoice): number {
  return model === "advanced" ? 10 : 6;
}

/** When exactly one RAG source is enabled, narrow retrieval to that document type. */
export function documentTypeFilter(ragSources: Record<string, boolean>): string | undefined {
  const enabled = RAG_SOURCE_DEFINITIONS.filter((s) => ragSources[s.id] !== false);
  if (enabled.length === 1) return enabled[0].documentType;
  return undefined;
}
