import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusCard } from "@/components/voice/VoiceStatusCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    sttAvailable: false,
    ttsAvailable: false,
    wakeDetectorActive: false,
    pttAvailable: true,
  }),
}));

describe("VoiceStatusCard", () => {
  it("shows PTT as Available when pttAvailable is true", () => {
    render(<VoiceStatusCard />);
    expect(screen.getByText("Push-to-Talk (PTT)")).toBeInTheDocument();
    expect(screen.getByText("Available")).toBeInTheDocument();
  });
});
