import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    sttAvailable: false,
    ttsAvailable: false,
    wakeDetectorActive: true,
    pttAvailable: false,
  }),
}));

describe("VoiceStatusCard", () => {
  it("shows Wake Word as Active when wakeDetectorActive is true", () => {
    render(<VoiceStatusCard />);
    expect(screen.getByText("Wake Word")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
});
