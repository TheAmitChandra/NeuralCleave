"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Package,
  CheckCircle,
  XCircle,
  Loader2,
  ExternalLink,
  ShieldCheck,
  HelpCircle,
  X,
  Plus,
  AlertCircle,
  Trash2,
  Download,
  ToggleLeft,
  ToggleRight,
  ScanLine,
} from "lucide-react";
import axios from "axios";
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

interface ScanResult {
  safe: boolean;
  blocked_imports: string[];
  dangerous_patterns: string[];
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Guide modal
// ---------------------------------------------------------------------------

function GuideModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <Package className="h-4 w-4 text-violet-400" />
            <h2 className="text-base font-semibold text-white">How Skills Hub Works</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 text-sm text-slate-300">
          <p>
            <strong className="text-white">Skills</strong> are installable Python packages that add new tools to your AI assistant.
            Once installed and enabled, the AI can use them automatically — web search, weather lookup,
            calendar integration, custom APIs, and more.
          </p>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Quick Start</p>
            <ol className="list-decimal pl-4 space-y-1.5 text-slate-300">
              <li>Click <strong className="text-white">Install Package</strong> and paste a GitHub/URL pointing to a skill.</li>
              <li>The package is <strong className="text-white">scanned for security</strong> first — blocked imports and dangerous patterns are checked automatically.</li>
              <li>Once installed, <strong className="text-white">enable it</strong> so the AI can use its tools.</li>
              <li>Ask the AI to use the skill in Chat (e.g. "Search the web for…").</li>
            </ol>
          </div>

          <div className="rounded-xl border border-emerald-900/30 bg-emerald-900/10 p-4 space-y-1">
            <div className="flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              <p className="text-xs font-semibold text-emerald-400">Supply-chain safe by design</p>
            </div>
            <p className="text-xs text-slate-400">
              Every package is scanned by PackageScanner before install. 13 blocked imports and 14 dangerous patterns are checked.
              You can also scan a URL without installing using the scan endpoint.
            </p>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">CLI equivalent</p>
            <code className="block text-xs text-violet-300 font-mono">neuralcleave hub install &lt;url&gt;</code>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Install package modal
// ---------------------------------------------------------------------------

function InstallModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [sourceUrl, setSourceUrl] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [author, setAuthor] = useState("");
  const [tags, setTags] = useState("");
  const [force, setForce] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<"form" | "scanned" | "installed">("form");

