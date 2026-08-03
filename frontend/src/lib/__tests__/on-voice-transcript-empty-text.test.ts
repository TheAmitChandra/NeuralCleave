import { describe, it, expect, vi, afterEach } from "vitest";
import { voiceStreamWS, onVoiceTranscript } from "@/lib/voice-ws";

describe("onVoiceTranscript skips frames with empty text", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not fire handler when audio_transcript text is missing", () => {
    let capturedSubscriber: ((msg: { type: string; text?: string }) => void) | null = null;
    vi.spyOn(voiceStreamWS, "subscribe").mockImplementation((fn) => {
      capturedSubscriber = fn as (msg: { type: string; text?: string }) => void;
      return () => {};
    });

    const handler = vi.fn();
    onVoiceTranscript(handler);

    capturedSubscriber?.({ type: "audio_transcript" }); // no text field
    expect(handler).not.toHaveBeenCalled();
  });
});
