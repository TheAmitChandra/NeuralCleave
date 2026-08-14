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

describe("LLM Providers section – save sends openrouter_api_key", () => {
  it("includes openrouter_api_key in the POST /settings/llm payload when filled in", async () => {
    render(<SettingsPage />);
    const label = screen.getByText("OpenRouter API Key");
    const row = label.closest("div")!.parentElement!;
    const input = row.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "or-test-key" } });

    const saveButton = screen.getAllByText("Save")[1]; // LLM Providers section Save
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
        "/settings/llm",
        expect.objectContaining({ openrouter_api_key: "or-test-key" }),
      )
    );
  });
});
