"use client";

import { useState, useEffect } from "react";
import { Settings, Save, CheckCircle, AlertCircle, Monitor, Loader2, Bell, Mic, Cpu } from "lucide-react";
import apiClient, { getVoiceDevices, type VoiceDevice } from "@/lib/api";
import { isTauri } from "@tauri-apps/api/core";
import { isEnabled as isAutostartEnabled, enable as enableAutostart, disable as disableAutostart } from "@tauri-apps/plugin-autostart";
import { sendDesktopNotification } from "@/lib/notifications";

interface SectionValues {
  [key: string]: string;
}

const DEFAULTS: Record<string, SectionValues> = {
  api: {
    "Backend API URL": "http://127.0.0.1:7432",
    "WebSocket URL": "ws://127.0.0.1:7432/ws",
  },
  llm: {
    "Gemini API Key": "",
    "DeepSeek API Key": "",
    "Anthropic API Key": "",
    "OpenAI API Key": "",
    "Ollama Base URL": "http://localhost:11434",
    "Web Search": "false",
  },
  model: {
    "Active Provider": "gemini",
    "Temperature": "0.7",
    "Max Tokens": "4096",
  },
  voice: {
    "STT Model": "base",
    "STT Device": "cpu",
    "TTS Engine": "pyttsx3",
    "ElevenLabs API Key": "",
    "ElevenLabs Voice ID": "",
    "Language": "en",
    "Wake Word": "",
    "Input Device": "",
    "Output Device": "",
  },
  appearance: {
    Timezone: "UTC",
  },
};

const STORAGE_KEY = "NeuralCleave_settings";

function loadSettings(): typeof DEFAULTS {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    return { ...DEFAULTS, ...JSON.parse(raw) };
  } catch {
    return DEFAULTS;
  }
}

