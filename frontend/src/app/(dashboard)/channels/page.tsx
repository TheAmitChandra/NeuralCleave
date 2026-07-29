"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  Wifi,
  WifiOff,
  Send,
  Loader2,
  CheckCircle,
  AlertCircle,
  Plus,
  X,
} from "lucide-react";
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

interface AddChannelPayload {
  type: string;
  config: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Per-channel-type field definitions
// ---------------------------------------------------------------------------

type FieldDef = {
  key: string;
  label: string;
  placeholder: string;
  secret?: boolean;
};

const CHANNEL_TYPES: { value: string; label: string; fields: FieldDef[] }[] = [
  {
    value: "telegram",
    label: "Telegram",
    fields: [
      { key: "bot_token", label: "Bot Token", placeholder: "123456:ABC-DEF...", secret: true },
    ],
  },
  {
    value: "discord",
    label: "Discord",
    fields: [
      { key: "bot_token", label: "Bot Token", placeholder: "Your Discord bot token", secret: true },
      { key: "guild_id", label: "Guild ID (optional)", placeholder: "Leave blank for all guilds" },
    ],
  },
  {
    value: "slack",
    label: "Slack",
    fields: [
      { key: "bot_token", label: "Bot Token (xoxb-...)", placeholder: "xoxb-...", secret: true },
      { key: "signing_secret", label: "Signing Secret (optional)", placeholder: "Slack signing secret", secret: true },
    ],
  },
  {
    value: "email",
    label: "Email (SMTP)",
    fields: [
      { key: "smtp_host", label: "SMTP Host", placeholder: "smtp.gmail.com" },
      { key: "smtp_port", label: "SMTP Port", placeholder: "587" },
      { key: "username", label: "Username / Email", placeholder: "you@example.com" },
      { key: "password", label: "Password / App Password", placeholder: "••••••••", secret: true },
    ],
  },
  {
    value: "whatsapp",
    label: "WhatsApp (Twilio)",
    fields: [
      { key: "account_sid", label: "Twilio Account SID", placeholder: "ACxxxxxxxxxxxxxxxx" },
      { key: "auth_token", label: "Auth Token", placeholder: "••••••••", secret: true },
      { key: "from_number", label: "From Number", placeholder: "whatsapp:+14155238886" },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function extractErrorDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  return "Request failed";
}

// ---------------------------------------------------------------------------
// Add Channel Modal
// ---------------------------------------------------------------------------

function AddChannelModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [selectedType, setSelectedType] = useState(CHANNEL_TYPES[0].value);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  const typeDef = CHANNEL_TYPES.find((t) => t.value === selectedType)!;

  function handleTypeChange(value: string) {
    setSelectedType(value);
    setFields({});
    setError(null);
  }

  function setField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  const addMutation = useMutation({
    mutationFn: async (payload: AddChannelPayload) => {
      const { data } = await api.post("/channels/add", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["channels"] });
      onClose();
    },
    onError: (err) => {
      setError(extractErrorDetail(err));
    },
  });

  function submit() {
    setError(null);
    // Strip empty optional fields so they don't write empty strings to config
    const config: Record<string, string> = {};
    for (const f of typeDef.fields) {
      const v = (fields[f.key] ?? "").trim();
      if (v) config[f.key] = v;
    }
    // Require at least the first (non-optional) field
    const firstKey = typeDef.fields[0].key;
    if (!config[firstKey]) {
      setError(`${typeDef.fields[0].label} is required`);
      return;
    }
    addMutation.mutate({ type: selectedType, config });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-white/[0.08] bg-[#0f0f1c] shadow-2xl p-6">
        {/* Header */}
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Add Channel</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-white/30 hover:bg-white/[0.07] hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Channel type selector */}
        <div className="mb-4">
          <label className="mb-1.5 block text-xs font-medium text-white/50">
            Channel Type
          </label>
          <select
            value={selectedType}
            onChange={(e) => handleTypeChange(e.target.value)}
            className="rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm w-full cursor-pointer"
          >
            {CHANNEL_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {/* Dynamic fields */}
        <div className="space-y-3">
          {typeDef.fields.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs font-medium text-white/50">
                {f.label}
              </label>
              <input
                type={f.secret ? "password" : "text"}
                value={fields[f.key] ?? ""}
                onChange={(e) => setField(f.key, e.target.value)}
                placeholder={f.placeholder}
                autoComplete="off"
                className="rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm w-full"
              />
            </div>
          ))}
        </div>

        {/* Error */}
        {error && (
          <div className="mt-3 flex items-center gap-1.5 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl px-3 py-2 text-xs">
            <AlertCircle className="h-3.5 w-3.5 shrink-0" />
            {error}
          </div>
        )}

        {/* Note */}
        <p className="mt-4 text-xs text-white/[0.2]">
          Settings are written to <code className="text-white/30">~/.neuralcleave/config.toml</code>.
          Restart the gateway to connect.
        </p>

        {/* Actions */}
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="text-white/40 hover:bg-white/[0.05] hover:text-white/80 rounded-xl px-4 py-2 text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={addMutation.isPending}
            className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl px-4 py-2 text-sm font-medium transition-colors disabled:opacity-40"
          >
            {addMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Add Channel
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Channel Card
// ---------------------------------------------------------------------------

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
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03]">
      {/* Card header */}
      <div className="flex items-start justify-between p-5 border-b border-white/[0.06]">
        <div className="flex items-center gap-3">
          {channel.connected ? (
            <Wifi className="h-5 w-5 text-emerald-400" />
          ) : (
            <WifiOff className="h-5 w-5 text-white/[0.2]" />
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
            <p className="text-xs text-white/50 capitalize">{channel.type}</p>
          </div>
        </div>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            channel.connected
              ? "bg-emerald-500/15 text-emerald-400"
              : "bg-white/[0.05] text-white/30"
          }`}
        >
          {channel.connected ? "connected" : "not connected"}
        </span>
      </div>

      {/* Test message send */}
      <div className="p-5 space-y-2">
        <input
          type="text"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder="Target (chat/user/channel ID)…"
          className="rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm w-full"
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
            className="flex-1 rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm"
          />
          <button
            onClick={submit}
            disabled={sendMutation.isPending || !target.trim() || !text.trim()}
            className="flex items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl px-3 py-2 text-sm font-medium transition-colors disabled:opacity-40"
          >
            {sendMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Send
          </button>
        </div>

        {result && (
          <p
            className={`flex items-center gap-1.5 text-xs ${
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ChannelsPage() {
  const [showAddModal, setShowAddModal] = useState(false);

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
      {showAddModal && <AddChannelModal onClose={() => setShowAddModal(false)} />}

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Channels</h1>
          <p className="mt-1 text-sm text-white/50">
            Connected messaging platforms and integrations
          </p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex shrink-0 items-center gap-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-xl px-4 py-2 text-sm font-medium transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Channel
        </button>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-36 bg-white/[0.06] animate-pulse rounded-xl"
            />
          ))}
        </div>
      ) : isError ? (
        <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded-xl p-6 text-sm">
          Could not reach the gateway. Make sure{" "}
          <code className="rounded bg-rose-500/10 px-1">neuralcleave start</code> is
          running.
        </div>
      ) : channels.length === 0 ? (
        <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] p-8 text-center">
          <WifiOff className="mx-auto mb-3 h-8 w-8 text-white/[0.2]" />
          <p className="text-sm text-white/50">No channels configured yet.</p>
          <p className="mt-1 text-xs text-white/[0.2]">
            Click{" "}
            <button
              onClick={() => setShowAddModal(true)}
              className="text-violet-400 hover:text-violet-300 underline"
            >
              Add Channel
            </button>{" "}
            to connect your first messaging platform.
          </p>
        </div>
      ) : (
        <>
          {connected.length > 0 && (
            <section>
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-white/[0.25]">
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
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-white/[0.25]">
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
