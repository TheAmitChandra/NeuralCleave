"use client";

import { useEffect } from "react";
import { Mic, MicOff } from "lucide-react";

import { getContinuousListenStatus } from "@/lib/api";
import { useVoiceStore } from "@/store/voice";

/**
 * Pill that shows continuous-listening state and lets the user toggle it.
 * Polls the gateway on mount so the UI reflects any server-side change
 * (e.g. voice started via CLI) without a page reload.
 */
export function VoiceStatusIndicator() {
  const { continuousListening, continuousAvailable, startListening, stopListening, _setListening, _setAvailable } =
    useVoiceStore();

  useEffect(() => {
    let cancelled = false;
    getContinuousListenStatus()
      .then((d) => {
        if (cancelled) return;
        _setAvailable(d.continuous_available);
        _setListening(d.continuous_listening);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [_setAvailable, _setListening]);

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
