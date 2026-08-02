import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript returns unsubscribe function", () => {
  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "subscribe").mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the unsubscribe fn from voiceStreamWS.subscribe", () => {
    const unsubscribe = vi.fn();
    vi.spyOn(voiceStreamWS, "subscribe").mockReturnValue(unsubscribe);
    const result = onVoiceTranscript(vi.fn());
    expect(result).toBe(unsubscribe);
  });
});
