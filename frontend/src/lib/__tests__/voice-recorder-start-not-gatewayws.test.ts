import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";
import { gatewayWS } from "@/lib/websocket";

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

describe("VoiceRecorder does not use gatewayWS", () => {
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

  it("does not call gatewayWS.sendBinary() when audio data is available", async () => {
    const gatewaySendSpy = vi.spyOn(gatewayWS, "sendBinary").mockReturnValue(true);
    const recorder = new VoiceRecorder();
    await recorder.start();
    capturedRecorder.ondataavailable?.({ data: { size: 42 } });
    expect(gatewaySendSpy).not.toHaveBeenCalled();
    recorder.stop();
  });
});
