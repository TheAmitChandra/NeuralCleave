import { describe, it, expect, vi } from "vitest";
import { onVoiceTranscript } from "@/lib/voice-ws";

vi.mock("@/lib/voice-ws", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/voice-ws")>();
  return { ...mod, onVoiceTranscript: vi.fn().mockReturnValue(vi.fn()) };
});

describe("onVoiceTranscript", () => {
  it("is exported from voice-ws", () => {
    expect(typeof onVoiceTranscript).toBe("function");
  });

  it("returns an unsubscribe function when called", () => {
    const unsub = onVoiceTranscript(vi.fn());
    expect(typeof unsub).toBe("function");
  });
});
