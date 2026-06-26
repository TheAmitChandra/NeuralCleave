"use client";

import { useState, useEffect } from "react";
import { Settings, Save, CheckCircle } from "lucide-react";

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
}: {
  title: string;
  sectionKey: string;
  values: SectionValues;
  types: Record<string, string>;
  onChange: (section: string, key: string, val: string) => void;
  onSave: (section: string) => void;
  saved: string | null;
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
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
        >
          {saved === sectionKey ? (
            <>
              <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
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

export default function SettingsPage() {
  const [values, setValues] = useState(DEFAULTS);
  const [savedSection, setSavedSection] = useState<string | null>(null);

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
    setSavedSection(section);
    setTimeout(() => setSavedSection((prev) => (prev === section ? null : prev)), 2000);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Configure CortexFlow connections and preferences
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
      />

      <Section
        title="LLM Providers"
        sectionKey="llm"
        values={values.llm}
        types={{
          "Gemini API Key": "password",
          "DeepSeek API Key": "password",
          "Ollama Base URL": "text",
        }}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
      />

      <Section
        title="Appearance"
        sectionKey="appearance"
        values={values.appearance}
        types={{ Timezone: "text" }}
        onChange={handleChange}
        onSave={handleSave}
        saved={savedSection}
      />
    </div>
  );
}

