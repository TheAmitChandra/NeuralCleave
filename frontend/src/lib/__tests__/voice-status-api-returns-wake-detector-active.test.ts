import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient, { getVoiceStatus } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return { ...mod, default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } };
});

const mockedGet = vi.mocked(apiClient.get);

beforeEach(() => {
  mockedGet.mockResolvedValue({
    data: {
      runtime_available: true,
      continuous_listening: false,
      wake_detector_active: true,
      is_handoff_active: false,
      ptt_available: false,
      ptt_is_recording: false,
      stt_available: true,
      tts_available: true,
    },
  });
});

describe("getVoiceStatus", () => {
  it("returns wake_detector_active field", async () => {
    const result = await getVoiceStatus();
    expect(result.wake_detector_active).toBe(true);
  });
});
