import { describe, it, expect, vi } from "vitest";

const mockStartPtt = vi.fn().mockResolvedValue({ started: true });

vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  getVoiceStatus: vi.fn().mockResolvedValue({ runtime_available: false, continuous_listening: false, wake_detector_active: false, is_handoff_active: false, ptt_available: false, ptt_is_recording: false, stt_available: false, tts_available: false }),
  startPtt: mockStartPtt,
  stopPtt: vi.fn().mockResolvedValue({}),
  startContinuousListening: vi.fn().mockResolvedValue({ started: false }),
  stopContinuousListening: vi.fn().mockResolvedValue({ stopped: false }),
  getContinuousListenStatus: vi.fn().mockResolvedValue({ continuous_available: false, continuous_listening: false }),
}));

describe("voice store startPtt", () => {
  it("sets pttRecording to true when started: true", async () => {
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().startPtt();
    expect(useVoiceStore.getState().pttRecording).toBe(true);
  });
});
