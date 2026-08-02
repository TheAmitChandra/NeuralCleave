import { describe, it, expect } from "vitest";
import { voiceStreamWS } from "@/lib/voice-ws";

describe("voiceStreamWS export", () => {
  it("is exported from the voice-ws module", () => {
    expect(voiceStreamWS).toBeDefined();
  });

  it("is a non-null object", () => {
    expect(voiceStreamWS).not.toBeNull();
    expect(typeof voiceStreamWS).toBe("object");
  });
});
