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
    input: [{ index: 3, name: "Line In", channels: 2, sample_rate: 44100, is_default: false }],
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – input option value is device name", () => {
  it("uses the device name (not index) as the option value for input devices", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vi.mocked(getVoiceDevices)).toHaveBeenCalled());
    const label = screen.getByText("Input Device");
    const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
    const select = row?.querySelector("select") as HTMLSelectElement;
    await waitFor(() => expect(Array.from(select.options).length).toBeGreaterThan(1));
    const lineInOption = Array.from(select.options).find((o) => o.text === "Line In");
    expect(lineInOption?.value).toBe("Line In");
  });
});
