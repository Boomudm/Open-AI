"use client";

import { ChatAttachmentChips } from "@/components/chat/gemini/ChatAttachmentChips";
import { MachineSelector } from "@/components/ui/MachineSelector";
import { Tooltip } from "@/components/ui/Tooltip";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { useMachinesInfinite } from "@/hooks/useMachinesQuery";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import {
  CHAT_ATTACHMENT_ACCEPT,
  validateChatAttachmentFiles,
} from "@/lib/chat-attachments";
import {
  clampQuestionLength,
  QUESTION_MAX_LENGTH,
} from "@/lib/chatLimits";
import { cn } from "@/lib/cn";
import {
  selectChatInput,
  selectChatSending,
  useChatStore,
} from "@/stores/chatStore";
import { useUiStore } from "@/stores/uiStore";
import { ArrowUp, Mic, Square } from "lucide-react";
import {
  memo,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

const composerIconBtn =
  "shrink-0 h-11 w-11 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover hover:text-gemini-text dark:hover:text-gemini-dark-text";

type MessageInputProps = {
  emptyChat?: boolean;
};

function MessageInputInner({ emptyChat = false }: MessageInputProps) {
  const {
    inputRef,
    sessionId,
    sessionBlocked,
    machineId,
    onMachineChange,
    onSend,
    onAbort,
    machinesEnabled = false,
  } = useChatSession();

  const input = useChatStore(selectChatInput);
  const sending = useChatStore(selectChatSending);
  const setInput = useChatStore((s) => s.setInput);
  const setComposerReady = useChatStore((s) => s.setComposerReady);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingAttachments, setPendingAttachments] = useState<File[]>([]);
  const previewUrlsRef = useRef<Map<File, string>>(new Map());
  const previousSessionIdRef = useRef(sessionId);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);
  const [machineSearch, setMachineSearch] = useState("");
  const setSelectedMachineId = useUiStore((s) => s.setSelectedMachineId);
  const attachmentErrorId = useId();
  const speechStatusId = useId();
  const speechErrorId = useId();

  const {
    machines,
    isLoading: machinesLoading,
    hasMore,
    loadMore,
    isFetchingNextPage,
  } = useMachinesInfinite(machineSearch, {
    enabled: machinesEnabled || Boolean(machineId),
  });

  const handleMachineChange = useCallback(
    (id: string | null) => {
      setSelectedMachineId(id);
      onMachineChange(id);
    },
    [onMachineChange, setSelectedMachineId]
  );

  const handleInputChange = useCallback(
    (value: string) => {
      setComposerReady(true);
      setInput(value);
    },
    [setComposerReady, setInput]
  );

  const getPreviewUrl = useCallback((file: File): string | undefined => {
    if (!file.type.startsWith("image/")) return undefined;
    const existing = previewUrlsRef.current.get(file);
    if (existing) return existing;
    const url = URL.createObjectURL(file);
    previewUrlsRef.current.set(file, url);
    return url;
  }, []);

  useEffect(() => {
    const urls = previewUrlsRef.current;
    const activeFiles = new Set(pendingAttachments);
    for (const [file, url] of urls) {
      if (!activeFiles.has(file)) {
        URL.revokeObjectURL(url);
        urls.delete(file);
      }
    }
  }, [pendingAttachments]);

  useEffect(() => {
    const urls = previewUrlsRef.current;
    return () => {
      for (const url of urls.values()) URL.revokeObjectURL(url);
      urls.clear();
    };
  }, []);

  const {
    supported: speechSupported,
    whisperMode: speechWhisperMode,
    listening: speechListening,
    waiting: speechWaiting,
    error: speechError,
    toggle: toggleSpeech,
    stop: stopSpeech,
    clearError: clearSpeechError,
  } = useSpeechRecognition({
    lang: "th-TH",
    onTranscript: handleInputChange,
  });

  const micDisabled = sessionBlocked || sending;
  const micTitle = !speechSupported
    ? "เบราว์เซอร์ไม่รองรับ Speech-to-text"
    : speechListening
      ? "หยุดฟังเสียง"
      : speechWhisperMode
        ? "พูดเพื่อพิมพ์ (Whisper local)"
        : "พูดเพื่อพิมพ์ (ไทย)";

  const speechStatusLabel = speechListening
    ? speechWaiting
      ? "กำลังรอเสียง…"
      : "กำลังฟัง…"
    : null;

  useEffect(() => {
    if (sending || sessionBlocked) {
      stopSpeech();
    }
  }, [sending, sessionBlocked, stopSpeech]);

  useEffect(() => {
    const previous = previousSessionIdRef.current;
    previousSessionIdRef.current = sessionId;
    if (!previous || previous === sessionId) return;
    setPendingAttachments([]);
    setAttachmentError(null);
    setMachineSearch("");
    stopSpeech();
  }, [sessionId, stopSpeech]);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (selected.length === 0) return;
    const combined = [...pendingAttachments, ...selected];
    const validationError = validateChatAttachmentFiles(combined);
    if (validationError) {
      setAttachmentError(validationError);
      return;
    }
    setAttachmentError(null);
    setPendingAttachments(combined);
  };

  const removePendingAttachment = (index: number) => {
    setPendingAttachments((current) => current.filter((_, i) => i !== index));
    setAttachmentError(null);
  };

  const handleSend = () => {
    if (sessionBlocked || sending) return;
    if (!input.trim() && pendingAttachments.length === 0) return;
    const files = pendingAttachments;
    setPendingAttachments([]);
    setAttachmentError(null);
    onSend(files.length > 0 ? files : undefined);
  };

  const canSend =
    !sessionBlocked &&
    !sending &&
    (input.trim().length > 0 || pendingAttachments.length > 0);

  const handleMicClick = () => {
    if (!speechSupported || micDisabled) return;
    clearSpeechError();
    toggleSpeech(input);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  useLayoutEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    const maxHeight = emptyChat ? 128 : 160;
    element.style.height = "auto";
    const nextHeight = Math.min(Math.max(element.scrollHeight, 44), maxHeight);
    element.style.height = `${nextHeight}px`;
    element.style.overflowY = element.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [emptyChat, input, inputRef]);

  return (
    <div
      className={cn(
        "shrink-0 w-full gemini-theme-transition",
        emptyChat
          ? "px-0 pt-0 pb-0"
          : "px-3 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] sm:px-4 sm:pb-1.5"
      )}
    >
      <div className={cn("mx-auto w-full", emptyChat ? "max-w-[820px]" : "max-w-[47rem]")}>
        {pendingAttachments.length > 0 && (
          <ChatAttachmentChips
            attachments={pendingAttachments.map((file) => ({
              filename: file.name,
              mime_type: file.type || "application/octet-stream",
              previewUrl: getPreviewUrl(file),
            }))}
            onRemove={removePendingAttachment}
          />
        )}
        <div
          className={cn(
            "chat-composer-surface items-center gemini-theme-transition",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/40 dark:border-gemini-dark-border/50",
            emptyChat
              ? "flex min-h-[3.25rem] gap-1 px-3 py-2 sm:gap-1.5 sm:px-4 rounded-[1.75rem] shadow-gemini-input dark:shadow-gemini-input-dark"
              : "chat-composer-card grid min-h-[6.5rem] grid-cols-[auto_minmax(0,1fr)_auto_auto_auto] grid-rows-[minmax(2.75rem,auto)_2.75rem] gap-x-1.5 gap-y-0 rounded-[1.5rem] px-3 py-2 sm:px-4"
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            multiple
            accept={CHAT_ATTACHMENT_ACCEPT}
            onChange={handleFilesSelected}
          />
          <Tooltip content="แนบรูปหรือ PDF (สูงสุด 3 ไฟล์, 10 MB)">
            <button
              type="button"
              className={cn(
                composerIconBtn,
                !emptyChat && "col-start-1 row-start-2"
              )}
              aria-label="แนบไฟล์"
              disabled={sessionBlocked || sending}
              onClick={() => fileInputRef.current?.click()}
            >
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </Tooltip>
          <textarea
            ref={inputRef}
            rows={1}
            value={input}
            maxLength={QUESTION_MAX_LENGTH}
            onChange={(e) => handleInputChange(clampQuestionLength(e.target.value))}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={
              sessionBlocked
                ? "กำลังเตรียมเซสชัน… (พิมพ์ได้แล้ว รอสักครู่แล้วกดส่ง)"
                : emptyChat
                  ? "ถาม Neo"
                  : "พิมพ์ข้อความถึง Neo..."
            }
            className={cn(
              "min-w-0 flex-1 resize-none bg-transparent gemini-theme-transition self-center gemini-scrollbar",
              emptyChat
                ? "min-h-12 max-h-32 py-3 text-base"
                : "col-span-5 col-start-1 row-start-1 min-h-11 max-h-40 w-full px-2 py-2.5 text-base",
              "text-gemini-text dark:text-gemini-dark-text",
              "placeholder:text-gemini-muted dark:placeholder:text-gemini-dark-muted",
              "focus:outline-none"
            )}
            aria-label="ข้อความแชท"
            aria-invalid={Boolean(attachmentError || speechError)}
            aria-describedby={
              [
                attachmentError ? attachmentErrorId : null,
                speechStatusLabel ? speechStatusId : null,
                speechError ? speechErrorId : null,
              ]
                .filter(Boolean)
                .join(" ") || undefined
            }
          />
          <MachineSelector
            machines={machines}
            value={machineId}
            onChange={handleMachineChange}
            isLoading={isFetchingNextPage || machinesLoading}
            hasMore={hasMore}
            onLoadMore={() => loadMore()}
            placeholder="ทุกเครื่อง"
            compact
            serverSearch
            searchQuery={machineSearch}
            onSearchQueryChange={setMachineSearch}
            dropdownPlacement="top"
            className={cn(
              "shrink-0 w-auto min-w-[4.5rem] max-w-[7rem] self-center",
              !emptyChat && "col-start-3 row-start-2"
            )}
            triggerClassName={cn(
              "!h-11 !px-2.5 !gap-1 !w-auto font-sans text-xs !rounded-full",
              "!border-0 !shadow-none !bg-transparent",
              "text-gemini-muted dark:text-gemini-dark-muted",
              "hover:!bg-gemini-hover dark:hover:!bg-gemini-dark-hover hover:!border-0",
              "hover:text-gemini-text dark:hover:text-gemini-dark-text",
              "gemini-focus-ring gemini-theme-transition"
            )}
          />
          <Tooltip content={micTitle}>
            <button
              type="button"
              onClick={handleMicClick}
              disabled={micDisabled || !speechSupported}
              className={cn(
                composerIconBtn,
                !emptyChat && "col-start-4 row-start-2",
                speechListening &&
                  "text-red-500 dark:text-red-400 bg-red-500/10 dark:bg-red-500/15 animate-pulse"
              )}
              aria-label={micTitle}
              aria-pressed={speechListening}
            >
              <Mic className="h-5 w-5" />
            </button>
          </Tooltip>
          {sending && onAbort ? (
            <Tooltip content="หยุดตอบ">
              <button
                type="button"
                onClick={onAbort}
                className={cn(
                  "shrink-0 h-10 w-10 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring bg-gemini-text dark:bg-gemini-dark-text text-white dark:text-gemini-dark-bg hover:opacity-80",
                  !emptyChat && "col-start-5 row-start-2"
                )}
                aria-label="หยุดตอบ"
              >
                <Square className="h-3.5 w-3.5" fill="currentColor" />
              </button>
            </Tooltip>
          ) : canSend ? (
            <Tooltip content="ส่งข้อความ">
              <button
                type="button"
                onClick={handleSend}
                className={cn(
                  "shrink-0 h-10 w-10 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring bg-gemini-text dark:bg-gemini-dark-text text-white dark:text-gemini-dark-bg hover:opacity-80",
                  !emptyChat && "col-start-5 row-start-2"
                )}
                aria-label="ส่งข้อความ"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            </Tooltip>
          ) : null}
        </div>
        {attachmentError && (
          <p
            id={attachmentErrorId}
            role="alert"
            className="mt-1.5 px-2 text-center text-xs text-red-700 dark:text-red-300"
          >
            {attachmentError}
          </p>
        )}
        {speechStatusLabel && (
          <p
            id={speechStatusId}
            role="status"
            aria-live="polite"
            className={cn(
              "mt-1.5 px-2 text-center text-xs",
              speechWaiting
                ? "text-gemini-muted dark:text-gemini-dark-muted"
                : "text-red-700 dark:text-red-300"
            )}
          >
            {speechStatusLabel}
          </p>
        )}
        {speechError && (
          <p
            id={speechErrorId}
            role="alert"
            className="mt-1.5 px-2 text-center text-xs text-red-700 dark:text-red-300"
          >
            {speechError}
          </p>
        )}
        {!emptyChat && (
          <p className="mt-2 px-3 text-center text-xs leading-4 text-gemini-muted dark:text-gemini-dark-muted">
            Neo เป็น AI และอาจให้ข้อมูลคลาดเคลื่อนได้ กรุณาตรวจสอบข้อมูลสำคัญอีกครั้ง
          </p>
        )}
      </div>
    </div>
  );
}

export const MessageInput = memo(MessageInputInner);
