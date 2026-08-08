import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { VoiceTranscriptCard } from "@/components/voice/VoiceTranscriptCard";

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((selector) =>
    selector({ lastTranscript: "What is the weather today?" })
  ),
}));

describe("VoiceTranscriptCard", () => {
  it("renders the lastTranscript text when available", () => {
    render(<VoiceTranscriptCard />);
    expect(screen.getByText("What is the weather today?")).toBeInTheDocument();
  });
});
