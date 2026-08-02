import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
}

describe("VoiceRecorder.stop() disconnects voiceStreamWS", () => {
  let disconnectSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    disconnectSpy = vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
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

  it("calls voiceStreamWS.disconnect() when recording stops", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    recorder.stop();
    expect(disconnectSpy).toHaveBeenCalledOnce();
  });
});
