import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, getVoiceStatus } from "@/lib/api";

beforeEach(() => {
  vi.spyOn(apiClient, "get").mockResolvedValue({
    data: { runtime_available: true, continuous_listening: false, wake_detector_active: false, is_handoff_active: false, ptt_available: false, ptt_is_recording: false, stt_available: true, tts_available: false },
  } as never);
});

afterEach(() => { vi.restoreAllMocks(); });

describe("getVoiceStatus", () => {
  it("returns runtime_available field", async () => {
    const result = await getVoiceStatus();
    expect(result.runtime_available).toBe(true);
  });
});
