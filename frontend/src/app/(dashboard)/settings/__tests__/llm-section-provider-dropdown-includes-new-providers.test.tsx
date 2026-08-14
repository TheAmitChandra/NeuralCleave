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

function getActiveProviderSelect(): HTMLSelectElement {
  const label = screen.getByText("Active Provider");
  const row = label.closest("div")!.parentElement!;
  return row.querySelector("select") as HTMLSelectElement;
}

describe("Model section – Active Provider dropdown includes the 3 new providers", () => {
  it("includes an OpenRouter option", () => {
    render(<SettingsPage />);
    const select = getActiveProviderSelect();
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toContain("openrouter");
  });

  it("includes an Azure OpenAI option", () => {
    render(<SettingsPage />);
    const select = getActiveProviderSelect();
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toContain("azure");
  });

  it("includes an Amazon Bedrock option", () => {
    render(<SettingsPage />);
    const select = getActiveProviderSelect();
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toContain("bedrock");
  });
});
