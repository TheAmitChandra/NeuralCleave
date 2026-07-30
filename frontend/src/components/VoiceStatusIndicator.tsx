"use client";

import { useEffect } from "react";
import { Mic, MicOff } from "lucide-react";

import { useVoiceStore } from "@/store/voice";

const POLL_INTERVAL_MS = 5_000;

/**
 * Pill that shows continuous-listening state and lets the user toggle it.
 * Polls the gateway every 5 s so the UI stays in sync with server-side
 * changes (e.g. voice started via CLI --voice flag) without a page reload.
 */
export function VoiceStatusIndicator() {
  const {
    continuousListening,
    continuousAvailable,
    startListening,
    stopListening,
    pollStatus,
  } = useVoiceStore();

  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [pollStatus]);

  if (!continuousAvailable) return null;

  const toggle = () => (continuousListening ? stopListening() : startListening());

  return (
    <button
      type="button"
      onClick={toggle}
      title={continuousListening ? "Stop continuous listening" : "Start continuous listening"}
      className={[
        "flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium transition-all select-none",
        continuousListening
          ? "bg-violet-600/20 text-violet-300 border border-violet-500/30"
          : "bg-white/[0.04] text-white/30 border border-white/[0.06] hover:text-white/50",
      ].join(" ")}
    >
      {continuousListening ? (
        <>
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-violet-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-violet-400" />
          </span>
          <Mic className="h-3 w-3" />
          Listening
        </>
      ) : (
        <>
          <MicOff className="h-3 w-3" />
          Listen
        </>
      )}
    </button>
  );
}
