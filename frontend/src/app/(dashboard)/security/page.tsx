import { ShieldCheck, AlertTriangle, Lock, Eye } from "lucide-react";

const SECURITY_FEATURES = [
  {
    title: "Zero-Trust Execution",
    icon: Lock,
    status: "Active",
    color: "text-emerald-400",
    description: "Every agent action is verified, sandboxed, and audited before execution.",
  },
  {
    title: "Prompt Injection Defense",
    icon: ShieldCheck,
    status: "Active",
    color: "text-emerald-400",
    description: "Multi-layer detection for prompt injection and jailbreak attempts.",
  },
  {
    title: "Risk Scoring",
    icon: AlertTriangle,
    status: "Active",
    color: "text-amber-400",
    description: "Real-time risk score (0-100) calculated before every tool call.",
  },
  {
    title: "Human Approval Layer",
    icon: Eye,
    status: "Pending",
    color: "text-slate-400",
    description: "High-risk actions (score >70) require human approval before execution.",
  },
];

export default function SecurityPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Security</h1>
        <p className="mt-1 text-sm text-slate-400">
          Zero-trust security controls and threat monitoring
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {SECURITY_FEATURES.map(({ title, icon: Icon, status, color, description }) => (
          <div
            key={title}
            className="rounded-xl border border-slate-800 bg-slate-900 p-6"
          >
            <div className="flex items-center gap-3">
              <Icon className={`h-5 w-5 ${color}`} />
              <div className="flex-1">
                <h3 className="font-semibold text-white">{title}</h3>
              </div>
              <span className={`text-xs font-medium ${color}`}>{status}</span>
            </div>
            <p className="mt-3 text-sm text-slate-400">{description}</p>
          </div>
        ))}
      </div>

      {/* Audit log */}
      <div className="rounded-xl border border-slate-800 bg-slate-900">
        <div className="border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Audit Log</h2>
        </div>
        <div className="p-6 text-center text-sm text-slate-500">
          Audit events will appear here once agents start executing.
        </div>
      </div>
    </div>
  );
}
