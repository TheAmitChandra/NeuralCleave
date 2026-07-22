"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Layout,
  RefreshCw,
  Maximize2,
  Loader2,
  FileText,
  Code2,
  BarChart2,
  Image,
  Table,
  Globe,
  X,
} from "lucide-react";
import api from "@/lib/api";

interface CanvasBlock {
  id: string;
  block_type: "text" | "markdown" | "image" | "table" | "code" | "chart" | "html";
  content: unknown;
  title: string;
  created_at: string;
}

interface CanvasState {
  available: boolean;
  blocks: CanvasBlock[];
  count: number;
}

interface CanvasStatus {
  available: boolean;
  block_count?: number;
  subscriber_count?: number;
}

const BLOCK_ICONS: Record<string, React.ElementType> = {
  text: FileText,
  markdown: FileText,
  code: Code2,
  chart: BarChart2,
  image: Image,
  table: Table,
  html: Globe,
};

function BlockCard({ block }: { block: CanvasBlock }) {
  const Icon = BLOCK_ICONS[block.block_type] ?? FileText;

  const renderContent = () => {
    switch (block.block_type) {
      case "text":
        return <p className="text-sm text-slate-300 whitespace-pre-wrap">{String(block.content)}</p>;

      case "markdown":
        return (
          <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">
            {String(block.content)}
          </pre>
        );

      case "code": {
        const c = block.content as { code?: string; language?: string } | string;
        const code = typeof c === "string" ? c : (c?.code ?? "");
        const lang = typeof c === "string" ? "" : (c?.language ?? "");
        return (
          <div className="overflow-x-auto">
            {lang && (
              <p className="mb-1 text-xs text-violet-400 font-mono">{lang}</p>
            )}
            <pre className="text-xs text-slate-300 font-mono whitespace-pre">{code}</pre>
          </div>
        );
      }

      case "image": {
        const src = String(block.content);
        return (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={block.title || "Canvas image"} className="max-w-full rounded" />
        );
      }

      case "table": {
        const t = block.content as { headers?: string[]; rows?: string[][] } | null;
        if (!t?.headers) return <p className="text-xs text-slate-500">Empty table</p>;
        return (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr>
                  {t.headers.map((h, i) => (
                    <th key={i} className="border border-slate-700 px-2 py-1 text-left font-medium text-slate-400">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(t.rows ?? []).map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="border border-slate-700 px-2 py-1">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }

      case "chart": {
        const ch = block.content as {
          chart_type?: string;
          labels?: string[];
          values?: number[];
        } | null;
        if (!ch?.labels) return <p className="text-xs text-slate-500">Empty chart</p>;
        const max = Math.max(...(ch.values ?? [1]));
        return (
          <div className="space-y-1">
            <p className="text-xs text-slate-500 uppercase tracking-wide">{ch.chart_type}</p>
            {ch.labels.map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-20 shrink-0 truncate text-xs text-slate-400">{label}</span>
                <div className="flex-1 rounded-full bg-slate-800 h-2">
                  <div
                    className="h-2 rounded-full bg-violet-500"
                    style={{ width: `${(((ch.values ?? [])[i] ?? 0) / max) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-slate-500 tabular-nums">
                  {(ch.values ?? [])[i]}
                </span>
              </div>
            ))}
          </div>
        );
      }

      case "html":
        return (
          <iframe
            title={block.title || "html-block"}
            sandbox="allow-scripts"
            srcDoc={String(block.content)}
            className="w-full h-40 rounded border border-slate-700 bg-white"
          />
        );

      default:
        return (
          <pre className="text-xs text-slate-400 overflow-x-auto">
            {JSON.stringify(block.content, null, 2)}
          </pre>
        );
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-sky-400" />
        {block.title ? (
          <span className="text-sm font-medium text-white">{block.title}</span>
        ) : (
          <span className="text-xs text-slate-600 font-mono">{block.block_type}</span>
        )}
        <span className="ml-auto text-xs text-slate-600">
          {block.created_at ? new Date(block.created_at).toLocaleTimeString() : ""}
        </span>
      </div>
      {renderContent()}
    </div>
  );
}

export default function CanvasPage() {
  const [fullscreen, setFullscreen] = useState(false);

  const { data: status } = useQuery<CanvasStatus>({
    queryKey: ["canvas", "status"],
    queryFn: async () => {
      const { data } = await api.get<CanvasStatus>("/canvas/status");
      return data;
    },
    refetchInterval: 10_000,
  });

  const {
    data: state,
    isLoading,
    refetch,
    isFetching,
  } = useQuery<CanvasState>({
    queryKey: ["canvas", "state"],
    queryFn: async () => {
      const { data } = await api.get<CanvasState>("/canvas/state");
      return data;
    },
    refetchInterval: 5_000,
  });

  const blocks = state?.blocks ?? [];

  return (
    <div
      className={`flex flex-col gap-4 ${
        fullscreen ? "fixed inset-0 z-50 bg-slate-950 p-4" : "h-full"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <Layout className="h-6 w-6 text-sky-400" />
            Canvas
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Live agent reasoning graph — blocks rendered by AI in real time
          </p>
        </div>
        <div className="flex items-center gap-2">
          {status && (
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span>
                <span className="text-white font-medium">{state?.count ?? 0}</span> blocks
              </span>
              <span
                className={`flex items-center gap-1 rounded-full px-2.5 py-1 ${
                  status.available
                    ? "bg-emerald-900/40 text-emerald-400"
                    : "bg-slate-800 text-slate-500"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    status.available ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                  }`}
                />
                {status.available ? "Live" : "Idle"}
              </span>
            </div>
          )}
          <button
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-sky-500 hover:text-white disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => setFullscreen((f) => !f)}
            className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 transition hover:border-sky-500 hover:text-white"
            title={fullscreen ? "Exit fullscreen" : "Toggle fullscreen"}
          >
            {fullscreen ? <X className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* Canvas viewport */}
      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-4">
        {isLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading canvas…
          </div>
        ) : blocks.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <Layout className="h-12 w-12 text-slate-700" />
            <p className="text-sm text-slate-500">Canvas is empty.</p>
            <p className="text-xs text-slate-600">
              Blocks appear here as the AI reasons through a task. Try{" "}
              <code className="rounded bg-slate-800 px-1.5 py-0.5">
                neuralcleave canvas render --text &quot;Hello&quot;
              </code>
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {blocks.map((block) => (
              <BlockCard key={block.id} block={block} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
