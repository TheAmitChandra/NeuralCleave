import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
}

describe("VoiceRecorder.stop() calls disconnect after clearing recording flag", () => {
  const callOrder: string[] = [];

  beforeEach(() => {
    callOrder.length = 0;
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {
      callOrder.push("disconnect");
    });
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

  it("recorder is no longer recording when disconnect is called", async () => {
    let recordingAtDisconnect: boolean | undefined;
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(function (this: { _isRecording?: boolean }) {
      callOrder.push("disconnect");
    });

    const recorder = new VoiceRecorder();
    const origDisconnect = voiceStreamWS.disconnect.bind(voiceStreamWS);
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {
      recordingAtDisconnect = recorder.recording;
      origDisconnect();
    });

    await recorder.start();
    recorder.stop();
    expect(recordingAtDisconnect).toBe(false);
  });
});
