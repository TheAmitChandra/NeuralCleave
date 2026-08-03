import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    continuousListening: false,
    continuousAvailable: false,
    wakeDetectorActive: false,
    pttRecording: false,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    pollStatus: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("VoiceStatusIndicator — Listen button visibility", () => {
  it("renders nothing when both continuousAvailable and wakeDetectorActive are false", () => {
    const { container } = render(<VoiceStatusIndicator />);
    expect(container.firstChild).toBeNull();
    expect(screen.queryByText("Listen")).not.toBeInTheDocument();
  });
});
