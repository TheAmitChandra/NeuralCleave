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

describe("VoiceSection – save voice section", () => {
  it("also calls PATCH /voice/config alongside POST /settings/voice", async () => {
    const patchMock = vi.mocked(api.default.patch);
    render(<SettingsPage />);

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    const voiceSaveBtn = saveButtons.find((b) => {
      const section = b.closest("[class*='rounded-2xl']");
      return section?.textContent?.includes("STT Backend");
    });

    await act(async () => { fireEvent.click(voiceSaveBtn!); });

    const patchCall = patchMock.mock.calls.find((c) => c[0] === "/voice/config");
    expect(patchCall).toBeTruthy();
  });
});
