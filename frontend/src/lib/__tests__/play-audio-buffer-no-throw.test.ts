import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { playAudioBuffer } from "@/lib/voice-ws";

describe("playAudioBuffer swallows errors", () => {
  beforeEach(() => {
    const MockAudioContext = vi.fn(() => ({
      decodeAudioData: vi.fn(() => Promise.reject(new Error("unsupported format"))),
      createBufferSource: vi.fn(),
      destination: {},
      close: vi.fn(),
    }));
    vi.stubGlobal("AudioContext", MockAudioContext);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not throw when decodeAudioData rejects", async () => {
    const data = new ArrayBuffer(4);
    await expect(playAudioBuffer(data)).resolves.toBeUndefined();
  });
});
