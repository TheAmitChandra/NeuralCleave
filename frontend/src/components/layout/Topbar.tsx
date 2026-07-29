"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Keyboard, Menu, RotateCcw, Shield } from "lucide-react";
import api from "@/lib/api";
import { ShortcutsModal } from "@/components/layout/ShortcutsModal";

interface GatewayStatus {
  status: string;
  version?: string;
  uptime_seconds?: number;
  active_sessions?: number;
  runtime_available?: boolean;
  /** "starting" | "runtime" | "plugins" | "ready" */
  init_phase?: string;
}

interface TopbarProps {
  onMenuClick: () => void;
}

/** Seconds before we stop calling it "Starting" and switch to "Connecting…"
 *  PyInstaller one-file extraction on first run can take 60-90 s on Windows;
 *  set the grace period long enough to cover extraction + uvicorn startup. */
const STARTUP_GRACE_SECONDS = 120;

export function Topbar({ onMenuClick }: TopbarProps) {
  const queryClient = useQueryClient();
  const mountTimeRef = useRef(Date.now());
  const [secondsSinceMount, setSecondsSinceMount] = useState(0);
  const [retrying, setRetrying] = useState(false);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [privacyMode, setPrivacyMode] = useState(false);

  // Tick every second so the countdown label stays live.
  useEffect(() => {
    const id = setInterval(() => {
      setSecondsSinceMount(Math.floor((Date.now() - mountTimeRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const { data, isError, isFetching } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    queryFn: async () => {
      const { data } = await api.get<GatewayStatus>("/status", { timeout: 5_000 });
      return data;
    },
    // Poll every 3 s while initializing / offline so phase labels update
    // promptly; back off to 30 s once the runtime is fully ready.
    refetchInterval: (query) => {
      const d = query.state.data;
      if (d?.status === "ok" && d.runtime_available && d.init_phase === "ready") return 30_000;
      return 3_000;
    },
    // Keep polling even when the Tauri WebView2 window reports as
    // "background" (document.visibilityState can flip to "hidden" during
    // startup on Windows) and regardless of navigator.onLine (localhost
    // connections don't need a real internet link).
    refetchIntervalInBackground: true,
    networkMode: "always",
    retry: 3,
    retryDelay: (attempt) => Math.min(1_000 * 2 ** attempt, 8_000),
  });

  // True only when the runtime is fully ready, not just when the status
  // endpoint starts responding (which now happens before AgentRuntime.start).
  // Use !== false so an old backend that omits runtime_available is still
  // treated as online (backward compat) while an explicit false signals init.
  const online = !isError && data?.status === "ok" && data.runtime_available !== false;
  const isInitializing = !isError && data?.status === "ok" && data.runtime_available === false;

  // Global Ctrl+/ shortcut to toggle the shortcuts panel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "/") {
        e.preventDefault();
        setShortcutsOpen((o) => !o);
      }
      if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
        const tag = (e.target as HTMLElement).tagName;
        if (tag !== "INPUT" && tag !== "TEXTAREA") {
          setShortcutsOpen((o) => !o);
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const handleRetry = useCallback(() => {
    setRetrying(true);
    void queryClient
      .invalidateQueries({ queryKey: ["gateway-status"] })
      .finally(() => setRetrying(false));
  }, [queryClient]);

  async function handlePrivacyToggle() {
    const next = !privacyMode;
    try {
      await api.post("/settings/model", { privacy_mode: next });
      setPrivacyMode(next);
    } catch {
      // Backend not yet ready — update local state optimistically; the
      // running backend will receive it on the next successful request.
      setPrivacyMode(next);
    }
  }

  const statusLabel = (): string => {
    // No data and no error — very first poll, server not yet reachable.
    if (!data && !isError) {
      return secondsSinceMount < STARTUP_GRACE_SECONDS ? "Launching backend…" : "Connecting…";
    }
    // Server responded but hasn't finished initializing.
    if (isInitializing) {
      if (isFetching || retrying) return "Initializing…";
      const phase = data?.init_phase;
      if (phase === "plugins") return "Loading plugins…";
      return "Initializing AI runtime…";
    }
    if (online) return "Gateway online";
    // Error / unreachable state.
    if (isFetching || retrying) return "Reconnecting…";
    return secondsSinceMount < STARTUP_GRACE_SECONDS ? "Starting backend…" : "Connecting…";
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-white/[0.05] px-4 sm:px-6" style={{ background: "#0c0c18" }}>
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 text-white/30 hover:bg-white/[0.05] hover:text-white lg:hidden transition-colors"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="hidden text-[13px] text-white/20 sm:inline tracking-wide">
          Personal AI Assistant Gateway
        </span>
      </div>

      <div className="flex items-center gap-2">
        {!online && !isFetching && !retrying && !isInitializing && (
          <button
            onClick={handleRetry}
            className="hidden items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-white/25 hover:bg-white/[0.05] hover:text-white/60 sm:flex transition-colors"
            title="Retry connection"
          >
            <RotateCcw className="h-3 w-3" />
            Retry
          </button>
        )}

        <button
          onClick={() => void handlePrivacyToggle()}
          title={privacyMode ? "Privacy mode ON — click to disable." : "Enable privacy mode — local Ollama only."}
          aria-pressed={privacyMode}
          className={`rounded-lg p-1.5 transition-colors ${
            privacyMode ? "text-amber-400 hover:bg-white/[0.05]" : "text-white/20 hover:bg-white/[0.05] hover:text-white/50"
          }`}
        >
          <Shield className="h-3.5 w-3.5" />
        </button>

        <button
          onClick={() => setShortcutsOpen(true)}
          className="rounded-lg p-1.5 text-white/20 hover:bg-white/[0.05] hover:text-white/50 transition-colors"
          title="Keyboard shortcuts (Ctrl+/)"
        >
          <Keyboard className="h-3.5 w-3.5" />
        </button>

        <div className="flex items-center gap-2 pl-1">
          <Activity className={`h-3.5 w-3.5 ${online ? "text-emerald-500" : isInitializing ? "text-amber-400" : "text-white/20"}`} />
          <span
            className={`hidden text-xs font-medium sm:inline ${
              online ? "text-emerald-500" : isInitializing ? "text-amber-400" : "text-white/25"
            }`}
          >
            {statusLabel()}
          </span>
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              online ? "bg-emerald-500 animate-pulse" : isInitializing || isFetching || retrying ? "animate-pulse bg-amber-400" : "bg-white/15"
            }`}
          />
        </div>
      </div>

      <ShortcutsModal
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </header>
  );
}
