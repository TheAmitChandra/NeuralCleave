import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";
import { useVoiceStore } from "@/store/voice";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: true,
    startPtt: vi.fn(),
    stopPtt: vi.fn().mockResolvedValue(undefined),
  }),
}));

describe("PushToTalkButton", () => {
  it("calls stopPtt on mouseup", () => {
    render(<PushToTalkButton />);
    const { stopPtt } = vi.mocked(useVoiceStore)();
    fireEvent.mouseUp(screen.getByRole("button"));
    expect(stopPtt).toHaveBeenCalledTimes(1);
  });
});
