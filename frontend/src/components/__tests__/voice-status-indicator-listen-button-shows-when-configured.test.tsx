import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    continuousListening: false,
    continuousAvailable: true,
    wakeDetectorActive: false,
    pttRecording: false,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    pollStatus: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("VoiceStatusIndicator — Listen button visibility", () => {
  it("shows the Listen button when continuousAvailable is true", () => {
    render(<VoiceStatusIndicator />);
    expect(screen.getByText("Listen")).toBeInTheDocument();
  });
});
