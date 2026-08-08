import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn().mockReturnValue({
    pttAvailable: true,
    pttRecording: false,
    startPtt: vi.fn(),
    stopPtt: vi.fn(),
  }),
}));

describe("PushToTalkButton", () => {
  it("shows the hold-to-talk tooltip when pttAvailable is true", () => {
    render(<PushToTalkButton />);
    const btn = screen.getByRole("button");
    expect(btn.title).toMatch(/hold while speaking/i);
  });
});
