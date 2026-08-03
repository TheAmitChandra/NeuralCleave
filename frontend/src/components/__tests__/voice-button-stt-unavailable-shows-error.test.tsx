import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { VoiceButton } from "@/components/VoiceButton";

vi.mock("@/lib/voice-ws", () => ({
  voiceRecorder: { start: vi.fn(), stop: vi.fn() },
}));

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((selector: (s: { sttAvailable: boolean }) => boolean) =>
    selector({ sttAvailable: false })
  ),
}));

describe("VoiceButton — STT unavailable", () => {
  it("shows an error toast when clicked and STT is not configured", () => {
    render(<VoiceButton />);
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText(/STT not configured/i)).toBeInTheDocument();
  });

  it("has a title hinting that STT needs configuration", () => {
    render(<VoiceButton />);
    const btn = screen.getByRole("button");
    expect(btn.getAttribute("title")).toMatch(/STT not configured|Settings/i);
  });
});
