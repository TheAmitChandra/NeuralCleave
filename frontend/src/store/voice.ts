import { create } from "zustand";

import {
  getContinuousListenStatus,
  startContinuousListening,
  stopContinuousListening,
} from "@/lib/api";

interface VoiceState {
  continuousListening: boolean;
  continuousAvailable: boolean;
  lastTranscript: string;
  vadBackend: string;
  _setListening: (v: boolean) => void;
  _setAvailable: (v: boolean) => void;
  _setLastTranscript: (t: string) => void;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
  /** Poll the gateway for live voice status and sync into the store. */
  pollStatus: () => Promise<void>;
}

export const useVoiceStore = create<VoiceState>()((set) => ({
  continuousListening: false,
  continuousAvailable: false,
  lastTranscript: "",
  vadBackend: "energy",

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

  pollStatus: async () => {
    try {
      const data = await getContinuousListenStatus();
      set({
        continuousAvailable: data.continuous_available,
        continuousListening: data.continuous_listening,
      });
    } catch {
      // gateway unreachable — leave state unchanged
    }
  },
}));
