import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

const stopPtt = vi.fn().mockResolvedValue(undefined);

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: true,
    startPtt: vi.fn(),
    stopPtt,
  }),
}));

describe("PushToTalkButton", () => {
  it("calls stopPtt on mouseup", () => {
    render(<PushToTalkButton />);
    fireEvent.mouseUp(screen.getByRole("button"));
    expect(stopPtt).toHaveBeenCalledTimes(1);
  });
});
