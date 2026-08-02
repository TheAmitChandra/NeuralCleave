import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, onAudioReply } from "@/lib/voice-ws";

describe("onAudioReply returns unsubscribe function", () => {
  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns the unsubscribe function from voiceStreamWS.subscribeBinary", () => {
    const unsubscribe = vi.fn();
    vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(unsubscribe);
    const result = onAudioReply(vi.fn());
    expect(result).toBe(unsubscribe);
  });
});
