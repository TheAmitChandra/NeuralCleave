"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, WifiOff } from "lucide-react";

interface GatewayStatus {
  status: string;
  runtime_available?: boolean;
}

type ToastKind = "online" | "offline";

interface ToastState {
  id: number;
  kind: ToastKind;
}

/** Auto-dismiss delay in ms */
const DISMISS_MS = 3_500;

/**
 * Listens to the "gateway-status" React Query cache and surfaces a brief
 * toast whenever the gateway transitions between online and offline states.
 * Mounts invisibly — renders nothing until a transition is detected.
 */
export function GatewayToast() {
  const prevOnlineRef = useRef<boolean | null>(null);
  const counterRef = useRef(0);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [visible, setVisible] = useState(false);

  const { data, isError } = useQuery<GatewayStatus>({
    queryKey: ["gateway-status"],
    // This component shares the existing query — it does NOT trigger a new
    // network request. enabled:false keeps it from running as a standalone
    // fetch while still receiving cache updates from Topbar's query.
    enabled: false,
  });

  // Mirror the Topbar definition: require runtime_available=true so the
  // "NeuralCleave is ready" toast fires after the AI runtime finishes init,
  // not the moment the status endpoint first responds (which now happens
  // before AgentRuntime.start() completes).
  const online = !isError && data?.status === "ok" && data.runtime_available === true;

  useEffect(() => {
    if (prevOnlineRef.current === null) {
      // First render — record baseline without showing anything.
      prevOnlineRef.current = online;
      return;
    }
    if (prevOnlineRef.current === online) return;

    prevOnlineRef.current = online;
    const id = ++counterRef.current;
    setToast({ id, kind: online ? "online" : "offline" });
    setVisible(true);

    const hideTimer = setTimeout(() => setVisible(false), DISMISS_MS);
    const removeTimer = setTimeout(() => setToast(null), DISMISS_MS + 300);
    return () => {
      clearTimeout(hideTimer);
      clearTimeout(removeTimer);
    };
  }, [online]);

  if (!toast) return null;

  const isOnline = toast.kind === "online";

  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className={`fixed bottom-6 left-1/2 z-50 -translate-x-1/2 transition-all duration-300 ${
        visible ? "translate-y-0 opacity-100" : "translate-y-4 opacity-0"
      }`}
    >
      <div
        className={`flex items-center gap-2.5 rounded-xl border px-4 py-3 shadow-xl backdrop-blur-sm ${
          isOnline
            ? "border-emerald-700/50 bg-emerald-950/90 text-emerald-300"
            : "border-rose-700/50 bg-rose-950/90 text-rose-300"
        }`}
      >
        {isOnline ? (
          <CheckCircle2 className="h-4 w-4 shrink-0" />
        ) : (
          <WifiOff className="h-4 w-4 shrink-0" />
        )}
        <span className="text-sm font-medium">
          {isOnline ? "NeuralCleave is ready" : "Gateway connection lost"}
        </span>
      </div>
    </div>
  );
}
