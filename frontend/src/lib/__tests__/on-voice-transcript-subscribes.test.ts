import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript subscribes to voiceStreamWS", () => {
  let subscribeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    subscribeSpy = vi.spyOn(voiceStreamWS, "subscribe").mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls voiceStreamWS.subscribe()", () => {
    onVoiceTranscript(vi.fn());
    expect(subscribeSpy).toHaveBeenCalledOnce();
  });
});
