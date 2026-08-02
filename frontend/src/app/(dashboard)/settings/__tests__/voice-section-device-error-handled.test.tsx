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
  getVoiceDevices: vi.fn().mockRejectedValue(new Error("gateway offline")),
}));

describe("VoiceSection – device fetch error", () => {
  it("renders without crashing when getVoiceDevices rejects", () => {
    expect(() => render(<SettingsPage />)).not.toThrow();
    expect(screen.getByText("Input Device")).toBeInTheDocument();
    expect(screen.getByText("Output Device")).toBeInTheDocument();
  });
});
