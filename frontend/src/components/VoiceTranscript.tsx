"use client";

import { useVoiceStore } from "@/store/voice";

/**
 * Displays the last transcribed utterance from continuous voice mode.
 * Only renders when continuous listening is active and a transcript exists.
 */
export function VoiceTranscript() {
  const { continuousListening, lastTranscript } = useVoiceStore();

  if (!continuousListening || !lastTranscript) return null;

  return (
    <div
      className="flex items-center gap-2 rounded-2xl border border-violet-500/20 bg-violet-600/10 px-3 py-1.5 text-[11px] text-violet-300"
      title="Last transcribed utterance"
    >
      <span className="shrink-0 opacity-60">Heard:</span>
      <span className="truncate max-w-[240px]">{lastTranscript}</span>
    </div>
  );
}
