import { describe, it, expect, vi, afterEach } from "vitest";
import { voiceStreamWS, onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript fires only for audio_transcript frames", () => {
  // Use the real voiceStreamWS.subscribe to test the filtering logic
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("calls handler when type is audio_transcript", () => {
    let capturedSubscriber: ((msg: { type: string; text?: string }) => void) | null = null;
    vi.spyOn(voiceStreamWS, "subscribe").mockImplementation((fn) => {
      capturedSubscriber = fn as (msg: { type: string; text?: string }) => void;
      return () => {};
    });

    const handler = vi.fn();
    onVoiceTranscript(handler);

    // Explicit cast resets TS closure-narrowing; ?.() safely no-ops if null.
    (capturedSubscriber as ((msg: { type: string; text?: string }) => void) | null)?.({ type: "audio_transcript", text: "hello" });
    expect(handler).toHaveBeenCalledWith("hello");
  });

  it("does not call handler for other frame types", () => {
    let capturedSubscriber: ((msg: { type: string; text?: string }) => void) | null = null;
    vi.spyOn(voiceStreamWS, "subscribe").mockImplementation((fn) => {
      capturedSubscriber = fn as (msg: { type: string; text?: string }) => void;
      return () => {};
    });

    const handler = vi.fn();
    onVoiceTranscript(handler);

    // Explicit casts reset TS closure-narrowing; ?.() safely no-ops if null.
    (capturedSubscriber as ((msg: { type: string; text?: string }) => void) | null)?.({ type: "message_done", text: "hello" });
    (capturedSubscriber as ((msg: { type: string; text?: string }) => void) | null)?.({ type: "ping" });
    expect(handler).not.toHaveBeenCalled();
  });
});
