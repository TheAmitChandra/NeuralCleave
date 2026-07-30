import { create } from "zustand";

import { startContinuousListening, stopContinuousListening } from "@/lib/api";

interface VoiceState {
  continuousListening: boolean;
  continuousAvailable: boolean;
  _setListening: (v: boolean) => void;
  _setAvailable: (v: boolean) => void;
  startListening: () => Promise<void>;
  stopListening: () => Promise<void>;
}

export const useVoiceStore = create<VoiceState>()((set) => ({
  continuousListening: false,
  continuousAvailable: false,

  _setListening: (v) => set({ continuousListening: v }),
  _setAvailable: (v) => set({ continuousAvailable: v }),

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
}));
