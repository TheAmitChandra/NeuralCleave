import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import SettingsPage from "../page";
import * as api from "@/lib/api";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(() => false), invoke: vi.fn() }));
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

describe("VoiceSection – save calls both PATCH and POST", () => {
  it("Voice Save calls both PATCH /voice/config and POST /settings/voice", async () => {
    const patchMock = vi.mocked(api.default.patch);
    const postMock = vi.mocked(api.default.post);
    render(<SettingsPage />);

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    const voiceSaveBtn = saveButtons.find((b) =>
      b.closest("[class*='rounded-2xl']")?.textContent?.includes("STT Backend")
    );

    await act(async () => { fireEvent.click(voiceSaveBtn!); });

    expect(patchMock).toHaveBeenCalledWith(
      "/voice/config",
      expect.any(Object),
    );
    expect(postMock).toHaveBeenCalledWith(
      "/settings/voice",
      expect.any(Object),
    );
  });
});
