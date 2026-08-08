import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    continuousListening: false,
    continuousAvailable: false,
    wakeDetectorActive: false,
    pttRecording: false,
    sttAvailable: true,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    pollStatus: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("VoiceStatusIndicator", () => {
  it("shows idle Voice badge when STT is available but nothing is actively recording", () => {
    render(<VoiceStatusIndicator />);
    expect(screen.getByText("Voice")).toBeInTheDocument();
  });
});
