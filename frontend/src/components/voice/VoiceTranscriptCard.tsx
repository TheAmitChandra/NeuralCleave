"use client";

import { useVoiceStore } from "@/store/voice";

export function VoiceTranscriptCard() {
  const lastTranscript = useVoiceStore((s) => s.lastTranscript);

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
      <h2 className="text-[11px] font-semibold text-white/40 uppercase tracking-wider mb-3">
        Last Transcript
      </h2>
      {lastTranscript ? (
        <p className="text-[14px] text-white/70 leading-relaxed">{lastTranscript}</p>
      ) : (
        <p className="text-[13px] text-white/20 italic">
          No transcript yet — speak after triggering voice input.
        </p>
      )}
    </div>
  );
}
