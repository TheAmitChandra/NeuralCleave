import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

let capturedRecorder: { ondataavailable: ((e: { data: { size: number } }) => void) | null };

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  constructor() {
    // eslint-disable-next-line @typescript-eslint/no-this-alias
    capturedRecorder = this;
  }
}

describe("VoiceRecorder skips empty audio chunks", () => {
  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
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

  it("does not call sendBinary when e.data.size is 0", async () => {
    const sendSpy = vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    const recorder = new VoiceRecorder();
    await recorder.start();
    capturedRecorder.ondataavailable?.({ data: { size: 0 } });
    expect(sendSpy).not.toHaveBeenCalled();
    recorder.stop();
  });
});
