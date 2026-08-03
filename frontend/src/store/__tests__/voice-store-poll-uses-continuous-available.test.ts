import { describe, it, expect, vi, beforeEach } from "vitest";

const mockGetVoiceStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  getVoiceStatus: mockGetVoiceStatus,
  startPtt: vi.fn().mockResolvedValue({ started: false }),
  stopPtt: vi.fn().mockResolvedValue({}),
  startContinuousListening: vi.fn().mockResolvedValue({ started: false }),
  stopContinuousListening: vi.fn().mockResolvedValue({ stopped: false }),
  getContinuousListenStatus: vi.fn().mockResolvedValue({ continuous_available: false, continuous_listening: false }),
}));

describe("voice store pollStatus — continuous_available mapping", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("sets continuousAvailable=true when continuous_available is true", async () => {
    mockGetVoiceStatus.mockResolvedValue({
      runtime_available: true,
      continuous_available: true,
      continuous_listening: false,
      wake_detector_active: false,
      is_handoff_active: false,
      ptt_available: false,
      ptt_is_recording: false,
      stt_available: false,
      tts_available: false,
    });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().continuousAvailable).toBe(true);
  });

  it("sets continuousAvailable=false when continuous_available is false even if runtime is up", async () => {
    mockGetVoiceStatus.mockResolvedValue({
      runtime_available: true,
      continuous_available: false,
      continuous_listening: false,
      wake_detector_active: false,
      is_handoff_active: false,
      ptt_available: false,
      ptt_is_recording: false,
      stt_available: false,
      tts_available: false,
    });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().continuousAvailable).toBe(false);
  });

  it("falls back to runtime_available when continuous_available is absent", async () => {
    mockGetVoiceStatus.mockResolvedValue({
      runtime_available: true,
      // continuous_available intentionally absent (old gateway build)
      continuous_listening: false,
      wake_detector_active: false,
      is_handoff_active: false,
      ptt_available: false,
      ptt_is_recording: false,
      stt_available: false,
      tts_available: false,
    });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().continuousAvailable).toBe(true);
  });
});
