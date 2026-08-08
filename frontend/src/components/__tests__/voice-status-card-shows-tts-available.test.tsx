import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    sttAvailable: false,
    ttsAvailable: true,
    wakeDetectorActive: false,
    pttAvailable: false,
  }),
}));

describe("VoiceStatusCard", () => {
  it("shows TTS as Available when ttsAvailable is true", () => {
    render(<VoiceStatusCard />);
    expect(screen.getByText("Text-to-Speech (TTS)")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
  });
});
