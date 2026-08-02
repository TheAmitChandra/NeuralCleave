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
    input: [],
    output: [{ index: 1, name: "Headset Earphones", channels: 2, sample_rate: 48000, is_default: false }],
    active: { input_device: null, output_device: "Headset Earphones" },
  }),
}));

describe("VoiceSection – save sends output_device", () => {
  it("includes output_device in the PATCH /voice/config payload when a device is active", async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      const label = screen.getByText("Output Device");
      const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
      const select = row?.querySelector("select") as HTMLSelectElement;
      expect(select.value).toBe("Headset Earphones");
    });
    const saveButton = screen.getAllByText("Save")[3]; // Voice section Save
    fireEvent.click(saveButton);
    await waitFor(() =>
      expect(vi.mocked(apiClient.patch)).toHaveBeenCalledWith(
        "/voice/config",
        expect.objectContaining({ output_device: "Headset Earphones" }),
      )
    );
  });
});
