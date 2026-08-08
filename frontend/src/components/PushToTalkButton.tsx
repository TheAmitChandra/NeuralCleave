"use client";

import { PhoneCall } from "lucide-react";
import { useVoiceStore } from "@/store/voice";

interface Props {
  className?: string;
}

export function PushToTalkButton({ className = "" }: Props) {
  const { pttAvailable, pttRecording, startPtt, stopPtt } = useVoiceStore();

  return (
    <button
      onMouseDown={pttAvailable ? () => void startPtt() : undefined}
      onMouseUp={pttAvailable ? () => void stopPtt() : undefined}
      onTouchStart={pttAvailable ? (e) => { e.preventDefault(); void startPtt(); } : undefined}
      onTouchEnd={pttAvailable ? () => void stopPtt() : undefined}
      disabled={!pttAvailable}
      aria-label={pttRecording ? "Release to send" : "Hold to talk"}
      title={
        pttAvailable
          ? "Push-to-talk — hold while speaking"
          : "PTT not configured — enable voice in Settings"
      }
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors select-none
        ${pttRecording
          ? "bg-emerald-600 hover:bg-emerald-500 animate-pulse"
          : pttAvailable
          ? "bg-white/[0.06] hover:bg-white/[0.1]"
          : "bg-white/[0.03] opacity-40 cursor-not-allowed"
        } ${className}`}
    >
      <PhoneCall className={`h-4 w-4 ${pttRecording ? "text-white" : "text-white/70"}`} />
    </button>
  );
}
