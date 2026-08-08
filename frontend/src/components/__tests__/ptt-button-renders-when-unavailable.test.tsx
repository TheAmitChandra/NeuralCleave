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
  it("always renders a button even when pttAvailable is false", () => {
    render(<PushToTalkButton />);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });
});
