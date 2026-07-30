"use client";

import { useState, useCallback } from "react";
import { Mic, Square } from "lucide-react";
import { voiceRecorder } from "@/lib/voice-ws";

interface Props {
  disabled?: boolean;
  className?: string;
}

export function VoiceButton({ disabled = false, className = "" }: Props) {
  const [recording, setRecording] = useState(false);

  const toggle = useCallback(async () => {
    if (recording) {
      voiceRecorder.stop();
      setRecording(false);
    } else {
      try {
        await voiceRecorder.start();
        setRecording(true);
      } catch {
        // Mic permission denied or MediaRecorder unavailable — stay silent;
        // the browser already shows its own permission-denied prompt.
      }
    }
  }, [recording]);

  return (
    <button
      onClick={toggle}
      disabled={disabled}
      aria-label={recording ? "Stop recording" : "Start voice input"}
      title={recording ? "Stop recording" : "Voice input"}
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors
        ${recording
          ? "bg-rose-600 hover:bg-rose-500"
          : "bg-white/[0.06] hover:bg-white/[0.1]"
        }
        ${recording ? "animate-pulse" : ""}
        disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {recording ? (
        <Square className="h-4 w-4 text-white" fill="currentColor" />
      ) : (
        <Mic className="h-4 w-4 text-white/70" />
      )}
    </button>
  );
}
