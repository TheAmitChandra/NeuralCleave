import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

const mockStartPtt = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: false,
    startPtt: mockStartPtt,
    stopPtt: vi.fn(),
  }),
}));

describe("PushToTalkButton", () => {
  it("calls startPtt on mousedown", () => {
    render(<PushToTalkButton />);
    fireEvent.mouseDown(screen.getByRole("button"));
    expect(mockStartPtt).toHaveBeenCalledTimes(1);
  });
});
