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
  getVoiceDevices: vi.fn().mockResolvedValue({ input: [], output: [], active: {} }),
}));

describe("LLM Providers section – empty OpenRouter key is not sent", () => {
  it("omits openrouter_api_key from the payload when the field is left blank", async () => {
    render(<SettingsPage />);
    const label = screen.getByText("Gemini API Key");
    const row = label.closest("div")!.parentElement!;
    const geminiInput = row.querySelector("input") as HTMLInputElement;
    fireEvent.change(geminiInput, { target: { value: "gk" } }); // give the save something to send

    const saveButton = screen.getAllByText("Save")[1];
    fireEvent.click(saveButton);

    await waitFor(() => expect(vi.mocked(apiClient.post)).toHaveBeenCalled());
    const payload = vi.mocked(apiClient.post).mock.calls[0][1] as Record<string, unknown>;
    expect(payload.openrouter_api_key).toBeUndefined();
  });
});
