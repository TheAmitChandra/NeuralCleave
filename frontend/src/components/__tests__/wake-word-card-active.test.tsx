import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WakeWordCard } from "@/components/voice/WakeWordCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    wakeDetectorActive: true,
    handoffActive: false,
  }),
}));

describe("WakeWordCard", () => {
  it("shows detector active text when wakeDetectorActive is true", () => {
    render(<WakeWordCard />);
    expect(screen.getByText("Detector active")).toBeInTheDocument();
  });
});
