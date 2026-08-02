import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, getVoiceStatus } from "@/lib/api";

beforeEach(() => {
  vi.spyOn(apiClient, "get").mockResolvedValue({
    data: { runtime_available: true, continuous_listening: false, wake_detector_active: false, is_handoff_active: false, ptt_available: true, ptt_is_recording: true, stt_available: true, tts_available: true },
  } as never);
});

afterEach(() => { vi.restoreAllMocks(); });

describe("getVoiceStatus", () => {
  it("returns ptt_available and ptt_is_recording fields", async () => {
    const result = await getVoiceStatus();
    expect(result.ptt_available).toBe(true);
    expect(result.ptt_is_recording).toBe(true);
  });
});
