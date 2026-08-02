import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, getVoiceStatus } from "@/lib/api";

const STATUS_DATA = {
  runtime_available: true,
  continuous_listening: false,
  wake_detector_active: false,
  is_handoff_active: false,
  ptt_available: false,
  ptt_is_recording: false,
  stt_available: true,
  tts_available: true,
};

beforeEach(() => {
  vi.spyOn(apiClient, "get").mockResolvedValue({ data: STATUS_DATA } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("getVoiceStatus", () => {
  it("calls GET /voice/status", async () => {
    await getVoiceStatus();
    expect(apiClient.get).toHaveBeenCalledWith("/voice/status");
  });
});
