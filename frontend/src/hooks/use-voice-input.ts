"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Voice input states.
 */
export type VoiceStatus = "idle" | "listening" | "processing" | "error";

/**
 * Hook return type.
 */
export interface UseVoiceInputReturn {
  /** Current status */
  status: VoiceStatus;
  /** Whether voice input is available in this browser */
  isSupported: boolean;
  /** Whether currently listening */
  isListening: boolean;
  /** Interim transcript (live while speaking) */
  interimTranscript: string;
  /** Final transcript (after speech ends) */
  transcript: string;
  /** Start listening */
  start: () => void;
  /** Stop listening */
  stop: () => void;
  /** Toggle listening */
  toggle: () => void;
  /** Reset transcript */
  reset: () => void;
  /** Last error message */
  error: string | null;
}

/**
 * Web Speech API interface (not yet in lib.dom.d.ts for all browsers).
 */
interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

type SpeechRecognitionCtor = new () => SpeechRecognition & EventTarget;

interface SpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

function getSpeechRecognitionClass(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;

  const w = window as any;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * React hook for browser-native voice input via Web Speech API.
 *
 * @param lang - BCP-47 language tag (default: navigator.language or "en-US")
 * @param onResult - callback fired with final transcript
 */
export function useVoiceInput(
  lang?: string,
  onResult?: (transcript: string) => void,
): UseVoiceInputReturn {
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [isSupported, setIsSupported] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const isSupportedRef = useRef(false);

  // Check support once
  useEffect(() => {
    const supported = getSpeechRecognitionClass() !== null;
    isSupportedRef.current = supported;
    setIsSupported(supported);
  }, []);

  const start = useCallback(() => {
    const Ctor = getSpeechRecognitionClass();
    if (!Ctor) {
      setError("Speech recognition is not supported in this browser.");
      setStatus("error");
      return;
    }

    // Stop existing
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
    }

    const recognition = new Ctor();
    recognition.lang = lang ?? navigator.language ?? "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setStatus("listening");
      setError(null);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      let final_ = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result?.[0]) {
          if (result.isFinal) {
            final_ += result[0].transcript;
          } else {
            interim += result[0].transcript;
          }
        }
      }
      setInterimTranscript(interim);
      if (final_) {
        setTranscript((prev) => {
          const next = prev ? `${prev} ${final_}` : final_;
          onResult?.(next);
          return next;
        });
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // "aborted" is normal when user stops manually
      if (event.error === "aborted") return;
      setError(event.error);
      setStatus("error");
    };

    recognition.onend = () => {
      setStatus("idle");
      setInterimTranscript("");
    };

    recognitionRef.current = recognition;

    try {
      recognition.start();
    } catch (err) {
      setError(String(err));
      setStatus("error");
    }
  }, [lang, onResult]);

  const stop = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }
    setStatus("idle");
    setInterimTranscript("");
  }, []);

  const toggle = useCallback(() => {
    if (status === "listening") {
      stop();
    } else {
      start();
    }
  }, [status, start, stop]);

  const reset = useCallback(() => {
    stop();
    setTranscript("");
    setInterimTranscript("");
    setError(null);
  }, [stop]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.abort();
        } catch {}
      }
    };
  }, []);

  return {
    status,
    isSupported,
    isListening: status === "listening",
    interimTranscript,
    transcript,
    start,
    stop,
    toggle,
    reset,
    error,
  };
}
