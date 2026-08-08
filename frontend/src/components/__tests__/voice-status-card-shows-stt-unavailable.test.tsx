import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    sttAvailable: false,
    ttsAvailable: false,
    wakeDetectorActive: false,
    pttAvailable: false,
  }),
}));

describe("VoiceStatusCard", () => {
  it("shows Unavailable labels when no subsystem is configured", () => {
    render(<VoiceStatusCard />);
    const unavailable = screen.getAllByText("Unavailable");
    expect(unavailable.length).toBeGreaterThanOrEqual(2);
  });
});
