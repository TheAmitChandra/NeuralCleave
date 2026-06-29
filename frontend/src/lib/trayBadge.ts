/**
 * Updates the Tauri tray icon's tooltip with the total unread channel
 * count. No-ops entirely outside the Tauri shell — there's no tray
 * icon to update in a regular browser tab.
 */
import { isTauri, invoke } from "@tauri-apps/api/core";

export async function setUnreadBadge(count: number): Promise<void> {
  if (!isTauri()) return;
  await invoke("set_unread_badge", { count });
}
