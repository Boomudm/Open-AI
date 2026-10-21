"use client";

import { api } from "@/lib/api";
import {
  joinPrefix,
  mergeRecognitionResults,
  spokenText,
} from "@/lib/speechTranscript";
import { useCallback, useEffect, useRef, useState } from "react";

export type UseSpeechRecognitionOptions = {
  lang?: string;
  onTranscript: (text: string) => void;
};

const MAX_RESTARTS = 8;
const WHISPER_MAX_MS = 30_000;
const INITIAL_RESTART_DELAY_MS = 100;
const MAX_RESTART_DELAY_MS = 2000;
const WAITING_TIMEOUT_MS = 3000;

const FATAL_ERRORS = new Set<SpeechRecognitionErrorEvent["error"]>([
  "network",
  "not-allowed",
  "service-not-allowed",
  "audio-capture",
  "language-not-supported",
]);

function getRecognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  if (!window.isSecureContext) return null;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

function errorMessage(code: SpeechRecognitionErrorEvent["error"]): string {
  switch (code) {
    case "not-allowed":
    case "service-not-allowed":
      return "ไม่ได้รับอนุญาตให้ใช้ไมโครโฟน — ตรวจสอบการตั้งค่าเบราว์เซอร์";
    case "no-speech":
      return "ไม่ได้ยินเสียงพูด — ลองพูดอีกครั้ง";
    case "audio-capture":
      return "ไม่พบไมโครโฟน";
    case "network":
      return "Speech-to-text ต้องการอินเทอร์เน็ต";
    case "language-not-supported":
      return "ภาษานี้ไม่รองรับในเบราว์เซอร์";
    default:
      return "ไม่สามารถใช้งานเสียงพูดได้";
  }
}

async function preflightMic(): Promise<string | null> {
  if (!navigator.mediaDevices?.getUserMedia) {
    return "เบราว์เซอร์ไม่รองรับไมโครโฟน";
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    return null;
  } catch {
    return "ไม่ได้รับอนุญาตให้ใช้ไมโครโฟน — ตรวจสอบการตั้งค่าเบราว์เซอร์";
  }
}

function mapResults(event: SpeechRecognitionEvent) {
  const results: { transcript: string; isFinal: boolean }[] = [];
  for (let i = 0; i < event.results.length; i += 1) {
    results.push({
      transcript: event.results[i][0]?.transcript ?? "",
      isFinal: event.results[i].isFinal,
    });
  }
  return results;
}

