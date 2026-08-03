import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { VoiceButton } from "@/components/VoiceButton";
import * as voiceWs from "@/lib/voice-ws";

vi.mock("@/lib/voice-ws", () => ({
  voiceRecorder: { start: vi.fn().mockResolvedValue(undefined), stop: vi.fn() },
}));

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((selector: (s: { sttAvailable: boolean }) => boolean) =>
    selector({ sttAvailable: true })
  ),
}));

describe("VoiceButton — STT available", () => {
  it("does not show an STT error toast when clicked", async () => {
    render(<VoiceButton />);
    fireEvent.click(screen.getByRole("button"));
    await vi.waitFor(() =>
      expect(vi.mocked(voiceWs.voiceRecorder.start)).toHaveBeenCalledOnce()
    );
    expect(screen.queryByText(/STT not configured/i)).not.toBeInTheDocument();
  });

  it("title says Voice input when STT is available", () => {
    render(<VoiceButton />);
    expect(screen.getByRole("button").getAttribute("title")).toBe("Voice input");
  });
});
