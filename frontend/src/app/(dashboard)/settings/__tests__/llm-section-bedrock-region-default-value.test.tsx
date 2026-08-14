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
  getVoiceDevices: vi.fn().mockResolvedValue({ input: [], output: [], active: {} }),
}));

describe("LLM Providers section – Bedrock Region field", () => {
  it("defaults to us-east-1", () => {
    render(<SettingsPage />);
    const label = screen.getByText("Bedrock Region");
    const row = label.closest("div")!.parentElement!;
    const input = row.querySelector("input") as HTMLInputElement;
    expect(input.value).toBe("us-east-1");
  });
});
