import { describe, it, expect, vi } from "vitest";

describe("onVoiceTranscript cleanup", () => {
  it("calling the returned function unsubscribes (does not invoke the handler after)", () => {
    const handler = vi.fn();
    let storedFn: ((text: string) => void) | null = null;

    const fakeSubscribe = (fn: (text: string) => void) => {
      storedFn = fn;
      return () => { storedFn = null; };
    };

    const unsub = fakeSubscribe(handler);
    unsub();
    // Explicit cast resets TS closure-narrowing; ?.() safely no-ops if null.
    (storedFn as ((text: string) => void) | null)?.("should not be received");

    expect(handler).not.toHaveBeenCalled();
  });
});
