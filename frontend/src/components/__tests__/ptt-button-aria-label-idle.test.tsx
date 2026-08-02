import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel: (s: object) => unknown) =>
    sel({ pttAvailable: true, pttRecording: false, startPtt: vi.fn(), stopPtt: vi.fn() })
  ),
}));

describe("PushToTalkButton", () => {
  it("has aria-label 'Hold to talk' when not recording", () => {
    render(<PushToTalkButton />);
    expect(screen.getByLabelText("Hold to talk")).toBeInTheDocument();
  });
});
