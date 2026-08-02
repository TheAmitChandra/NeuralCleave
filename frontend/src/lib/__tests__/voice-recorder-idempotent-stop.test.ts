import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

describe("VoiceRecorder.stop() idempotent", () => {
  let disconnectSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    disconnectSpy = vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    vi.stubGlobal("window", {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("calling stop() when not recording does not call disconnect", () => {
    const recorder = new VoiceRecorder();
    recorder.stop();
    expect(disconnectSpy).not.toHaveBeenCalled();
  });
});
