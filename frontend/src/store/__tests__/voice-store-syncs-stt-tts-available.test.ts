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

const baseStatus = {
  runtime_available: true,
  continuous_available: false,
  continuous_listening: false,
  wake_detector_active: false,
  is_handoff_active: false,
  ptt_available: false,
  ptt_is_recording: false,
};

describe("voice store pollStatus — sttAvailable / ttsAvailable", () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it("sets sttAvailable=true when gateway reports stt_available=true", async () => {
    mockGetVoiceStatus.mockResolvedValue({ ...baseStatus, stt_available: true, tts_available: false });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().sttAvailable).toBe(true);
  });

  it("sets sttAvailable=false when gateway reports stt_available=false", async () => {
    mockGetVoiceStatus.mockResolvedValue({ ...baseStatus, stt_available: false, tts_available: false });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().sttAvailable).toBe(false);
  });

  it("sets ttsAvailable=true when gateway reports tts_available=true", async () => {
    mockGetVoiceStatus.mockResolvedValue({ ...baseStatus, stt_available: false, tts_available: true });
    const { useVoiceStore } = await import("@/store/voice");
    await useVoiceStore.getState().pollStatus();
    expect(useVoiceStore.getState().ttsAvailable).toBe(true);
  });
});
