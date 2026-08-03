import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import SettingsPage from "../page";
import * as api from "@/lib/api";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(() => false) }));
vi.mock("@tauri-apps/plugin-autostart", () => ({
  isEnabled: vi.fn().mockResolvedValue(false),
  enable: vi.fn(),
  disable: vi.fn(),
}));
vi.mock("@/lib/notifications", () => ({ sendDesktopNotification: vi.fn() }));
vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    patch: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
  getVoiceDevices: vi.fn().mockResolvedValue({
    input: [],
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – save voice calls POST /settings/voice", () => {
  it("calls apiClient.post with /settings/voice when Voice Save is clicked", async () => {
    const postMock = vi.mocked(api.default.post);
    render(<SettingsPage />);

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    const voiceSaveBtn = saveButtons.find((b) => {
      const section = b.closest("[class*='rounded-2xl']");
      return section?.textContent?.includes("STT Backend");
    });
    expect(voiceSaveBtn).toBeTruthy();

    await act(async () => {
      fireEvent.click(voiceSaveBtn!);
    });

    const calls = postMock.mock.calls;
    const voiceCall = calls.find((c) => c[0] === "/settings/voice");
    expect(voiceCall).toBeTruthy();
  });
});
