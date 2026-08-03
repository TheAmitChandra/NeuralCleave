import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
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
    post: vi.fn().mockResolvedValue({ data: { ok: true, restart_required: true } }),
  },
  getVoiceDevices: vi.fn().mockResolvedValue({
    input: [],
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – amber restart notice", () => {
  it("shows amber restart notice after saving STT backend change", async () => {
    render(<SettingsPage />);

    const saveButtons = screen.getAllByRole("button", { name: /save/i });
    const voiceSaveBtn = saveButtons.find((b) =>
      b.closest("[class*='rounded-2xl']")?.textContent?.includes("STT Backend")
    );

    await act(async () => { fireEvent.click(voiceSaveBtn!); });

    await waitFor(() =>
      expect(screen.queryByText(/restart the gateway/i)).not.toBeNull()
    );
  });
});
