"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { GatewayToast } from "@/components/layout/GatewayToast";
import { gatewayWS } from "@/lib/websocket";
import { sendDesktopNotification } from "@/lib/notifications";
import { setUnreadBadge } from "@/lib/trayBadge";
import api from "@/lib/api";

interface GatewayStatus {
  status: string;
  runtime_available: boolean;
  init_phase: string;
}

interface ChannelsResponse {
  channels: { unread: number }[];
}

export default function DashboardShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const prevReadyRef = useRef(false);

  // Poll gateway status — shares the same React Query key as Topbar so both
  // components read from a single network request.
  // Shares the "gateway-status" query key with Topbar — React Query dedupes
  // into a single network request. Use the same smart backoff so we don't
  // override Topbar's 30 s interval when the runtime is fully ready.
  const { data: gatewayStatus } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    queryFn: async () => {
      const { data } = await api.get<GatewayStatus>("/status", { timeout: 5_000 });
      return data;
    },
    refetchInterval: (query) => {
      const d = query.state.data;
      if (d?.status === "ok" && d.runtime_available && d.init_phase === "ready") return 30_000;
      return 3_000;
    },
    refetchIntervalInBackground: true,
    networkMode: "always",
    retry: false,
  });

  // Re-apply saved LLM settings to the gateway every time it transitions from
  // not-ready to ready (covers first launch and gateway restarts). The gateway
  // holds API keys only in memory, so a restart wipes them. localStorage is
  // the durable source of truth for the session.
  useEffect(() => {
    const isReady = !!(gatewayStatus?.runtime_available);
    if (isReady && !prevReadyRef.current) {
      prevReadyRef.current = true;
      try {
        const raw = localStorage.getItem("NeuralCleave_settings");
        if (!raw) return;
        const saved = JSON.parse(raw) as Record<string, Record<string, string>>;
        const llm = saved.llm ?? {};
        const model = saved.model ?? {};

        const llmPayload: Record<string, string | boolean> = {};
        if (llm["Gemini API Key"]) llmPayload.gemini_api_key = llm["Gemini API Key"];
        if (llm["DeepSeek API Key"]) llmPayload.deepseek_api_key = llm["DeepSeek API Key"];
        if (llm["Anthropic API Key"]) llmPayload.anthropic_api_key = llm["Anthropic API Key"];
        if (llm["OpenAI API Key"]) llmPayload.openai_api_key = llm["OpenAI API Key"];
        if (llm["Ollama Base URL"]) llmPayload.ollama_base_url = llm["Ollama Base URL"];
        llmPayload.web_search_enabled = llm["Web Search"] === "true";

        void api.post("/settings/llm", llmPayload).catch(() => {});

        if (model["Active Provider"]) {
          void api.post("/settings/model", { provider: model["Active Provider"] }).catch(() => {});
        }
      } catch {
        // malformed localStorage — leave gateway at defaults
      }
    } else if (!isReady) {
      prevReadyRef.current = false;
    }
  }, [gatewayStatus?.runtime_available]);

  // Keeps a live gateway connection for the lifetime of the dashboard so
  // agent replies can trigger a desktop notification when the window isn't
  // focused. Replies stream as message_chunk frames followed by one
  // message_done frame (neuralcleave/gateway/websocket.py) — notify off
  // message_done, since that's the only frame guaranteed to carry the full
  // reply text exactly once per message.
  useEffect(() => {
    gatewayWS.connect();
    const unsubscribe = gatewayWS.subscribe((msg) => {
      if (msg.type !== "message_done" || !msg.text) return;
      if (document.hasFocus()) return;
      void sendDesktopNotification("NeuralCleave", msg.text);
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
    <div className="flex h-screen overflow-hidden bg-[#08080f]">
      <Sidebar open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />
      <div className="flex flex-1 min-w-0 flex-col overflow-hidden">
        <Topbar onMenuClick={() => setMobileNavOpen(true)} />
        <main className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 relative">{children}</main>
      </div>
      <GatewayToast />
    </div>
  );
}
