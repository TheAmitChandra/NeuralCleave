"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, AlertTriangle, Lock, Eye, CheckCircle, XCircle } from "lucide-react";
import api from "@/lib/api";

interface AuditLog {
  id: string;
  event_type: string;
  actor_id: string | null;
  actor_type: string;
  action: string;
  outcome: string;
  risk_score: string | null;
  ip_address: string | null;
  created_at: string;
}

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

const OUTCOME_ICON: Record<string, React.ReactNode> = {
  success: <CheckCircle className="h-4 w-4 text-emerald-400" />,
  failure: <XCircle className="h-4 w-4 text-rose-400" />,
  rejected: <XCircle className="h-4 w-4 text-amber-400" />,
};

export default function SecurityPage() {
  const { data: auditLogs = [], isLoading } = useQuery<AuditLog[]>({
    queryKey: ["audit-logs"],
    queryFn: async () => {
      const { data } = await api.get<AuditLog[]>("/observability/logs?limit=30&min_level=INFO");
      return data;
    },
    refetchInterval: 15_000,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Security</h1>
        <p className="mt-1 text-sm text-slate-400">
          Zero-trust security controls and threat monitoring
        </p>
      </div>

      {/* Security feature cards */}
      <div className="grid gap-4 sm:grid-cols-2">
        {SECURITY_FEATURES.map(({ title, icon: Icon, status, color, description }) => (
          <div key={title} className="rounded-xl border border-slate-800 bg-slate-900 p-6">
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
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-sm font-semibold text-white">Audit Log</h2>
          {!isLoading && (
            <span className="text-xs text-slate-500">{auditLogs.length} events</span>
          )}
        </div>
        {isLoading ? (
          <div className="space-y-2 p-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-800" />
            ))}
          </div>
        ) : auditLogs.length === 0 ? (
          <div className="p-6 text-center text-sm text-slate-500">
            Audit events will appear here once agents start executing.
          </div>
        ) : (
          <ul className="divide-y divide-slate-800">
            {auditLogs.map((log) => (
              <li key={log.id} className="flex items-center gap-3 px-5 py-3">
                <span className="shrink-0">
                  {OUTCOME_ICON[log.outcome] ?? OUTCOME_ICON.failure}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="truncate text-sm text-white">{log.action}</p>
                  <p className="text-xs text-slate-500">
                    {log.event_type} · {log.actor_type}
                    {log.actor_id ? ` · ${log.actor_id.slice(0, 8)}` : ""}
                    {log.risk_score ? ` · risk ${log.risk_score}` : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs text-slate-500">
                    {new Date(log.created_at).toLocaleTimeString()}
                  </p>
                  {log.ip_address && (
                    <p className="text-xs text-slate-600">{log.ip_address}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

