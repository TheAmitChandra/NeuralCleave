import { create } from "zustand";

import {
  getContinuousListenStatus,
  startContinuousListening,
  stopContinuousListening,
  getVoiceStatus,
  startPtt,
  stopPtt,
} from "@/lib/api";

interface VoiceState {
  continuousListening: boolean;
  continuousAvailable: boolean;
  lastTranscript: string;
  vadBackend: string;
  pttAvailable: boolean;
  pttRecording: boolean;
  wakeDetectorActive: boolean;
  handoffActive: boolean;
  _setListening: (v: boolean) => void;
  _setAvailable: (v: boolean) => void;
  _setLastTranscript: (t: string) => void;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
  startPtt: () => Promise<void>;
  stopPtt: () => Promise<void>;
  /** Poll GET /voice/status and sync all voice subsystem state into the store. */
  pollStatus: () => Promise<void>;
}

export const useVoiceStore = create<VoiceState>()((set) => ({
  continuousListening: false,
  continuousAvailable: false,
  lastTranscript: "",
  vadBackend: "energy",
  pttAvailable: false,
  pttRecording: false,
  wakeDetectorActive: false,
  handoffActive: false,

  _setListening: (v) => set({ continuousListening: v }),
  _setAvailable: (v) => set({ continuousAvailable: v }),
  _setLastTranscript: (t) => set({ lastTranscript: t }),

  startListening: async () => {
    try {
      const data = await startContinuousListening();
      if (data.started) set({ continuousListening: true, continuousAvailable: true });
    } catch {
      // gateway unreachable — leave state unchanged
    }
  },

  stopListening: async () => {
    try {
      const data = await stopContinuousListening();
      if (data.stopped) set({ continuousListening: false });
    } catch {
      // gateway unreachable — leave state unchanged
    }
  },

  startPtt: async () => {
    try {
      const data = await startPtt();
      if (data.started) set({ pttRecording: true });
    } catch {
      // gateway unreachable — leave state unchanged
    }
  },

  stopPtt: async () => {
    try {
      await stopPtt();
      set({ pttRecording: false });
    } catch {
      set({ pttRecording: false });
    }
  },

  pollStatus: async () => {
    try {
      const data = await getVoiceStatus();
      set({
        continuousAvailable: data.runtime_available,
        continuousListening: data.continuous_listening,
        pttAvailable: data.ptt_available,
        pttRecording: data.ptt_is_recording,
        wakeDetectorActive: data.wake_detector_active,
        handoffActive: data.is_handoff_active,
      });
    } catch {
      // gateway unreachable — leave state unchanged
    }
  },
}));
