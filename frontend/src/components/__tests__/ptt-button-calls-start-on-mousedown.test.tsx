import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

const startPtt = vi.fn().mockResolvedValue(undefined);

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel: (s: object) => unknown) =>
    sel({ pttAvailable: true, pttRecording: false, startPtt, stopPtt: vi.fn() })
  ),
}));

describe("PushToTalkButton", () => {
  it("calls startPtt on mousedown", () => {
    render(<PushToTalkButton />);
    fireEvent.mouseDown(screen.getByRole("button"));
    expect(startPtt).toHaveBeenCalledTimes(1);
  });
});
