import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import SettingsPage from "../page";

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

describe("VoiceSection – input device System default option", () => {
  it("shows a 'System default' option as the first option in the input device dropdown", () => {
    render(<SettingsPage />);
    const label = screen.getByText("Input Device");
    const row = label.closest("div[class*='flex']")?.closest("div[class*='flex']");
    const select = row?.querySelector("select") as HTMLSelectElement;
    expect(select.options[0].text).toBe("System default");
  });
});
