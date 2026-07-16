"use client";

import { useQuery } from "@tanstack/react-query";
import { Package, CheckCircle, XCircle, Loader2, ExternalLink, ShieldCheck } from "lucide-react";
import api from "@/lib/api";

interface HubPackage {
  name: string;
  version: string;
  description: string;
  enabled: boolean;
  author?: string;
  homepage?: string;
  entry_point?: string;
  tags?: string[];
}

interface HubPackagesResponse {
  available: boolean;
  packages: HubPackage[];
}

function PackageCard({ pkg }: { pkg: HubPackage }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Package className="h-4 w-4 shrink-0 text-violet-400" />
          <span className="truncate font-semibold text-white">{pkg.name}</span>
          <span className="shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
            v{pkg.version}
          </span>
        </div>
        {pkg.enabled ? (
          <CheckCircle className="h-4 w-4 shrink-0 text-emerald-400" />
        ) : (
          <XCircle className="h-4 w-4 shrink-0 text-slate-600" />
        )}
      </div>

      <p className="text-sm text-slate-400 line-clamp-2">{pkg.description || "No description."}</p>

      {pkg.tags && pkg.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {pkg.tags.map((tag) => (
            <span key={tag} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-3 mt-auto text-xs text-slate-500">
        {pkg.author && <span>by {pkg.author}</span>}
        {pkg.homepage && (
          <a
            href={pkg.homepage}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 hover:text-violet-400 transition"
          >
            <ExternalLink className="h-3 w-3" /> docs
          </a>
        )}
        <span
          className={`ml-auto rounded-full px-2 py-0.5 ${
            pkg.enabled
              ? "bg-emerald-900/30 text-emerald-400"
              : "bg-slate-800 text-slate-500"
          }`}
        >
          {pkg.enabled ? "enabled" : "disabled"}
        </span>
      </div>
    </div>
  );
}

export default function SkillsPage() {
  const { data, isLoading, isError } = useQuery<HubPackagesResponse>({
    queryKey: ["hub-packages"],
    queryFn: async () => {
      const { data } = await api.get<HubPackagesResponse>("/hub/packages");
      return data;
    },
    refetchInterval: 30_000,
  });

  const packages = data?.packages ?? [];
  const enabled = packages.filter((p) => p.enabled).length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Package className="h-6 w-6 text-violet-400" />
            Skills Hub
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Installed CortexFlow Hub packages — extend your AI assistant with new capabilities
          </p>
        </div>
        {!isLoading && packages.length > 0 && (
          <div className="text-right text-sm text-slate-400">
            <span className="text-white font-medium">{enabled}</span>/{packages.length} enabled
          </div>
        )}
      </div>

      {/* Safety badge */}
      <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2.5 text-xs text-slate-400">
        <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
        All packages scanned by PackageScanner before install — 13 blocked imports, 14 dangerous
        patterns checked. Supply-chain safe by design.
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading packages…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-900/40 bg-red-900/10 p-6 text-sm text-red-400">
          Failed to load hub packages. Make sure the gateway is running.
        </div>
      )}

      {!isLoading && !isError && packages.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-10 text-center">
          <Package className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <p className="text-sm text-slate-400">No packages installed yet.</p>
          <p className="mt-2 text-xs text-slate-600">
            Run{" "}
            <code className="rounded bg-slate-800 px-1.5 py-0.5">
              cortex hub install &lt;url&gt;
            </code>{" "}
            to add one.
          </p>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {packages.map((pkg) => (
          <PackageCard key={pkg.name} pkg={pkg} />
        ))}
      </div>
    </div>
  );
}
