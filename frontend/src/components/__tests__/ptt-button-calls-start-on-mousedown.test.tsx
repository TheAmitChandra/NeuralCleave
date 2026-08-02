import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";
import { useVoiceStore } from "@/store/voice";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: false,
    startPtt: vi.fn().mockResolvedValue(undefined),
    stopPtt: vi.fn(),
  }),
}));

describe("PushToTalkButton", () => {
  it("calls startPtt on mousedown", () => {
    render(<PushToTalkButton />);
    const { startPtt } = vi.mocked(useVoiceStore)();
    fireEvent.mouseDown(screen.getByRole("button"));
    expect(startPtt).toHaveBeenCalledTimes(1);
  });
});
