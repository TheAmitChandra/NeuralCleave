import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import SettingsPage from "../page";
import apiClient from "@/lib/api";

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
    input: [{ index: 0, name: "Blue Yeti", channels: 1, sample_rate: 44100, is_default: false }],
    output: [],
    active: { input_device: "Blue Yeti", output_device: null },
  }),
}));

describe("VoiceSection – save sends input_device", () => {
  it("includes input_device in the PATCH /voice/config payload when a device is active", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      const label = screen.getByText("Input Device");
      const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
      const select = row?.querySelector("select") as HTMLSelectElement;
      expect(select.value).toBe("Blue Yeti");
    });
    const saveButton = screen.getAllByText("Save")[3]; // Voice section Save
    fireEvent.click(saveButton);
    await waitFor(() =>
      expect(vi.mocked(apiClient.patch)).toHaveBeenCalledWith(
        "/voice/config",
        expect.objectContaining({ input_device: "Blue Yeti" }),
      )
    );
  });
});
