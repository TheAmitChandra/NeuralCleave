import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceTranscriptCard } from "@/components/voice/VoiceTranscriptCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((selector) =>
    selector({ lastTranscript: "" })
  ),
}));

describe("VoiceTranscriptCard", () => {
  it("shows placeholder text when lastTranscript is empty", () => {
    render(<VoiceTranscriptCard />);
    expect(screen.getByText(/No transcript yet/i)).toBeInTheDocument();
  });
});
