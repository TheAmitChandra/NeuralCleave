/**
 * Native desktop notifications via the Tauri notification plugin.
 * No-ops entirely outside the Tauri shell (isTauri() is false in a
 * regular browser tab) — there's no OS notification center to talk to
 * there, and the plugin's IPC calls would just hang/reject.
 */
import { isTauri } from "@tauri-apps/api/core";
import {
  isPermissionGranted,
  requestPermission,
  sendNotification,
} from "@tauri-apps/plugin-notification";

async function ensurePermission(): Promise<boolean> {
  if (await isPermissionGranted()) return true;
  const permission = await requestPermission();
  return permission === "granted";
}

/**
 * Shows a native OS notification. Returns whether it was actually
 * sent (false if outside Tauri or permission was denied).
 */
export async function sendDesktopNotification(
  title: string,
  body?: string
): Promise<boolean> {
  if (!isTauri()) return false;
  if (!(await ensurePermission())) return false;
  sendNotification({ title, body });
  return true;
}
