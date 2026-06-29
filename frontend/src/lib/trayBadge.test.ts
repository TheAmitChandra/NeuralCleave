import { describe, it, expect, vi, beforeEach } from "vitest";

const isTauriMock = vi.fn();
const invokeMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: isTauriMock,
  invoke: invokeMock,
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("setUnreadBadge", () => {
  it("no-ops outside Tauri without invoking the command", async () => {
    isTauriMock.mockReturnValue(false);
    const { setUnreadBadge } = await import("./trayBadge");

    await setUnreadBadge(3);

    expect(invokeMock).not.toHaveBeenCalled();
  });

  it("invokes set_unread_badge with the count inside Tauri", async () => {
    isTauriMock.mockReturnValue(true);
    const { setUnreadBadge } = await import("./trayBadge");

    await setUnreadBadge(5);

    expect(invokeMock).toHaveBeenCalledWith("set_unread_badge", { count: 5 });
  });
});
