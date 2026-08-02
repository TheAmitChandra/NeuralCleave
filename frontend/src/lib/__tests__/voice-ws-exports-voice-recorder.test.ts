import { describe, it, expect } from "vitest";
import { voiceRecorder, VoiceRecorder } from "@/lib/voice-ws";

describe("voiceRecorder singleton export", () => {
  it("is exported as a module-level singleton", () => {
    expect(voiceRecorder).toBeDefined();
  });

  it("is an instance of VoiceRecorder", () => {
    expect(voiceRecorder).toBeInstanceOf(VoiceRecorder);
  });
});
