import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { WakeWordCard } from "@/components/voice/WakeWordCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    wakeDetectorActive: false,
    handoffActive: false,
  }),
}));

describe("WakeWordCard", () => {
  it("shows detector inactive text when wakeDetectorActive is false", () => {
    render(<WakeWordCard />);
    expect(screen.getByText("Detector inactive")).toBeInTheDocument();
  });
});
