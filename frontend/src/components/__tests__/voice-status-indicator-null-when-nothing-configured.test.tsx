import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { VoiceStatusIndicator } from "@/components/VoiceStatusIndicator";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    continuousListening: false,
    continuousAvailable: false,
    wakeDetectorActive: false,
    pttRecording: false,
    sttAvailable: false,
    startListening: vi.fn(),
    stopListening: vi.fn(),
    pollStatus: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("VoiceStatusIndicator", () => {
  it("renders nothing when no voice subsystem is configured", () => {
    const { container } = render(<VoiceStatusIndicator />);
    expect(container.firstChild).toBeNull();
  });
});
