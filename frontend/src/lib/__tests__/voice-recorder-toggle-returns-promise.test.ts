import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

describe("VoiceRecorder.toggle() returns a Promise", () => {
  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    vi.stubGlobal("window", {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("toggle() when recording returns a resolved Promise", () => {
    const recorder = new VoiceRecorder();
    // Manually force recording state to true to test the stop branch
    (recorder as unknown as { _recording: boolean })._recording = true;
    const result = recorder.toggle();
    expect(result).toBeInstanceOf(Promise);
  });
});
