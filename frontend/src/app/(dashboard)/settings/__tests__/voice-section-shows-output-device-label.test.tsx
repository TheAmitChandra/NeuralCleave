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

describe("VoiceSection – Output Device label", () => {
  it("renders an 'Output Device' label in the voice section", () => {
    render(<SettingsPage />);
    expect(screen.getByText("Output Device")).toBeInTheDocument();
  });
});