export function useSpeechRecognition({
  lang = "th-TH",
  onTranscript,
}: UseSpeechRecognitionOptions) {
  const [supported, setSupported] = useState(false);
  const [whisperMode, setWhisperMode] = useState(false);
  const [listening, setListening] = useState(false);
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const whisperActiveRef = useRef(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const whisperTimeoutRef = useRef<number | null>(null);
  const prefixRef = useRef("");
  const committedRef = useRef("");
  const onTranscriptRef = useRef(onTranscript);
  const activeRef = useRef(false);
  const restartCountRef = useRef(0);
  const restartDelayRef = useRef(INITIAL_RESTART_DELAY_MS);
  const restartTimeoutRef = useRef<number | null>(null);
  const lastResultAtRef = useRef(0);

  const clearRestartTimeout = useCallback(() => {
    if (restartTimeoutRef.current !== null) {
      window.clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
  }, []);

  const emitTranscript = useCallback(() => {
    const spoken = spokenText(committedRef.current, "");
    onTranscriptRef.current(joinPrefix(prefixRef.current, spoken));
  }, []);

  const emitTranscriptWithInterim = useCallback((interim: string) => {
    const spoken = spokenText(committedRef.current, interim);
    onTranscriptRef.current(joinPrefix(prefixRef.current, spoken));
  }, []);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    void api
      .getChatCapabilities()
      .then((caps) => {
        const whisper = Boolean(caps.speech?.whisper);
        setWhisperMode(whisper);
        setSupported(whisper || getRecognitionCtor() !== null);
      })
      .catch(() => {
        if (!window.isSecureContext) {
          setSupported(false);
          return;
        }
        setSupported(getRecognitionCtor() !== null);
      });
    return () => {
      activeRef.current = false;
      whisperActiveRef.current = false;
      clearRestartTimeout();
      recognitionRef.current?.abort();
      recognitionRef.current = null;
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      if (whisperTimeoutRef.current !== null) {
        window.clearTimeout(whisperTimeoutRef.current);
      }
    };
  }, [clearRestartTimeout]);

  useEffect(() => {
    if (!listening) {
      setWaiting(false);
      return;
    }

    const interval = window.setInterval(() => {
      if (Date.now() - lastResultAtRef.current >= WAITING_TIMEOUT_MS) {
        setWaiting(true);
      }
    }, 500);

    return () => window.clearInterval(interval);
  }, [listening]);

  const stop = useCallback(() => {
    activeRef.current = false;
    whisperActiveRef.current = false;
    clearRestartTimeout();
    recognitionRef.current?.stop();
    recognitionRef.current = null;
    if (whisperTimeoutRef.current !== null) {
      window.clearTimeout(whisperTimeoutRef.current);
      whisperTimeoutRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    } else {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setListening(false);
      setWaiting(false);
    }
  }, [clearRestartTimeout]);

  const finishWhisperRecording = useCallback(async () => {
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    chunksRef.current = [];
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    mediaRecorderRef.current = null;
    setListening(false);
    setWaiting(true);
    try {
      const result = await api.transcribeAudio(blob);
      const spoken = spokenText(result.text ?? "", "");
      onTranscriptRef.current(joinPrefix(prefixRef.current, spoken));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Whisper transcribe failed");
    } finally {
      setWaiting(false);
      whisperActiveRef.current = false;
    }
  }, []);

  const startWhisper = useCallback(
    async (inputPrefix: string) => {
      const micError = await preflightMic();
      if (micError) {
        setError(micError);
        return;
      }
      prefixRef.current = inputPrefix;
      committedRef.current = "";
      setError(null);
      setWaiting(false);
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        const recorder = new MediaRecorder(stream);
        chunksRef.current = [];
        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data);
        };
        recorder.onstop = () => {
          void finishWhisperRecording();
        };
        mediaRecorderRef.current = recorder;
        whisperActiveRef.current = true;
        setListening(true);
        recorder.start();
        whisperTimeoutRef.current = window.setTimeout(() => {
          if (whisperActiveRef.current) stop();
        }, WHISPER_MAX_MS);
      } catch {
        setError("ไม่สามารถเริ่มบันทึกเสียง Whisper ได้");
        whisperActiveRef.current = false;
        setListening(false);
      }
    },
    [finishWhisperRecording, stop]
  );

  const handleFatalError = useCallback(
    (message: string) => {
      activeRef.current = false;
      clearRestartTimeout();
      recognitionRef.current?.abort();
      recognitionRef.current = null;
      setError(message);
      setListening(false);
      setWaiting(false);
    },
    [clearRestartTimeout]
  );

  const scheduleRestart = useCallback(() => {
    if (!activeRef.current) {
      setListening(false);
      setWaiting(false);
      return;
    }

    restartCountRef.current += 1;
    if (restartCountRef.current > MAX_RESTARTS) {
      handleFatalError("ไม่สามารถฟังเสียงต่อได้ — ลองกดไมค์อีกครั้ง");
      return;
    }

    const delay = restartDelayRef.current;
    restartDelayRef.current = Math.min(
      Math.round(restartDelayRef.current * 1.5),
      MAX_RESTART_DELAY_MS
    );

    clearRestartTimeout();
    restartTimeoutRef.current = window.setTimeout(() => {
      restartTimeoutRef.current = null;
      if (activeRef.current) {
        launchRecognitionRef.current();
      }
    }, delay);
  }, [clearRestartTimeout, handleFatalError]);

  const launchRecognitionRef = useRef<() => void>(() => {});

  const launchRecognition = useCallback(() => {
    const Ctor = getRecognitionCtor();
    if (!Ctor || !activeRef.current) return;

    recognitionRef.current?.abort();

    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      lastResultAtRef.current = Date.now();
      setWaiting(false);

      const merged = mergeRecognitionResults(
        committedRef.current,
        mapResults(event),
        event.resultIndex
      );
      committedRef.current = merged.committed;

      let hadFinal = false;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        if (event.results[i]?.isFinal) hadFinal = true;
      }

      if (hadFinal) {
        restartCountRef.current = 0;
        restartDelayRef.current = INITIAL_RESTART_DELAY_MS;
      }

      emitTranscriptWithInterim(merged.interim);
    };

    recognition.onerror = (event) => {
      if (event.error === "aborted") return;
      if (event.error === "no-speech") return;

      if (FATAL_ERRORS.has(event.error)) {
        handleFatalError(errorMessage(event.error));
        return;
      }

      setError(errorMessage(event.error));
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      if (!activeRef.current) {
        setListening(false);
        setWaiting(false);
        return;
      }
      scheduleRestart();
    };

    recognitionRef.current = recognition;
    setListening(true);

    try {
      recognition.start();
    } catch {
      handleFatalError("ไม่สามารถเริ่มฟังเสียงได้ — ลองอีกครั้ง");
    }
  }, [emitTranscriptWithInterim, handleFatalError, lang, scheduleRestart]);

  useEffect(() => {
    launchRecognitionRef.current = launchRecognition;
  }, [launchRecognition]);

  const start = useCallback(
    async (inputPrefix: string) => {
      if (typeof window !== "undefined" && !window.isSecureContext) {
        setError("Speech-to-text ต้องใช้ HTTPS หรือ localhost");
        return;
      }

      const Ctor = getRecognitionCtor();
      if (!Ctor) {
        setError("เบราว์เซอร์นี้ไม่รองรับ Speech-to-text — ใช้ Chrome, Edge หรือ Safari");
        return;
      }

      const micError = await preflightMic();
      if (micError) {
        setError(micError);
        return;
      }

      activeRef.current = true;
      prefixRef.current = inputPrefix;
      committedRef.current = "";
      restartCountRef.current = 0;
      restartDelayRef.current = INITIAL_RESTART_DELAY_MS;
      lastResultAtRef.current = Date.now();
      setError(null);
      setWaiting(false);
      clearRestartTimeout();
      recognitionRef.current?.abort();
      launchRecognition();
    },
    [clearRestartTimeout, launchRecognition]
  );

  const toggle = useCallback(
    (inputPrefix: string) => {
      if (listening || activeRef.current || whisperActiveRef.current) {
        if (whisperMode) {
          stop();
        } else {
          emitTranscript();
          stop();
        }
        return;
      }
      if (whisperMode) {
        void startWhisper(inputPrefix);
        return;
      }
      void start(inputPrefix);
    },
    [emitTranscript, listening, start, startWhisper, stop, whisperMode]
  );

  return {
    supported,
    whisperMode,
    listening,
    waiting,
    error,
    toggle,
    stop,
    clearError: () => setError(null),
  };
}
