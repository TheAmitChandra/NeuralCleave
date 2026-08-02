import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import SettingsPage from "../page";
import { getVoiceDevices } from "@/lib/api";

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
    output: [
      { index: 0, name: "Laptop Speakers", channels: 2, sample_rate: 48000, is_default: true },
      { index: 1, name: "USB DAC", channels: 2, sample_rate: 192000, is_default: false },
    ],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – multiple output devices", () => {
  it("renders all fetched output devices as options (plus System default)", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vi.mocked(getVoiceDevices)).toHaveBeenCalled());
    const label = screen.getByText("Output Device");
    const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
    const select = row?.querySelector("select") as HTMLSelectElement;
    await waitFor(() => expect(Array.from(select.options).length).toBe(3)); // 2 devices + System default
    const names = Array.from(select.options).map((o) => o.text);
    expect(names).toContain("Laptop Speakers");
    expect(names).toContain("USB DAC");
  });
});
