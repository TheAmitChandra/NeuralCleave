import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, VoiceRecorder } from "@/lib/voice-ws";

let capturedMimeType: string | undefined;

class MockMediaRecorder {
  static isTypeSupported = vi.fn((mime: string) => mime === "audio/ogg;codecs=opus");
  ondataavailable: ((e: { data: { size: number } }) => void) | null = null;
  start = vi.fn();
  stop = vi.fn();
  constructor(_stream: unknown, options?: { mimeType?: string }) {
    capturedMimeType = options?.mimeType;
  }
}

describe("VoiceRecorder MIME preference", () => {
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
    capturedMimeType = undefined;
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("prefers audio/ogg;codecs=opus when supported", async () => {
    const recorder = new VoiceRecorder();
    await recorder.start();
    expect(capturedMimeType).toBe("audio/ogg;codecs=opus");
    recorder.stop();
  });
});
