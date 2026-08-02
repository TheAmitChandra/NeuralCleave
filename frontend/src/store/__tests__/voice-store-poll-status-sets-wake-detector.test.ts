import { describe, it, expect, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  getVoiceStatus: vi.fn().mockResolvedValue({
    runtime_available: true,
    continuous_listening: false,
    wake_detector_active: true,
    is_handoff_active: false,
    ptt_available: false,
    ptt_is_recording: false,
    stt_available: true,
    tts_available: true,
  }),
  startPtt: vi.fn().mockResolvedValue({ started: false }),
  stopPtt: vi.fn().mockResolvedValue({}),
  startContinuousListening: vi.fn().mockResolvedValue({ started: false }),
  stopContinuousListening: vi.fn().mockResolvedValue({ stopped: false }),
  getContinuousListenStatus: vi.fn().mockResolvedValue({ continuous_available: false, continuous_listening: false }),
}));

describe("voice store pollStatus", () => {
  it("syncs wakeDetectorActive from /voice/status", async () => {
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().wakeDetectorActive).toBe(true);
  });
});
