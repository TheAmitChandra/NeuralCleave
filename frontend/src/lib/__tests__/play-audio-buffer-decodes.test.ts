import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { playAudioBuffer } from "@/lib/voice-ws";

describe("playAudioBuffer decodes audio", () => {
  let decodeAudioDataSpy: ReturnType<typeof vi.fn>;
  let startSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    startSpy = vi.fn();
    decodeAudioDataSpy = vi.fn(() =>
      Promise.resolve({
        /* decoded AudioBuffer stub */
      }),
    );
    const MockAudioContext = vi.fn(() => ({
      decodeAudioData: decodeAudioDataSpy,
      createBufferSource: vi.fn(() => ({
        buffer: null,
        connect: vi.fn(),
        start: startSpy,
        onended: null,
      })),
      destination: {},
      close: vi.fn(),
    }));
    vi.stubGlobal("AudioContext", MockAudioContext);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("calls decodeAudioData with the provided buffer", async () => {
    const data = new ArrayBuffer(8);
    await playAudioBuffer(data);
    expect(decodeAudioDataSpy).toHaveBeenCalledOnce();
  });

  it("calls source.start() to play back audio", async () => {
    const data = new ArrayBuffer(8);
    await playAudioBuffer(data);
    expect(startSpy).toHaveBeenCalledOnce();
  });
});