  const scanMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ScanResult>("/hub/scan", { source_url: sourceUrl.trim() });
      return data;
    },
    onSuccess: (data) => {
      setScanResult(data);
      setStep("scanned");
      setError(null);
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) setError(err.response?.data?.detail ?? "Scan failed");
      else setError("Scan failed");
    },
  });

  const installMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, unknown> = {
        source_url: sourceUrl.trim(),
        force,
      };
      if (name.trim()) payload.name = name.trim();
      if (description.trim()) payload.description = description.trim();
      if (author.trim()) payload.author = author.trim();
      if (tags.trim()) payload.tags = tags.split(",").map(s => s.trim()).filter(Boolean);
      const { data } = await api.post("/hub/packages", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["hub-packages"] });
      setStep("installed");
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) setError(err.response?.data?.detail ?? "Install failed");
      else setError("Install failed");
    },
  });

  if (step === "installed") {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
        <div className="w-full max-w-sm rounded-2xl border border-slate-700 bg-slate-900 p-8 text-center shadow-2xl">
          <CheckCircle className="mx-auto mb-3 h-10 w-10 text-emerald-400" />
          <p className="text-base font-semibold text-white">Package installed!</p>
          <p className="mt-1 text-sm text-slate-400">Enable it below to make it available to the AI.</p>
          <button onClick={onClose} className="mt-4 rounded-lg bg-violet-600 px-5 py-2 text-sm font-medium text-white hover:bg-violet-500 transition-colors">
            Done
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-base font-semibold text-white">
            {step === "scanned" ? "Scan Result — Confirm Install" : "Install Skill Package"}
          </h2>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {step === "form" && (
            <>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-400">Source URL <span className="text-slate-600">— GitHub raw URL or direct .py link</span></label>
                <input type="url" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)}
                  placeholder="https://raw.githubusercontent.com/…/skill.py"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-400">Name <span className="text-slate-600">— optional, auto-derived from URL</span></label>
                <input type="text" value={name} onChange={e => setName(e.target.value)} placeholder="my-skill"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-400">Description</label>
                <input type="text" value={description} onChange={e => setDescription(e.target.value)} placeholder="What this skill does"
                  className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">Author</label>
                  <input type="text" value={author} onChange={e => setAuthor(e.target.value)} placeholder="optional"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-400">Tags <span className="text-slate-600">comma-sep</span></label>
                  <input type="text" value={tags} onChange={e => setTags(e.target.value)} placeholder="web, search"
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-violet-500 placeholder:text-slate-600" />
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} className="accent-violet-500 h-4 w-4 rounded" />
                <span className="text-xs text-slate-400">Force reinstall if already installed</span>
              </label>
            </>
          )}

          {step === "scanned" && scanResult && (
            <div className="space-y-3">
              <div className={`flex items-center gap-2 rounded-lg p-3 text-sm font-medium ${scanResult.safe ? "bg-emerald-900/20 text-emerald-400" : "bg-rose-900/20 text-rose-400"}`}>
                {scanResult.safe ? <ShieldCheck className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                {scanResult.safe ? "Package passed security scan" : "Security issues detected"}
              </div>
              {scanResult.blocked_imports.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-rose-400 mb-1">Blocked imports found:</p>
                  <div className="flex flex-wrap gap-1">
                    {scanResult.blocked_imports.map(i => <span key={i} className="rounded bg-rose-900/20 px-1.5 py-0.5 text-xs text-rose-300 font-mono">{i}</span>)}
                  </div>
                </div>
              )}
              {scanResult.warnings.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-amber-400 mb-1">Warnings:</p>
                  <ul className="space-y-0.5">
                    {scanResult.warnings.map((w, i) => <li key={i} className="text-xs text-amber-300">{w}</li>)}
                  </ul>
                </div>
              )}
              {!scanResult.safe && (
                <p className="text-xs text-slate-500">We recommend not installing packages with security issues. Proceeding is at your own risk.</p>
              )}
            </div>
          )}

          {error && (
            <p className="flex items-center gap-1.5 text-xs text-rose-400">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
          {step === "form" && (
            <>
              <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">Cancel</button>
              <button onClick={() => { setError(null); if (!sourceUrl.trim()) { setError("Source URL is required"); return; } scanMutation.mutate(); }}
                disabled={scanMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white disabled:opacity-40 transition-colors">
                {scanMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
                Scan first
              </button>
              <button onClick={() => { setError(null); if (!sourceUrl.trim()) { setError("Source URL is required"); return; } installMutation.mutate(); }}
                disabled={installMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 transition-colors">
                {installMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Install
              </button>
            </>
          )}
          {step === "scanned" && (
            <>
              <button onClick={() => { setStep("form"); setScanResult(null); }} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">Back</button>
              <button onClick={() => installMutation.mutate()} disabled={installMutation.isPending}
                className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-4 py-2 text-sm font-medium text-white hover:bg-violet-500 disabled:opacity-40 transition-colors">
                {installMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                Install anyway
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Package card
// ---------------------------------------------------------------------------

function PackageCard({ pkg }: { pkg: HubPackage }) {
  const queryClient = useQueryClient();

  const toggleMutation = useMutation({
    mutationFn: () => api.patch(`/hub/packages/${pkg.name}`, { enabled: !pkg.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hub-packages"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`/hub/packages/${pkg.name}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hub-packages"] }),
  });

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Package className="h-4 w-4 shrink-0 text-violet-400" />
          <span className="truncate font-semibold text-white">{pkg.name}</span>
          <span className="shrink-0 rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">v{pkg.version}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {pkg.enabled ? (
            <CheckCircle className="h-4 w-4 text-emerald-400" />
          ) : (
            <XCircle className="h-4 w-4 text-slate-600" />
          )}
        </div>
      </div>

      <p className="text-sm text-slate-400 line-clamp-2 flex-1">{pkg.description || "No description."}</p>

      {pkg.tags && pkg.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {pkg.tags.map((tag) => (
            <span key={tag} className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500">{tag}</span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 mt-auto">
        {pkg.author && <span className="text-xs text-slate-600">by {pkg.author}</span>}
        {pkg.homepage && (
          <a href={pkg.homepage} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-slate-600 hover:text-violet-400 transition">
            <ExternalLink className="h-3 w-3" /> docs
          </a>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => toggleMutation.mutate()}
            disabled={toggleMutation.isPending}
            title={pkg.enabled ? "Disable" : "Enable"}
            className="text-slate-500 hover:text-violet-400 transition-colors"
          >
            {pkg.enabled ? <ToggleRight className="h-4 w-4 text-emerald-400" /> : <ToggleLeft className="h-4 w-4" />}
          </button>
          <button
            onClick={() => deleteMutation.mutate()}
            disabled={deleteMutation.isPending}
            title="Uninstall"
            className="text-slate-600 hover:text-rose-400 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SkillsPage() {
  const [showGuide, setShowGuide] = useState(false);
  const [showInstall, setShowInstall] = useState(false);

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
      {showGuide && <GuideModal onClose={() => setShowGuide(false)} />}
      {showInstall && <InstallModal onClose={() => setShowInstall(false)} />}

      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
              <Package className="h-6 w-6 text-violet-400" />
              Skills Hub
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Installed NeuralCleave Hub packages — extend your AI assistant with new capabilities
            </p>
          </div>
          <button
            onClick={() => setShowGuide(true)}
            className="relative mt-1 rounded-full p-1.5 text-slate-600 hover:bg-slate-800 hover:text-violet-400 transition-colors"
            title="How does this work?"
          >
            <HelpCircle className="h-4 w-4" />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-violet-500 animate-pulse" />
          </button>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {!isLoading && packages.length > 0 && (
            <span className="text-sm text-slate-400">
              <span className="text-white font-medium">{enabled}</span>/{packages.length} enabled
            </span>
          )}
          <button
            onClick={() => setShowInstall(true)}
            className="flex items-center gap-1.5 rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-violet-500 transition-colors"
          >
            <Plus className="h-4 w-4" /> Install Package
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-2.5 text-xs text-slate-400">
        <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
        All packages scanned by PackageScanner before install — 13 blocked imports, 14 dangerous patterns checked. Supply-chain safe by design.
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading packages…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-900/40 bg-red-900/10 p-6 text-sm text-red-400">
          Failed to load hub packages. Make sure the gateway is running.
        </div>
      )}

      {!isLoading && !isError && packages.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-10 text-center">
          <Package className="mx-auto mb-3 h-10 w-10 text-slate-700" />
          <p className="text-sm font-medium text-slate-400">No packages installed yet.</p>
          <p className="mt-2 text-xs text-slate-600">
            Click{" "}
            <button onClick={() => setShowInstall(true)} className="text-violet-400 hover:text-violet-300 underline">
              Install Package
            </button>{" "}
            above to add your first skill, or click the{" "}
            <button onClick={() => setShowGuide(true)} className="text-violet-400 hover:text-violet-300 underline">
              guide
            </button>{" "}
            to learn more.
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