function Section({
  title,
  sectionKey,
  values,
  types,
  onChange,
  onSave,
  saved,
  error,
}: {
  title: string;
  sectionKey: string;
  values: SectionValues;
  types: Record<string, string>;
  onChange: (section: string, key: string, val: string) => void;
  onSave: (section: string) => void;
  saved: string | null;
  error: string | null;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">{title}</h2>
        </div>
        <button
          onClick={() => onSave(sectionKey)}
          className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-white transition-colors ${
            error === sectionKey
              ? "bg-rose-600 hover:bg-rose-500"
              : "bg-violet-600 hover:bg-violet-500"
          }`}
        >
          {saved === sectionKey ? (
            <>
              <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
              Saved
            </>
          ) : error === sectionKey ? (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-rose-400" />
              Failed — gateway unreachable
            </>
          ) : (
            <>
              <Save className="h-3.5 w-3.5" />
              Save
            </>
          )}
        </button>
      </div>
      <div className="divide-y divide-white/[0.05]">
        {Object.entries(values).map(([label, value]) => (
          <div
            key={label}
            className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4"
          >
            <label className="text-sm font-medium text-white/75">{label}</label>
            {types[label] === "toggle" ? (
              <button
                role="switch"
                aria-checked={value === "true"}
                onClick={() => onChange(sectionKey, label, value === "true" ? "false" : "true")}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
                  value === "true" ? "bg-violet-600" : "bg-white/[0.1]"
                }`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                    value === "true" ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            ) : (
              <input
                type={types[label] ?? "text"}
                value={value}
                onChange={(e) => onChange(sectionKey, label, e.target.value)}
                className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-72"
                placeholder={types[label] === "password" ? "Enter API key…" : undefined}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model selector section
// ---------------------------------------------------------------------------

const PROVIDERS = ["gemini", "anthropic", "openai", "deepseek", "ollama"] as const;

function ModelSection({
  values,
  onChange,
  onSave,
  saved,
  error,
}: {
  values: SectionValues;
  onChange: (section: string, key: string, val: string) => void;
  onSave: (section: string) => void;
  saved: string | null;
  error: string | null;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">Model</h2>
        </div>
        <button
          onClick={() => onSave("model")}
          className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-white transition-colors ${
            error === "model"
              ? "bg-rose-600 hover:bg-rose-500"
              : "bg-violet-600 hover:bg-violet-500"
          }`}
        >
          {saved === "model" ? (
            <>
              <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
              Saved
            </>
          ) : (
            <>
              <Save className="h-3.5 w-3.5" />
              Save
            </>
          )}
        </button>
      </div>
      <div className="divide-y divide-white/[0.05]">
        {/* Active provider — dropdown */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <label className="text-sm font-medium text-white/75">Active Provider</label>
          <select
            value={values["Active Provider"] ?? "gemini"}
            onChange={(e) => onChange("model", "Active Provider", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-48"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Temperature */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">Temperature</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Controls response randomness (0 = focused, 1 = creative)</p>
          </div>
          <div className="flex w-full items-center gap-3 sm:w-48">
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={values["Temperature"] ?? "0.7"}
              onChange={(e) => onChange("model", "Temperature", e.target.value)}
              className="flex-1 accent-violet-500"
            />
            <span className="w-10 text-right text-sm text-white/75">
              {parseFloat(values["Temperature"] ?? "0.7").toFixed(2)}
            </span>
          </div>
        </div>

        {/* Max tokens */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <label className="text-sm font-medium text-white/75">Max Tokens</label>
          <input
            type="number"
            min={256}
            max={32768}
            step={256}
            value={values["Max Tokens"] ?? "4096"}
            onChange={(e) => onChange("model", "Max Tokens", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-48"
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Voice settings section
// ---------------------------------------------------------------------------

const STT_MODELS = ["tiny", "base", "small", "medium", "large"] as const;
const TTS_ENGINES = ["pyttsx3", "elevenlabs", "kokoro"] as const;

function VoiceSection({
  values,
  onChange,
  onSave,
  saved,
  error,
}: {
  values: SectionValues;
  onChange: (section: string, key: string, val: string) => void;
  onSave: (section: string) => void;
  saved: string | null;
  error: string | null;
}) {
  const [inputDevices, setInputDevices] = useState<VoiceDevice[]>([]);
  const [outputDevices, setOutputDevices] = useState<VoiceDevice[]>([]);

  useEffect(() => {
    getVoiceDevices().then((data) => {
      setInputDevices(data.input);
      setOutputDevices(data.output);
      if (data.active.input_device) onChange("voice", "Input Device", data.active.input_device);
      if (data.active.output_device) onChange("voice", "Output Device", data.active.output_device);
    }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-6 py-4">
        <div className="flex items-center gap-2">
          <Mic className="h-4 w-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">Voice</h2>
        </div>
        <button
          onClick={() => onSave("voice")}
          className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium text-white transition-colors ${
            error === "voice"
              ? "bg-rose-600 hover:bg-rose-500"
              : "bg-violet-600 hover:bg-violet-500"
          }`}
        >
          {saved === "voice" ? (
            <>
              <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
              Saved
            </>
          ) : (
            <>
              <Save className="h-3.5 w-3.5" />
              Save
            </>
          )}
        </button>
      </div>
      <div className="divide-y divide-white/[0.05]">
        {/* STT model */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">STT Model</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Whisper model size (larger = more accurate but slower)</p>
          </div>
          <select
            value={values["STT Model"] ?? "base"}
            onChange={(e) => onChange("voice", "STT Model", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-48"
          >
            {STT_MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* STT device */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">STT Device</label>
            <p className="text-xs text-white/[0.3] mt-0.5">cpu or cuda (requires NVIDIA GPU + CUDA toolkit)</p>
          </div>
          <select
            value={values["STT Device"] ?? "cpu"}
            onChange={(e) => onChange("voice", "STT Device", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-48"
          >
            <option value="cpu">CPU</option>
            <option value="cuda">CUDA (GPU)</option>
          </select>
        </div>

        {/* TTS engine */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">TTS Engine</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Text-to-speech backend</p>
          </div>
          <select
            value={values["TTS Engine"] ?? "pyttsx3"}
            onChange={(e) => onChange("voice", "TTS Engine", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-48"
          >
            {TTS_ENGINES.map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </select>
        </div>

        {/* ElevenLabs fields — shown for all but only relevant when TTS = elevenlabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <label className="text-sm font-medium text-white/75">ElevenLabs API Key</label>
          <input
            type="password"
            value={values["ElevenLabs API Key"] ?? ""}
            onChange={(e) => onChange("voice", "ElevenLabs API Key", e.target.value)}
            placeholder="Enter ElevenLabs key…"
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-72"
          />
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <label className="text-sm font-medium text-white/75">ElevenLabs Voice ID</label>
          <input
            type="text"
            value={values["ElevenLabs Voice ID"] ?? ""}
            onChange={(e) => onChange("voice", "ElevenLabs Voice ID", e.target.value)}
            placeholder="Voice ID from ElevenLabs dashboard…"
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-72"
          />
        </div>

        {/* Language + wake word */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">Language</label>
            <p className="text-xs text-white/[0.3] mt-0.5">BCP-47 language code for STT (e.g. en, es, fr)</p>
          </div>
          <input
            type="text"
            value={values["Language"] ?? "en"}
            onChange={(e) => onChange("voice", "Language", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-48"
          />
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">Wake Word</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Trigger phrase for hands-free activation (optional)</p>
          </div>
          <input
            type="text"
            value={values["Wake Word"] ?? ""}
            onChange={(e) => onChange("voice", "Wake Word", e.target.value)}
            placeholder="e.g. hey neural"
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm sm:w-72"
          />
        </div>

        {/* Input device — microphone selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">Input Device</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Microphone used for STT and push-to-talk</p>
          </div>
          <select
            value={values["Input Device"] ?? ""}
            onChange={(e) => onChange("voice", "Input Device", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-72"
          >
            <option value="">System default</option>
            {inputDevices.map((d) => (
              <option key={d.index} value={d.name}>{d.name}</option>
            ))}
          </select>
        </div>

        {/* Output device — speaker/headphone selector */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <label className="text-sm font-medium text-white/75">Output Device</label>
            <p className="text-xs text-white/[0.3] mt-0.5">Speaker or headphones used for TTS playback</p>
          </div>
          <select
            value={values["Output Device"] ?? ""}
            onChange={(e) => onChange("voice", "Output Device", e.target.value)}
            className="w-full rounded-xl bg-white/[0.05] border border-white/[0.08] text-white/85 placeholder:text-white/[0.2] focus:border-violet-500/50 outline-none px-3 py-2 text-sm cursor-pointer sm:w-72"
          >
            <option value="">System default</option>
            {outputDevices.map((d) => (
              <option key={d.index} value={d.name}>{d.name}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

/**
 * Desktop-only settings (currently just autostart-on-login). Hidden
 * entirely outside the Tauri shell — isTauri() is false in a regular
 * browser tab, and @tauri-apps/plugin-autostart has no OS to talk to
 * there anyway.
 */
function DesktopSection() {
  const [inTauri, setInTauri] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [notifyStatus, setNotifyStatus] = useState<"idle" | "sent" | "denied">("idle");

  useEffect(() => {
    let mounted = true;
    (async () => {
      const tauri = isTauri();
      if (!mounted) return;
      setInTauri(tauri);
      if (tauri) {
        const current = await isAutostartEnabled();
        if (mounted) setEnabled(current);
      }
      if (mounted) setLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  async function handleToggle() {
    setToggling(true);
    try {
      if (enabled) {
        await disableAutostart();
        setEnabled(false);
      } else {
        await enableAutostart();
        setEnabled(true);
      }
    } finally {
      setToggling(false);
    }
  }

  async function handleSendTestNotification() {
    const sent = await sendDesktopNotification(
      "NeuralCleave",
      "This is a test notification."
    );
    setNotifyStatus(sent ? "sent" : "denied");
    setTimeout(() => setNotifyStatus((prev) => (prev === "sent" ? "idle" : prev)), 2000);
  }

  if (loading || !inTauri) return null;

  return (
    <div className="rounded-2xl border border-white/[0.06] bg-white/[0.03] overflow-hidden">
      <div className="flex items-center gap-2 border-b border-white/[0.06] px-6 py-4">
        <Monitor className="h-4 w-4 text-violet-400" />
        <h2 className="text-sm font-semibold text-white">Desktop</h2>
      </div>
      <div className="divide-y divide-white/[0.05]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <p className="text-sm font-medium text-white/75">Launch on login</p>
            <p className="text-xs text-white/[0.3] mt-0.5">
              Start NeuralCleave automatically when you log in
            </p>
          </div>
          <button
            onClick={handleToggle}
            disabled={toggling}
            role="switch"
            aria-checked={enabled}
            aria-label="Launch on login"
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
              enabled ? "bg-violet-600" : "bg-white/[0.1]"
            } disabled:opacity-40 disabled:cursor-not-allowed`}
          >
            {toggling ? (
              <Loader2 className="absolute left-1/2 top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 animate-spin text-white" />
            ) : (
              <span
                className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                  enabled ? "translate-x-5" : "translate-x-0.5"
                }`}
              />
            )}
          </button>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-6 py-4">
          <div>
            <p className="text-sm font-medium text-white/75">Notifications</p>
            <p className="text-xs text-white/[0.3] mt-0.5">
              Send a native notification to confirm the OS permission is granted
            </p>
          </div>
          <button
            onClick={handleSendTestNotification}
            className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 transition-colors"
          >
            {notifyStatus === "sent" ? (
              <>
                <CheckCircle className="h-3.5 w-3.5 text-emerald-400" />
                Sent
              </>
            ) : notifyStatus === "denied" ? (
              "Permission denied"
            ) : (
              <>
                <Bell className="h-3.5 w-3.5" />
                Send test notification
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [values, setValues] = useState(DEFAULTS);
  const [savedSection, setSavedSection] = useState<string | null>(null);
  const [errorSection, setErrorSection] = useState<string | null>(null);

  useEffect(() => {
    setValues(loadSettings());
  }, []);

  useEffect(() => {
    apiClient.get("/voice/config").then((res) => {
      const d = res.data as Record<string, unknown>;
      setValues((prev) => ({
        ...prev,
        voice: {
          ...prev.voice,
          ...(d.tts_engine ? { "TTS Engine": String(d.tts_engine) } : {}),
          ...(d.language ? { "Language": String(d.language) } : {}),
          ...(d.elevenlabs_voice_id ? { "ElevenLabs Voice ID": String(d.elevenlabs_voice_id) } : {}),
        },
      }));
    }).catch(() => {
      // gateway offline — localStorage values stand
    });
  }, []);

  function handleChange(section: string, key: string, val: string) {
    setValues((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: val },
    }));
  }

  function handleSave(section: string) {
    const current = loadSettings();
    const updated = { ...current, [section]: values[section] };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));

    if (section === "model") {
      const payload: Record<string, unknown> = {
        provider: values.model["Active Provider"] || null,
      };
      apiClient
        .post("/settings/model", payload)
        .then(() => {
          setErrorSection(null);
          setSavedSection(section);
          setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
        })
        .catch(() => {
          // Swallow gateway errors — model preferences are still saved locally
          setSavedSection(section);
          setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
        });
      return;
    }

    if (section === "voice") {
      // tts_engine, elevenlabs_*, language can be applied live via PATCH.
      // STT model/device and wake_word require a gateway restart — localStorage only.
      const payload: Record<string, string> = {};
      if (values.voice["TTS Engine"]) payload.tts_engine = values.voice["TTS Engine"];
      if (values.voice["ElevenLabs API Key"]) payload.elevenlabs_api_key = values.voice["ElevenLabs API Key"];
      if (values.voice["ElevenLabs Voice ID"]) payload.elevenlabs_voice_id = values.voice["ElevenLabs Voice ID"];
      if (values.voice["Language"]) payload.language = values.voice["Language"];
      if (values.voice["Input Device"]) payload.input_device = values.voice["Input Device"];
      if (values.voice["Output Device"]) payload.output_device = values.voice["Output Device"];
      apiClient
        .patch("/voice/config", payload)
        .then(() => {
          setErrorSection(null);
          setSavedSection(section);
          setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
        })
        .catch(() => {
          setErrorSection(section);
          setTimeout(() => setErrorSection((prev) => (prev === section ? null : prev)), 3000);
        });
      return;
    }

    if (section === "llm") {
      const payload: Record<string, string | boolean> = {};
      if (values.llm["Gemini API Key"]) payload.gemini_api_key = values.llm["Gemini API Key"];
      if (values.llm["DeepSeek API Key"]) payload.deepseek_api_key = values.llm["DeepSeek API Key"];
      if (values.llm["Anthropic API Key"]) payload.anthropic_api_key = values.llm["Anthropic API Key"];
      if (values.llm["OpenAI API Key"]) payload.openai_api_key = values.llm["OpenAI API Key"];
      if (values.llm["Ollama Base URL"]) payload.ollama_base_url = values.llm["Ollama Base URL"];
      payload.web_search_enabled = values.llm["Web Search"] === "true";
      if (Object.keys(payload).length > 0) {
        // Defer "Saved" until the gateway actually confirms — show "Failed" on error.
        apiClient
          .post("/settings/llm", payload)
          .then(() => {
            setErrorSection(null);
            setSavedSection(section);
            setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
          })
          .catch(() => {
            setErrorSection(section);
            setTimeout(() => setErrorSection((prev) => (prev === section ? null : prev)), 3000);
          });
        return;
      }
    }

    // For non-API sections (api, appearance) or LLM with no keys to push,
    // the save is localStorage-only — show Saved immediately.
    setSavedSection(section);
    setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="text-sm text-white/40 mt-1">
          Configure NeuralCleave connections and preferences
        </p>
      </div>

      <Section
        title="API Configuration"
        sectionKey="api"
        values={values.api}
        types={{ "Backend API URL": "text", "WebSocket URL": "text" }}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
        error={errorSection}
      />

      <Section
        title="LLM Providers"
        sectionKey="llm"
        values={values.llm}
        types={{
          "Gemini API Key": "password",
          "DeepSeek API Key": "password",
          "Anthropic API Key": "password",
          "OpenAI API Key": "password",
          "Ollama Base URL": "text",
          "Web Search": "toggle",
        }}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
        error={errorSection}
      />

      <ModelSection
        values={values.model}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
        error={errorSection}
      />

      <VoiceSection
        values={values.voice}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
        error={errorSection}
      />

      <Section
        title="Appearance"
        sectionKey="appearance"
        values={values.appearance}
        types={{ Timezone: "text" }}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
        error={errorSection}
      />

      <DesktopSection />
    </div>
  );
}
