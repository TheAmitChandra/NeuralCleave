import { describe, it, expect, vi, afterEach } from "vitest";
import { voiceStreamWS, onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript subscribes to voiceStreamWS", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls voiceStreamWS.subscribe()", () => {
    const subscribeSpy = vi.spyOn(voiceStreamWS, "subscribe").mockReturnValue(() => {});
    onVoiceTranscript(vi.fn());
    expect(subscribeSpy).toHaveBeenCalledOnce();
  });
});
