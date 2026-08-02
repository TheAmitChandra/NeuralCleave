import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

class MockMediaRecorder {
  static isTypeSupported = vi.fn(() => false);
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
}

describe("VoiceRecorder.start() requests microphone", () => {
  let getUserMediaSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "connect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "disconnect").mockImplementation(() => {});
    vi.spyOn(voiceStreamWS, "sendBinary").mockReturnValue(true);
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    vi.stubGlobal("window", {});
    getUserMediaSpy = vi.fn(() => Promise.resolve({ getTracks: () => [] }));
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia: getUserMediaSpy } });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("calls getUserMedia with audio:true, video:false", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    expect(getUserMediaSpy).toHaveBeenCalledWith({ audio: true, video: false });
    recorder.stop();
  });
});
