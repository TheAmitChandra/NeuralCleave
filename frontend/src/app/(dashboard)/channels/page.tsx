"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Wifi, WifiOff, Send, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import api from "@/lib/api";

interface Channel {
  id: string;
  name: string;
  type: string;
  enabled: boolean;
  status?: string; // "connected" | "disconnected" | "error" | …
  last_message_at?: string | null;
  error?: string | null;
}

interface SendResult {
  ok: boolean;
  error?: string;
}

function ChannelCard({ channel }: { channel: Channel }) {
  const [testMsg, setTestMsg] = useState("");
  const [result, setResult] = useState<SendResult | null>(null);

  const sendMutation = useMutation({
    mutationFn: async (message: string) => {
      const { data } = await api.post<SendResult>(
        `/channels/${channel.id}/send`,
        { message }
      );
      return data;
    },
    onSuccess: (data) => {
      setResult(data);
      if (data.ok) setTestMsg("");
      setTimeout(() => setResult(null), 4000);
    },
    onError: () => {
      setResult({ ok: false, error: "Request failed" });
      setTimeout(() => setResult(null), 4000);
    },
  });

  const isEnabled = channel.enabled;
  const statusText = channel.status ?? (isEnabled ? "enabled" : "disabled");

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {isEnabled ? (
            <Wifi className="h-5 w-5 text-emerald-400" />
          ) : (
            <WifiOff className="h-5 w-5 text-slate-500" />
          )}
          <div>
            <h3 className="font-semibold capitalize text-white">{channel.name}</h3>
            <p className="text-xs text-slate-500 capitalize">{channel.type}</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            isEnabled
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-slate-700 text-slate-500"
          }`}
        >
          {statusText}
        </span>
      </div>

      {channel.error && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-rose-400">
          <AlertCircle className="h-3.5 w-3.5" />
          {channel.error}
        </p>
      )}

      {channel.last_message_at && (
        <p className="mt-2 text-xs text-slate-600">
          Last message:{" "}
          {new Date(channel.last_message_at).toLocaleString()}
        </p>
      )}

      {/* Test message send */}
      {isEnabled && (
        <div className="mt-4 flex gap-2">
          <input
            type="text"
            value={testMsg}
            onChange={(e) => setTestMsg(e.target.value)}
            placeholder="Send a test message…"
            onKeyDown={(e) => {
              if (e.key === "Enter" && testMsg.trim())
                sendMutation.mutate(testMsg.trim());
            }}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
          />
          <button
            onClick={() => {
              if (testMsg.trim()) sendMutation.mutate(testMsg.trim());
            }}
            disabled={sendMutation.isPending || !testMsg.trim()}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            {sendMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Send
          </button>
        </div>
      )}

      {result && (
        <p
          className={`mt-2 flex items-center gap-1.5 text-xs ${
            result.ok ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {result.ok ? (
            <CheckCircle className="h-3.5 w-3.5" />
          ) : (
            <AlertCircle className="h-3.5 w-3.5" />
          )}
          {result.ok ? "Sent!" : result.error ?? "Failed"}
        </p>
      )}
    </div>
  );
}

export default function ChannelsPage() {
  const { data: channels, isLoading, isError } = useQuery<Channel[]>({
    queryKey: ["channels"],
    queryFn: async () => {
      const { data } = await api.get<Channel[]>("/channels");
      return data;
    },
    refetchInterval: 30_000,
  });

  const enabled = channels?.filter((c) => c.enabled) ?? [];
  const disabled = channels?.filter((c) => !c.enabled) ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Channels</h1>
        <p className="mt-1 text-sm text-slate-400">
          Connected messaging platforms — add or remove via{" "}
          <code className="rounded bg-slate-800 px-1 py-0.5 text-xs">
            cortex channels add
          </code>
        </p>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-36 animate-pulse rounded-xl border border-slate-800 bg-slate-900"
            />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-rose-800 bg-rose-900/20 p-6 text-sm text-rose-300">
          Could not reach the gateway. Make sure{" "}
          <code className="rounded bg-rose-800/40 px-1">cortex start</code> is
          running.
        </div>
      ) : channels && channels.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center">
          <WifiOff className="mx-auto mb-3 h-8 w-8 text-slate-600" />
          <p className="text-sm text-slate-400">No channels configured yet.</p>
          <p className="mt-1 text-xs text-slate-600">
            Run{" "}
            <code className="rounded bg-slate-800 px-1 py-0.5">
              cortex channels add telegram
            </code>{" "}
            to add your first channel.
          </p>
        </div>
      ) : (
        <>
          {enabled.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Enabled ({enabled.length})
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {enabled.map((ch) => (
                  <ChannelCard key={ch.id} channel={ch} />
                ))}
              </div>
            </section>
          )}
          {disabled.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Disabled ({disabled.length})
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {disabled.map((ch) => (
                  <ChannelCard key={ch.id} channel={ch} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
