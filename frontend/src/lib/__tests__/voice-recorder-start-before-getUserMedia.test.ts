import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
}

describe("VoiceRecorder.start() connects before getUserMedia", () => {
  const callOrder: string[] = [];

  beforeEach(() => {
    callOrder.length = 0;
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {
      callOrder.push("connect");
    });
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("window", {});
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn(() => {
          callOrder.push("getUserMedia");
          return Promise.resolve({ getTracks: () => [] });
        }),
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("calls voiceStreamWS.connect() before navigator.getUserMedia()", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    expect(callOrder[0]).toBe("connect");
    expect(callOrder[1]).toBe("getUserMedia");
    recorder.stop();
  });
});
