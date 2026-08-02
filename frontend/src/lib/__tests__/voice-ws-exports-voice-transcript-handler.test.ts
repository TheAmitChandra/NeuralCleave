import { describe, it, expect } from "vitest";
import { onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript export", () => {
  it("is exported as a function", () => {
    expect(typeof onVoiceTranscript).toBe("function");
  });
});
