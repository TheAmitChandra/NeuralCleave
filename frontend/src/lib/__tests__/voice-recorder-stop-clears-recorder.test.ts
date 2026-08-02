import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

let capturedMediaRecorder: { stop: ReturnType<typeof vi.fn> };

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    capturedMediaRecorder = this;
  }
}

describe("VoiceRecorder.stop() calls recorder.stop()", () => {
  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("window", {});
    vi.stubGlobal("navigator", {
      mediaDevices: { getUserMedia: vi.fn(() => Promise.resolve({ getTracks: () => [] })) },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("calls MediaRecorder.stop() when recording stops", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    recorder.stop();
    expect(capturedMediaRecorder.stop).toHaveBeenCalledOnce();
  });
});
