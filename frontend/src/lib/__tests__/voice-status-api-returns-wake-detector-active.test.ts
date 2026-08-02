import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, getVoiceStatus } from "@/lib/api";

beforeEach(() => {
  vi.spyOn(apiClient, "get").mockResolvedValue({
    data: { runtime_available: true, continuous_listening: false, wake_detector_active: true, is_handoff_active: false, ptt_available: false, ptt_is_recording: false, stt_available: true, tts_available: true },
  } as never);
});

afterEach(() => { vi.restoreAllMocks(); });

describe("getVoiceStatus", () => {
  it("returns wake_detector_active field", async () => {
    const result = await getVoiceStatus();
    expect(result.wake_detector_active).toBe(true);
  });
});
