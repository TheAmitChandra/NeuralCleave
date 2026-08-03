import { describe, it, expect, vi, afterEach } from "vitest";
import { voiceStreamWS, onAudioReply } from "@/lib/voice-ws";

describe("onAudioReply uses voiceStreamWS", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("delegates to voiceStreamWS.subscribeBinary()", () => {
    const subscribeBinarySpy = vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(() => {});
    const handler = vi.fn();
    onAudioReply(handler);
    expect(subscribeBinarySpy).toHaveBeenCalledWith(handler);
  });
});
