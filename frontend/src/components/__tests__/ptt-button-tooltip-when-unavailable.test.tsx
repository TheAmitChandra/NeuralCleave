import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: false,
    pttRecording: false,
    startPtt: vi.fn(),
    stopPtt: vi.fn(),
  }),
}));

describe("PushToTalkButton", () => {
  it("shows a settings tooltip when pttAvailable is false", () => {
    render(<PushToTalkButton />);
    const btn = screen.getByRole("button");
    expect(btn.title).toMatch(/Settings/i);
  });
});
