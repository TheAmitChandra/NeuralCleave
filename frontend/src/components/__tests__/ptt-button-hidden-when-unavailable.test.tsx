import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PushToTalkButton } from "@/components/PushToTalkButton";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel: (s: object) => unknown) =>
    sel({ pttAvailable: false, pttRecording: false, startPtt: vi.fn(), stopPtt: vi.fn() })
  ),
}));

describe("PushToTalkButton", () => {
  it("renders nothing when pttAvailable is false", () => {
    const { container } = render(<PushToTalkButton />);
    expect(container.firstChild).toBeNull();
  });
});
