"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { gatewayWS } from "@/lib/websocket";
import { sendDesktopNotification } from "@/lib/notifications";
import { setUnreadBadge } from "@/lib/trayBadge";
import api from "@/lib/api";

interface ChannelsResponse {
  channels: { unread: number }[];
}

export default function DashboardShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Keeps a live gateway connection for the lifetime of the dashboard so
  // agent replies can trigger a desktop notification when the window isn't
  // focused. The Chat page is what actually emits "message" frames.
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

  // Shares the "channels" query key with the Channels page — React Query
  // dedupes this into a single network call when both are mounted, and
  // keeps polling even when the user is on a different page, so the tray
  // badge stays current regardless of which dashboard page is active.
  const { data: channelsData } = useQuery<ChannelsResponse>({
    queryKey: ["channels"],
    queryFn: async () => {
      const { data } = await api.get<ChannelsResponse>("/channels");
      return data;
    },
    refetchInterval: 15_000,
    retry: false,
  });

  useEffect(() => {
    if (!channelsData) return;
    const total = channelsData.channels.reduce((sum, c) => sum + c.unread, 0);
    void setUnreadBadge(total);
  }, [channelsData]);

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
