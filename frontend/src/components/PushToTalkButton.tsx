"use client";

import { PhoneCall } from "lucide-react";
import { useVoiceStore } from "@/store/voice";

interface Props {
  className?: string;
}

/**
 * Press-and-hold button that starts a server-side PTT recording on mousedown/
 * touchstart and stops it (triggering transcription + TTS reply) on release.
 * Renders nothing when PTT is not configured on the gateway.
 */
export function PushToTalkButton({ className = "" }: Props) {
  const { pttAvailable, pttRecording, startPtt, stopPtt } = useVoiceStore();

  if (!pttAvailable) return null;

  return (
    <button
      onMouseDown={() => void startPtt()}
      onMouseUp={() => void stopPtt()}
      onTouchStart={(e) => { e.preventDefault(); void startPtt(); }}
      onTouchEnd={() => void stopPtt()}
      aria-label={pttRecording ? "Release to send" : "Hold to talk"}
      title="Push-to-talk — hold while speaking"
      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors select-none
        ${pttRecording
          ? "bg-emerald-600 hover:bg-emerald-500 animate-pulse"
          : "bg-white/[0.06] hover:bg-white/[0.1]"
        } ${className}`}
    >
      <PhoneCall className={`h-4 w-4 ${pttRecording ? "text-white" : "text-white/70"}`} />
    </button>
  );
}
