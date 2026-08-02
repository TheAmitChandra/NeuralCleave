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
    output: [],
    active: { input_device: null, output_device: null },
  }),
}));

describe("VoiceSection – empty input device not sent", () => {
  it("does not include input_device in PATCH payload when no device is selected", async () => {
    render(<SettingsPage />);
    const saveButton = screen.getAllByText("Save")[3]; // Voice section Save
    fireEvent.click(saveButton);
    await waitFor(() => expect(vi.mocked(apiClient.patch)).toHaveBeenCalled());
    const patchCall = vi.mocked(apiClient.patch).mock.calls[0];
    expect(patchCall[1]).not.toHaveProperty("input_device");
  });
});
