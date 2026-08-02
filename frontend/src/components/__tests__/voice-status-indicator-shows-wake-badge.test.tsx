import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel: (s: object) => unknown) =>
    sel({
      continuousListening: false,
      continuousAvailable: false,
      wakeDetectorActive: true,
      pttRecording: false,
      startListening: vi.fn(),
      stopListening: vi.fn(),
      pollStatus: vi.fn().mockResolvedValue(undefined),
    })
  ),
}));

describe("VoiceStatusIndicator", () => {
  it("shows the Wake badge when wakeDetectorActive is true", () => {
    render(<VoiceStatusIndicator />);
    expect(screen.getByText("Wake")).toBeInTheDocument();
  });
});
