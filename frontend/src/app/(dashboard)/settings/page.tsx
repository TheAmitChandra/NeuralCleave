"use client";

import { useState, useEffect } from "react";
import { Settings, Save, CheckCircle, AlertCircle, Monitor, Loader2, Bell } from "lucide-react";
import apiClient from "@/lib/api";
import { isTauri } from "@tauri-apps/api/core";
import { isEnabled as isAutostartEnabled, enable as enableAutostart, disable as disableAutostart } from "@tauri-apps/plugin-autostart";
import { sendDesktopNotification } from "@/lib/notifications";

interface SectionValues {
  [key: string]: string;
}

const DEFAULTS: Record<string, SectionValues> = {
  api: {
    "Backend API URL": "http://localhost:7432",
    "WebSocket URL": "ws://localhost:7432/ws",
  },
  llm: {
    "Gemini API Key": "",
    "DeepSeek API Key": "",
    "Anthropic API Key": "",
    "OpenAI API Key": "",
    "Ollama Base URL": "http://localhost:11434",
  },
  appearance: {
    Timezone: "UTC",
  },
};

const STORAGE_KEY = "cortexflow_settings";

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
    <div className="rounded-xl border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
        <div className="flex items-center gap-2">
          <Settings className="h-4 w-4 text-slate-400" />
          <h2 className="text-sm font-semibold text-white">{title}</h2>
        </div>
        <button
          onClick={() => onSave(sectionKey)}
          className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-white ${
            error === sectionKey
              ? "bg-rose-700 hover:bg-rose-600"
              : "bg-indigo-600 hover:bg-indigo-500"
          }`}
        >
          {saved === sectionKey ? (
            <>
              <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
              Saved
            </>
          ) : error === sectionKey ? (
            <>
              <AlertCircle className="h-3.5 w-3.5 text-rose-300" />
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
      <div className="divide-y divide-slate-800">
        {Object.entries(values).map(([label, value]) => (
          <div
            key={label}
            className="flex flex-col gap-2 px-6 py-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <label className="text-sm text-slate-300">{label}</label>
            <input
              type={types[label] ?? "text"}
              value={value}
              onChange={(e) => onChange(sectionKey, label, e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 sm:w-72"
              placeholder={types[label] === "password" ? "Enter API key…" : undefined}
            />
          </div>
        ))}
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
      "CortexFlow-AI",
      "This is a test notification."
    );
    setNotifyStatus(sent ? "sent" : "denied");
    setTimeout(() => setNotifyStatus((prev) => (prev === "sent" ? "idle" : prev)), 2000);
  }

  if (loading || !inTauri) return null;

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900">
      <div className="flex items-center gap-2 border-b border-slate-800 px-6 py-4">
        <Monitor className="h-4 w-4 text-slate-400" />
        <h2 className="text-sm font-semibold text-white">Desktop</h2>
      </div>
      <div className="divide-y divide-slate-800">
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm text-slate-300">Launch on login</p>
            <p className="text-xs text-slate-500">
              Start CortexFlow-AI automatically when you log in
            </p>
          </div>
          <button
            onClick={handleToggle}
            disabled={toggling}
            role="switch"
            aria-checked={enabled}
            aria-label="Launch on login"
            className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
              enabled ? "bg-indigo-600" : "bg-slate-700"
            } disabled:opacity-50`}
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

        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm text-slate-300">Notifications</p>
            <p className="text-xs text-slate-500">
              Send a native notification to confirm the OS permission is granted
            </p>
          </div>
          <button
            onClick={handleSendTestNotification}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
          >
            {notifyStatus === "sent" ? (
              <>
                <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
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

    if (section === "llm") {
      const payload: Record<string, string> = {};
      if (values.llm["Gemini API Key"]) payload.gemini_api_key = values.llm["Gemini API Key"];
      if (values.llm["DeepSeek API Key"]) payload.deepseek_api_key = values.llm["DeepSeek API Key"];
      if (values.llm["Anthropic API Key"]) payload.anthropic_api_key = values.llm["Anthropic API Key"];
      if (values.llm["OpenAI API Key"]) payload.openai_api_key = values.llm["OpenAI API Key"];
      if (values.llm["Ollama Base URL"]) payload.ollama_base_url = values.llm["Ollama Base URL"];
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
        <p className="mt-1 text-sm text-slate-400">
          Configure CortexFlow-AI connections and preferences
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
        }}
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

