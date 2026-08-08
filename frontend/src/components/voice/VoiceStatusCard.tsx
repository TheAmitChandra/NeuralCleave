"use client";

import { useVoiceStore } from "@/store/voice";

interface StatusRowProps {
  label: string;
  active: boolean;
  activeLabel?: string;
  inactiveLabel?: string;
}

function StatusRow({
  label,
  active,
  activeLabel = "Available",
  inactiveLabel = "Unavailable",
}: StatusRowProps) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-white/[0.04] last:border-0">
      <span className="text-[13px] text-white/50">{label}</span>
      <span
        className={`text-[11px] font-medium px-2.5 py-0.5 rounded-full ${
          active
            ? "text-emerald-400 bg-emerald-500/10 border border-emerald-500/20"
            : "text-white/25 bg-white/[0.04] border border-white/[0.06]"
        }`}
      >
        {active ? activeLabel : inactiveLabel}
      </span>
    </div>
  );
}

export function VoiceStatusCard() {
  const { sttAvailable, ttsAvailable, wakeDetectorActive, pttAvailable } =
    useVoiceStore();

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 pt-4 pb-2">
      <h2 className="text-[11px] font-semibold text-white/40 uppercase tracking-wider mb-1">
        Voice Subsystems
      </h2>
      <StatusRow label="Speech-to-Text (STT)" active={sttAvailable} />
      <StatusRow label="Text-to-Speech (TTS)" active={ttsAvailable} />
      <StatusRow
        label="Wake Word"
        active={wakeDetectorActive}
        activeLabel="Active"
        inactiveLabel="Inactive"
      />
      <StatusRow label="Push-to-Talk (PTT)" active={pttAvailable} />
    </div>
  );
}
