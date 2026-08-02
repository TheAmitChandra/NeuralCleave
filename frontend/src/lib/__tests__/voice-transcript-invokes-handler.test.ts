import { describe, it, expect, vi } from "vitest";

describe("onVoiceTranscript handler", () => {
  it("invokes the callback with the transcript text", () => {
    const handler = vi.fn();
    const fakeSubscribe = (fn: (text: string) => void) => { fn("hello world"); return vi.fn(); };

    fakeSubscribe(handler);

    expect(handler).toHaveBeenCalledWith("hello world");
  });
});
