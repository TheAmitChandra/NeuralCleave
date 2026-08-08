import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import VoicePage from "../page";

const STORE_STATE = {
  continuousListening: false,
  continuousAvailable: true,
  sttAvailable: false,
  ttsAvailable: false,
  wakeDetectorActive: false,
  pttAvailable: false,
  pttRecording: false,
  handoffActive: false,
  lastTranscript: "",
  pollStatus: vi.fn().mockResolvedValue(undefined),
  startListening: vi.fn(),
  stopListening: vi.fn(),
  startPtt: vi.fn(),
  stopPtt: vi.fn(),
};

vi.mock("@/store/voice", () => ({
  useVoiceStore: vi.fn((sel) => (sel ? sel(STORE_STATE) : STORE_STATE)),
}));

describe("VoicePage", () => {
  it("shows the Continuous Listening toggle when continuousAvailable is true", () => {
    render(<VoicePage />);
    expect(screen.getByText("Continuous Listening")).toBeInTheDocument();
  });
});
