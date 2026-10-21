"use client";

import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { BadgeCheck, Check, Copy, RotateCw, Square, ThumbsDown, ThumbsUp, Volume2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type Reaction = "up" | "down" | null;

type AiMessageActionsProps = {
  content: string;
  onRegenerate?: () => void;
  regenerating?: boolean;
  onVerify?: () => void;
  verifying?: boolean;
  showVerify?: boolean;
  verified?: boolean;
  className?: string;
};

const actionBtn =
  "h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring text-gemini-muted/80 dark:text-gemini-dark-muted/80 hover:text-gemini-blue dark:hover:text-gemini-dark-blue hover:bg-gemini-hover/60 dark:hover:bg-gemini-dark-hover/60";

function speechText(content: string): string {
  return content
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_>#-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 4000);
}

function pickThaiVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !window.speechSynthesis) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((voice) => voice.lang.toLowerCase().startsWith("th")) ??
    voices.find((voice) => voice.lang.toLowerCase().startsWith("en")) ??
    voices[0] ??
    null
  );
}

export function AiMessageActions({
  content,
  onRegenerate,
  regenerating,
  onVerify,
  verifying,
  showVerify,
  verified,
  className,
}: AiMessageActionsProps) {
  const [reaction, setReaction] = useState<Reaction>(null);
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const readableText = useMemo(() => speechText(content), [content]);

  useEffect(() => {
    setSpeechSupported(
      typeof window !== "undefined" &&
        "speechSynthesis" in window &&
        "SpeechSynthesisUtterance" in window
    );
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis && speaking) {
        window.speechSynthesis.cancel();
      }
    };
  }, [speaking]);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard may be unavailable */
    }
  }, [content]);

  const handleReaction = (value: Reaction) => {
    setReaction((prev) => (prev === value ? null : value));
  };

  const handleSpeak = useCallback(() => {
    if (!speechSupported || !readableText) return;
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }

    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(readableText);
    utterance.lang = "th-TH";
    utterance.rate = 0.95;
    utterance.pitch = 1;
    const voice = pickThaiVoice();
    if (voice) {
      utterance.voice = voice;
      utterance.lang = voice.lang || "th-TH";
    }
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    synth.speak(utterance);
  }, [readableText, speaking, speechSupported]);

  return (
    <div
      className={cn("inline-flex items-center gap-1 flex-wrap", className)}
      role="toolbar"
      aria-label="ตัวเลือกสำหรับคำตอบ Neo Chat"
    >
      <Tooltip content="ถูกใจคำตอบนี้">
        <button
          type="button"
          onClick={() => handleReaction("up")}
          className={cn(
            actionBtn,
            reaction === "up" && "text-gemini-blue dark:text-gemini-dark-blue"
          )}
          aria-label="ถูกใจ"
          aria-pressed={reaction === "up"}
        >
          <ThumbsUp className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </Tooltip>

      <Tooltip content="ไม่ถูกใจคำตอบนี้">
        <button
          type="button"
          onClick={() => handleReaction("down")}
          className={cn(
            actionBtn,
            reaction === "down" && "text-gemini-blue dark:text-gemini-dark-blue"
          )}
          aria-label="ไม่ถูกใจ"
          aria-pressed={reaction === "down"}
        >
          <ThumbsDown className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </Tooltip>

      {onRegenerate && (
        <Tooltip content="สร้างคำตอบใหม่">
          <button
            type="button"
            onClick={onRegenerate}
            disabled={regenerating}
            className={cn(actionBtn, regenerating && "opacity-50 cursor-not-allowed")}
            aria-label="ทำซ้ำ"
          >
            <RotateCw
              className={cn("h-3.5 w-3.5", regenerating && "animate-spin")}
              strokeWidth={1.5}
            />
          </button>
        </Tooltip>
      )}

      {speechSupported && readableText && (
        <Tooltip content={speaking ? "หยุดอ่านคำตอบ" : "อ่านคำตอบออกเสียง"}>
          <button
            type="button"
            onClick={handleSpeak}
            className={cn(
              actionBtn,
              speaking && "text-gemini-blue dark:text-gemini-dark-blue"
            )}
            aria-label={speaking ? "หยุดอ่านคำตอบ" : "อ่านคำตอบ"}
            aria-pressed={speaking}
          >
            {speaking ? (
              <Square className="h-3.5 w-3.5" strokeWidth={1.5} />
            ) : (
              <Volume2 className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
          </button>
        </Tooltip>
      )}

      {showVerify && onVerify && (
        <Tooltip content={verified ? "ยืนยันแล้ว" : "ยืนยันคำตอบ (admin)"}>
          <button
            type="button"
            onClick={onVerify}
            disabled={verifying || verified}
            className={cn(
              actionBtn,
              verified && "text-gemini-blue dark:text-gemini-dark-blue",
              (verifying || verified) && "opacity-60 cursor-not-allowed"
            )}
            aria-label={verified ? "ยืนยันแล้ว" : "ยืนยันคำตอบ"}
            aria-pressed={verified}
          >
            <BadgeCheck className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </Tooltip>
      )}

      <Tooltip content={copied ? "คัดลอกแล้ว" : "คัดลอกคำตอบ"}>
        <button
          type="button"
          onClick={handleCopy}
          className={cn(
            actionBtn,
            copied && "text-gemini-blue dark:text-gemini-dark-blue"
          )}
          aria-label={copied ? "คัดลอกแล้ว" : "คัดลอกคำตอบ"}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5" strokeWidth={1.5} />
          ) : (
            <Copy className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
        </button>
      </Tooltip>
    </div>
  );
}
