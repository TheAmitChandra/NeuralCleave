"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { gatewayWS } from "@/lib/websocket";
import { sendDesktopNotification } from "@/lib/notifications";

export default function DashboardShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Keeps a live gateway connection for the lifetime of the dashboard so
  // agent replies can trigger a desktop notification when the window
  // isn't focused. There's no chat-send UI yet (nothing emits a "message"
  // frame today), so this currently has no live trigger — it's correct,
  // tested infrastructure ready for when a chat UI lands.
  useEffect(() => {
    gatewayWS.connect();
    const unsubscribe = gatewayWS.subscribe((msg) => {
      if (msg.type !== "message" || !msg.text) return;
      if (document.hasFocus()) return;
      void sendDesktopNotification("CortexFlow-AI", msg.text);
    });
    return () => {
      unsubscribe();
      gatewayWS.disconnect();
    };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-slate-950">
      <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Topbar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 sm:p-6">{children}</main>
      </div>
    </div>
  );
}
