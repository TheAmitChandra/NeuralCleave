"use client";

import { useEffect } from "react";
import { Mic, MicOff, Radio } from "lucide-react";

import { useVoiceStore } from "@/store/voice";

const POLL_INTERVAL_MS = 5_000;

/**
 * Composite voice-status pill rendered in the chat toolbar.
 *
 * Shows three independent indicators:
 * - Wake badge  — amber "Wake" pill when the wake-word detector is active
 * - PTT badge   — green "Recording" pulse while a PTT session is live
 * - Listen pill — violet toggle button for continuous-listen mode
 *
 * Polls GET /voice/status every 5 s so the UI stays in sync with server-
 * side changes without a reload. Renders nothing if neither continuous-
 * listen nor wake-word is configured on the gateway.
 */
export function VoiceStatusIndicator() {
  const {
    continuousListening,
    continuousAvailable,
    wakeDetectorActive,
    pttRecording,
    startListening,
    stopListening,
    pollStatus,
  } = useVoiceStore();

  useEffect(() => {
    void pollStatus();
    const id = setInterval(() => void pollStatus(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [pollStatus]);

  if (!continuousAvailable && !wakeDetectorActive) return null;

  const toggle = () => void (continuousListening ? stopListening() : startListening());

  return (
    <div className="flex items-center gap-1.5">
      {wakeDetectorActive && (
        <span
          title="Wake-word detector is active"
          className="flex items-center gap-1 rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[10px] font-medium text-amber-400"
        >
          <Radio className="h-2.5 w-2.5" />
          Wake
        </span>
      )}

      {pttRecording && (
        <span className="flex animate-pulse items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-1 text-[10px] font-medium text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Recording
        </span>
      )}

      {continuousAvailable && (
        <button
          type="button"
          onClick={toggle}
          title={continuousListening ? "Stop continuous listening" : "Start continuous listening"}
          className={[
            "flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium transition-all select-none",
            continuousListening
              ? "border border-violet-500/30 bg-violet-600/20 text-violet-300"
              : "border border-white/[0.06] bg-white/[0.04] text-white/30 hover:text-white/50",
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
      )}
    </div>
  );
}
