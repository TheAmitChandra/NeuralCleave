import { describe, it, expect } from "vitest";
import { onAudioReply } from "@/lib/voice-ws";

describe("onAudioReply export", () => {
  it("is exported as a function", () => {
    expect(typeof onAudioReply).toBe("function");
  });
});
