"use client";

import { useState, useCallback } from "react";
import { Mic, Square, MicOff } from "lucide-react";
import { voiceRecorder } from "@/lib/voice-ws";

interface Props {
  disabled?: boolean;
  className?: string;
}

export function VoiceButton({ disabled = false, className = "" }: Props) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toggle = useCallback(async () => {
    if (recording) {
      voiceRecorder.stop();
      setRecording(false);
      setError(null);
    } else {
      setError(null);
      try {
        await voiceRecorder.start();
        setRecording(true);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        const isPermission = msg.toLowerCase().includes("permission") || msg.toLowerCase().includes("denied") || msg.toLowerCase().includes("notallowed");
        setError(isPermission ? "Microphone access denied. Allow mic in OS settings." : "Microphone unavailable.");
        setTimeout(() => setError(null), 4000);
      }
    }
  }, [recording]);

  return (
    <div className="relative flex flex-col items-center">
      {error && (
        <div className="absolute bottom-11 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-lg bg-rose-600 px-3 py-1.5 text-xs text-white shadow-lg z-50">
          {error}
        </div>
      )}
      <button
        onClick={toggle}
        disabled={disabled}
        aria-label={recording ? "Stop recording" : "Start voice input"}
        title={recording ? "Stop recording" : "Voice input"}
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors
          ${error
            ? "bg-rose-700 hover:bg-rose-600"
            : recording
            ? "bg-rose-600 hover:bg-rose-500"
            : "bg-white/[0.06] hover:bg-white/[0.1]"
          }
          ${recording ? "animate-pulse" : ""}
          disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
      >
        {error ? (
          <MicOff className="h-4 w-4 text-white" />
        ) : recording ? (
          <Square className="h-4 w-4 text-white" fill="currentColor" />
        ) : (
          <Mic className="h-4 w-4 text-white/70" />
        )}
      </button>
    </div>
  );
}
