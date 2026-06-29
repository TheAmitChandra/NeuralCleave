"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import { Wifi, WifiOff, Send, Loader2, CheckCircle, AlertCircle } from "lucide-react";
import api from "@/lib/api";

interface Channel {
  channel_id: string;
  type: string;
  connected: boolean;
  unread: number;
}

interface ChannelsResponse {
  channels: Channel[];
  count: number;
}

interface SendResponse {
  sent: boolean;
  message_id: string;
}

function extractErrorDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return "Request failed";
}

function ChannelCard({ channel }: { channel: Channel }) {
  const [target, setTarget] = useState("");
  const [text, setText] = useState("");
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);
  const queryClient = useQueryClient();

  const sendMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<SendResponse>(
        `/channels/${channel.channel_id}/send`,
        { target, text }
      );
      return data;
    },
    onSuccess: (data) => {
      setResult({ ok: true, message: `Sent (message_id: ${data.message_id})` });
      setText("");
      setTimeout(() => setResult(null), 4000);
    },
    onError: (err) => {
      setResult({ ok: false, message: extractErrorDetail(err) });
      setTimeout(() => setResult(null), 4000);
    },
  });

  const markReadMutation = useMutation({
    mutationFn: () => api.post(`/channels/${channel.channel_id}/read`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["channels"] }),
  });

  // Viewing this card on the Channels page is the closest thing this app
  // has to "reading" a channel — there's no per-channel message thread UI
  // yet, just the connection-status overview. Marks read once per mount
  // rather than every time `channel.unread` ticks up from new traffic.
  useEffect(() => {
    if (channel.unread > 0 && !markReadMutation.isPending) {
      markReadMutation.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel.channel_id]);

  function submit() {
    if (target.trim() && text.trim()) sendMutation.mutate();
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          {channel.connected ? (
            <Wifi className="h-5 w-5 text-emerald-400" />
          ) : (
            <WifiOff className="h-5 w-5 text-slate-500" />
          )}
          <div>
            <h3 className="flex items-center gap-2 font-semibold text-white">
              {channel.channel_id}
              {channel.unread > 0 && (
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-xs font-bold text-white">
                  {channel.unread}
                </span>
              )}
            </h3>
            <p className="text-xs text-slate-500 capitalize">{channel.type}</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            channel.connected
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-slate-700 text-slate-500"
          }`}
        >
          {channel.connected ? "connected" : "not connected"}
        </span>
      </div>

      {/* Test message send */}
      <div className="mt-4 space-y-2">
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Target (chat/user/channel ID)…"
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
        />
        <div className="flex gap-2">
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Send a test message…"
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-white outline-none focus:border-indigo-500"
          />
          <button
            onClick={submit}
            disabled={sendMutation.isPending || !target.trim() || !text.trim()}
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
      </div>

      {result && (
        <p
          className={`mt-2 flex items-center gap-1.5 text-xs ${
            result.ok ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          {result.ok ? (
            <CheckCircle className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          )}
          {result.message}
        </p>
      )}
    </div>
  );
}

export default function ChannelsPage() {
  const { data, isLoading, isError } = useQuery<ChannelsResponse>({
    queryKey: ["channels"],
    queryFn: async () => {
      const { data } = await api.get<ChannelsResponse>("/channels");
      return data;
    },
    refetchInterval: 30_000,
  });

  const channels = data?.channels ?? [];
  const connected = channels.filter((c) => c.connected);
  const notConnected = channels.filter((c) => !c.connected);

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
      ) : channels.length === 0 ? (
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
          {connected.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Connected ({connected.length})
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {connected.map((ch) => (
                  <ChannelCard key={ch.channel_id} channel={ch} />
                ))}
              </div>
            </section>
          )}
          {notConnected.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Not Connected ({notConnected.length})
              </h2>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {notConnected.map((ch) => (
                  <ChannelCard key={ch.channel_id} channel={ch} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
