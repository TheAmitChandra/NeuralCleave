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
    input: [
      { index: 0, name: "Mic Alpha", channels: 1, sample_rate: 44100, is_default: true },
      { index: 1, name: "Mic Beta", channels: 1, sample_rate: 44100, is_default: false },
      { index: 2, name: "Mic Gamma", channels: 2, sample_rate: 48000, is_default: false },
    ],
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – multiple input devices", () => {
  it("renders all fetched input devices as options (plus System default)", async () => {
    render(<SettingsPage />);
    await waitFor(() => expect(vi.mocked(getVoiceDevices)).toHaveBeenCalled());
    const label = screen.getByText("Input Device");
    const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
    const select = row?.querySelector("select") as HTMLSelectElement;
    await waitFor(() => expect(Array.from(select.options).length).toBe(4)); // 3 devices + System default
    const names = Array.from(select.options).map((o) => o.text);
    expect(names).toContain("Mic Alpha");
    expect(names).toContain("Mic Beta");
    expect(names).toContain("Mic Gamma");
  });
});
