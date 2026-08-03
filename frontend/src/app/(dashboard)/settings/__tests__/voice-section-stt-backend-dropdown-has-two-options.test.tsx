import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import SettingsPage from "../page";

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
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
  getVoiceDevices: vi.fn().mockResolvedValue({
    input: [],
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – STT Backend dropdown options", () => {
  it("STT Backend dropdown has exactly two options: Disabled and Local Whisper", () => {
    render(<SettingsPage />);
    const sttSelect = screen
      .getAllByRole("combobox")
      .find((el) =>
        Array.from((el as HTMLSelectElement).options).some((o) => o.value === "whisper")
      ) as HTMLSelectElement | undefined;
    expect(sttSelect).toBeTruthy();
    const values = Array.from((sttSelect as HTMLSelectElement).options).map((o) => o.value);
    expect(values).toContain("none");
    expect(values).toContain("whisper");
    expect((sttSelect as HTMLSelectElement).options.length).toBe(2);
  });
});
