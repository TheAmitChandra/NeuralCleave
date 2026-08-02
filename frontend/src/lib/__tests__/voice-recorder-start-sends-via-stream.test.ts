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

describe("VoiceRecorder sends audio via voiceStreamWS", () => {
  let sendSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    sendSpy = vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
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

  it("calls voiceStreamWS.sendBinary() when audio data is available", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    capturedRecorder.ondataavailable?.({ data: { size: 42 } });
    expect(sendSpy).toHaveBeenCalledOnce();
    recorder.stop();
  });
});
