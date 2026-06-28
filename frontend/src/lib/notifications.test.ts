import { describe, it, expect, vi, beforeEach } from "vitest";

const isTauriMock = vi.fn();
const isPermissionGrantedMock = vi.fn();
const requestPermissionMock = vi.fn();
const sendNotificationMock = vi.fn();

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: isTauriMock,
}));

vi.mock("@tauri-apps/plugin-notification", () => ({
  isPermissionGranted: isPermissionGrantedMock,
  requestPermission: requestPermissionMock,
  sendNotification: sendNotificationMock,
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("sendDesktopNotification", () => {
  it("no-ops outside Tauri without touching the plugin", async () => {
    isTauriMock.mockReturnValue(false);
    const { sendDesktopNotification } = await import("./notifications");

    const sent = await sendDesktopNotification("title", "body");

    expect(sent).toBe(false);
    expect(isPermissionGrantedMock).not.toHaveBeenCalled();
    expect(sendNotificationMock).not.toHaveBeenCalled();
  });

  it("sends immediately when permission is already granted", async () => {
    isTauriMock.mockReturnValue(true);
    isPermissionGrantedMock.mockResolvedValue(true);
    const { sendDesktopNotification } = await import("./notifications");

    const sent = await sendDesktopNotification("title", "body");

    expect(sent).toBe(true);
    expect(requestPermissionMock).not.toHaveBeenCalled();
    expect(sendNotificationMock).toHaveBeenCalledWith({ title: "title", body: "body" });
  });

  it("requests permission when not yet granted, then sends if approved", async () => {
    isTauriMock.mockReturnValue(true);
    isPermissionGrantedMock.mockResolvedValue(false);
    requestPermissionMock.mockResolvedValue("granted");
    const { sendDesktopNotification } = await import("./notifications");

    const sent = await sendDesktopNotification("title");

    expect(sent).toBe(true);
    expect(requestPermissionMock).toHaveBeenCalled();
    expect(sendNotificationMock).toHaveBeenCalledWith({ title: "title", body: undefined });
  });

  it("does not send when permission is denied", async () => {
    isTauriMock.mockReturnValue(true);
    isPermissionGrantedMock.mockResolvedValue(false);
    requestPermissionMock.mockResolvedValue("denied");
    const { sendDesktopNotification } = await import("./notifications");

    const sent = await sendDesktopNotification("title");

    expect(sent).toBe(false);
    expect(sendNotificationMock).not.toHaveBeenCalled();
  });
});
