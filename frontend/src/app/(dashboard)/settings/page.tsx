import { Settings } from "lucide-react";

const SECTIONS = [
  {
    title: "API Configuration",
    fields: [
      { label: "Backend API URL", value: "http://localhost:8000", type: "text" },
      { label: "WebSocket URL", value: "ws://localhost:8000/ws", type: "text" },
    ],
  },
  {
    title: "LLM Providers",
    fields: [
      { label: "Gemini API Key", value: "••••••••••••••••", type: "password" },
      { label: "DeepSeek API Key", value: "••••••••••••••••", type: "password" },
      { label: "Ollama Base URL", value: "http://localhost:11434", type: "text" },
    ],
  },
  {
    title: "Appearance",
    fields: [
      { label: "Theme", value: "Dark", type: "text" },
      { label: "Timezone", value: "UTC", type: "text" },
    ],
  },
];

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Configure CortexFlow connections and preferences
        </p>
      </div>

      <div className="space-y-6">
        {SECTIONS.map(({ title, fields }) => (
          <div
            key={title}
            className="rounded-xl border border-slate-800 bg-slate-900"
          >
            <div className="flex items-center gap-2 border-b border-slate-800 px-6 py-4">
              <Settings className="h-4 w-4 text-slate-400" />
              <h2 className="text-sm font-semibold text-white">{title}</h2>
            </div>
            <div className="divide-y divide-slate-800">
              {fields.map(({ label, value, type }) => (
                <div
                  key={label}
                  className="flex items-center justify-between px-6 py-4"
                >
                  <label className="text-sm text-slate-300">{label}</label>
                  <input
                    type={type}
                    defaultValue={value}
                    readOnly
                    className="w-72 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
