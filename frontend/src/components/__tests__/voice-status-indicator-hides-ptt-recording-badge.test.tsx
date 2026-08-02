import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel: (s: object) => unknown) =>
    sel({
      continuousListening: false,
      continuousAvailable: true,
      wakeDetectorActive: false,
      pttRecording: false,
      startListening: vi.fn(),
      stopListening: vi.fn(),
      pollStatus: vi.fn().mockResolvedValue(undefined),
    })
  ),
}));

describe("VoiceStatusIndicator", () => {
  it("hides the Recording badge when pttRecording is false", () => {
    render(<VoiceStatusIndicator />);
    expect(screen.queryByText("Recording")).not.toBeInTheDocument();
  });
});
