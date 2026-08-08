import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    sttAvailable: true,
    ttsAvailable: false,
    wakeDetectorActive: false,
    pttAvailable: false,
  }),
}));

describe("VoiceStatusCard", () => {
  it("shows STT as Available when sttAvailable is true", () => {
    render(<VoiceStatusCard />);
    const availableBadges = screen.getAllByText("Available");
    expect(availableBadges.length).toBeGreaterThanOrEqual(1);
  });
});
