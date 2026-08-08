"use client";

import { useEffect } from "react";
import { Mic } from "lucide-react";

import { useVoiceStore } from "@/store/voice";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";
import { WakeWordCard } from "@/components/voice/WakeWordCard";
import { VoiceTranscriptCard } from "@/components/voice/VoiceTranscriptCard";
import { PushToTalkButton } from "@/components/PushToTalkButton";
import { VoiceButton } from "@/components/VoiceButton";

export default function VoicePage() {
  const {
    pollStatus,
    continuousAvailable,
    continuousListening,
    startListening,
    stopListening,
  } = useVoiceStore();

  useEffect(() => {
    void pollStatus();
    const id = setInterval(() => void pollStatus(), 5_000);
    return () => clearInterval(id);
  }, [pollStatus]);

  const toggleContinuous = () =>
    void (continuousListening ? stopListening() : startListening());

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600/20">
          <Mic className="h-5 w-5 text-violet-400" />
        </div>
        <div>
          <h1 className="text-[18px] font-semibold text-white">Voice</h1>
          <p className="text-[13px] text-white/35">Wake word · STT · TTS · Push-to-talk</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <PushToTalkButton />
          <VoiceButton />
        </div>
      </div>

      {/* Continuous listening toggle (only when configured) */}
      {continuousAvailable && (
        <div className="flex items-center justify-between rounded-2xl border border-white/[0.06] bg-white/[0.02] px-4 py-3">
          <div>
            <p className="text-[13px] font-medium text-white/70">Continuous Listening</p>
            <p className="text-[11px] text-white/30 mt-0.5">
              Always-on voice detection — speak at any time
            </p>
          </div>
          <button
            onClick={toggleContinuous}
            aria-label={
              continuousListening
                ? "Stop continuous listening"
                : "Start continuous listening"
            }
            className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
              continuousListening ? "bg-violet-600" : "bg-white/[0.08]"
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                continuousListening ? "translate-x-4" : "translate-x-0.5"
              }`}
            />
          </button>
        </div>
      )}

      {/* Status grid */}
      <VoiceStatusCard />

      {/* Wake word */}
      <WakeWordCard />

      {/* Last transcript */}
      <VoiceTranscriptCard />
    </div>
  );
}
