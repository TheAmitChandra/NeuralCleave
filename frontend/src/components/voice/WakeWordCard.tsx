"use client";

import { Radio } from "lucide-react";
import { useVoiceStore } from "@/store/voice";

export function WakeWordCard() {
  const { wakeDetectorActive, handoffActive } = useVoiceStore();

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.02] p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-[11px] font-semibold text-white/40 uppercase tracking-wider">
          Wake Word
        </h2>
        {wakeDetectorActive && (
          <span className="flex items-center gap-1.5 text-[11px] font-medium text-amber-400">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-400" />
            </span>
            Listening
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        <div
          className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${
            wakeDetectorActive ? "bg-amber-500/15" : "bg-white/[0.04]"
          }`}
        >
          <Radio
            className={`h-6 w-6 ${wakeDetectorActive ? "text-amber-400" : "text-white/20"}`}
          />
        </div>
        <div>
          <p
            className={`text-[14px] font-medium ${
              wakeDetectorActive ? "text-amber-300" : "text-white/30"
            }`}
          >
            {wakeDetectorActive ? "Detector active" : "Detector inactive"}
          </p>
          <p className="text-[12px] text-white/25 mt-0.5">
            {handoffActive
              ? "Voice handoff in progress"
              : wakeDetectorActive
              ? "Say the wake word to start a session"
              : "Enable in Settings → Voice"}
          </p>
        </div>
      </div>
    </div>
  );
}
