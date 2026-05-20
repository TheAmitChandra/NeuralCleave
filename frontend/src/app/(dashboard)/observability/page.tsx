import { BarChart3, Activity, Cpu, Clock } from "lucide-react";

const PANELS = [
  {
    title: "HTTP Request Rate",
    icon: Activity,
    subtitle: "Requests / second across all endpoints",
  },
  {
    title: "LLM Token Usage",
    icon: Cpu,
    subtitle: "Tokens consumed across Gemini / DeepSeek / Ollama",
  },
  {
    title: "Agent Latency P99",
    icon: Clock,
    subtitle: "99th percentile execution time per agent type",
  },
  {
    title: "Workflow Throughput",
    icon: BarChart3,
    subtitle: "DAG executions completed per minute",
  },
];

export default function ObservabilityPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Observability</h1>
        <p className="mt-1 text-sm text-slate-400">
          Prometheus metrics · OpenTelemetry traces · Structured logs
        </p>
      </div>

      {/* Metric chart placeholders */}
      <div className="grid gap-4 lg:grid-cols-2">
        {PANELS.map(({ title, icon: Icon, subtitle }) => (
          <div
            key={title}
            className="rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <div className="mb-4 flex items-center gap-2">
              <Icon className="h-4 w-4 text-indigo-400" />
              <h3 className="text-sm font-semibold text-white">{title}</h3>
            </div>
            <div className="flex h-32 items-center justify-center rounded-lg bg-slate-800/50">
              <p className="text-xs text-slate-500">{subtitle}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Trace viewer */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Distributed Traces</h2>
        </div>
        <div className="p-6 text-center text-sm text-slate-500">
          OpenTelemetry trace viewer — Jaeger/Tempo integration in Phase 3.
        </div>
      </div>
    </div>
  );
}
