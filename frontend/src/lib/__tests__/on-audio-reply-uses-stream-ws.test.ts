import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, onAudioReply } from "@/lib/voice-ws";

describe("onAudioReply uses voiceStreamWS", () => {
  let subscribeBinarySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    subscribeBinarySpy = vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("delegates to voiceStreamWS.subscribeBinary()", () => {
    const handler = vi.fn();
    onAudioReply(handler);
    expect(subscribeBinarySpy).toHaveBeenCalledWith(handler);
  });
});
