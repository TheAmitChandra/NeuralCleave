import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: true,
    startPtt: vi.fn(),
    stopPtt: vi.fn(),
  }),
}));

describe("PushToTalkButton", () => {
  it("has aria-label 'Release to send' while recording", () => {
    render(<PushToTalkButton />);
    expect(screen.getByLabelText("Release to send")).toBeInTheDocument();
  });
});
