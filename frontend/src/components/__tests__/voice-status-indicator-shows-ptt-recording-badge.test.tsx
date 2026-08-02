import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    continuousListening: false,
    continuousAvailable: true,
    wakeDetectorActive: false,
    pttRecording: true,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    pollStatus: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("VoiceStatusIndicator", () => {
  it("shows the Recording badge when pttRecording is true", () => {
    render(<VoiceStatusIndicator />);
    expect(screen.getByText("Recording")).toBeInTheDocument();
  });
});
