"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
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
  HelpCircle,
  Plus,
  Trash2,
  AlertCircle,
} from "lucide-react";
import axios from "axios";
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

// ---------------------------------------------------------------------------
// Guide modal
// ---------------------------------------------------------------------------

function GuideModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-y-auto max-h-[90vh]">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <div className="flex items-center gap-2">
            <Layout className="h-4 w-4 text-sky-400" />
            <h2 className="text-base font-semibold text-white">How Canvas Works</h2>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4 text-sm text-slate-300">
          <p>
            <strong className="text-white">Canvas</strong> is a live rendering surface where the AI displays structured outputs as it thinks.
            Instead of plain text in Chat, the AI can push code blocks, data tables, charts, or even full HTML pages here in real time.
          </p>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Ways to use Canvas</p>
            <div className="space-y-2 text-slate-300">
              <div className="flex gap-2">
                <span className="shrink-0 rounded bg-sky-900/40 px-1.5 py-0.5 text-xs text-sky-300 font-mono">Chat</span>
                <p>Ask the AI: <em>&quot;Draw a bar chart of monthly sales&quot;</em> or <em>&quot;Show me a code diff in Canvas.&quot;</em></p>
              </div>
              <div className="flex gap-2">
                <span className="shrink-0 rounded bg-violet-900/40 px-1.5 py-0.5 text-xs text-violet-300 font-mono">UI</span>
                <p>Click <strong className="text-white">Render Block</strong> to add any block type directly from this page.</p>
              </div>
              <div className="flex gap-2">
                <span className="shrink-0 rounded bg-slate-700 px-1.5 py-0.5 text-xs text-slate-300 font-mono">CLI</span>
                <p><code className="text-violet-300">neuralcleave canvas render --text &quot;Hello World&quot;</code></p>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Block Types</p>
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              {[
                ["text", "Plain text output"],
                ["markdown", "Formatted markdown"],
                ["code", "Syntax-highlighted code"],
                ["chart", "Bar/line charts"],
                ["table", "Data tables"],
                ["html", "Rendered HTML pages"],
              ].map(([type, desc]) => (
                <div key={type} className="flex items-center gap-1.5">
                  <span className="rounded bg-slate-700 px-1 py-0.5 font-mono text-slate-300">{type}</span>
                  <span className="text-slate-500">{desc}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Live updates</p>
            <p className="text-slate-400 text-xs">Canvas auto-refreshes every 5 seconds. Blocks persist until you click <strong className="text-slate-300">Clear Canvas</strong>. Maximum 200 blocks are stored at a time.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Render block modal
// ---------------------------------------------------------------------------

const BLOCK_TYPES = [
  { value: "text", label: "Text", placeholder: "Plain text content…" },
  { value: "markdown", label: "Markdown", placeholder: "## Heading\n\nParagraph with **bold** and *italic*." },
  { value: "code", label: "Code", placeholder: "def hello():\n    print('Hello, world!')" },
  { value: "html", label: "HTML", placeholder: "<h1>Hello</h1><p>World</p>" },
];

function RenderBlockModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [blockType, setBlockType] = useState("text");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [language, setLanguage] = useState("python");
  const [error, setError] = useState<string | null>(null);

  const def = BLOCK_TYPES.find(b => b.value === blockType)!;

  const mutation = useMutation({
    mutationFn: async () => {
      let finalContent: unknown = content;
      if (blockType === "code") finalContent = { code: content, language: language.trim() || "text" };
      const { data } = await api.post("/canvas/render", {
        block_type: blockType,
        title: title.trim() || undefined,
        content: finalContent,
      });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["canvas"] });
      onClose();
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) setError(err.response?.data?.detail ?? "Render failed");
      else setError("Render failed");
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
          <h2 className="text-base font-semibold text-white">Render Block</h2>
          <button onClick={onClose} className="rounded-lg p-1 text-slate-500 hover:bg-slate-800 hover:text-white transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Block Type</label>
            <select value={blockType} onChange={e => setBlockType(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-sky-500">
              {BLOCK_TYPES.map(b => <option key={b.value} value={b.value}>{b.label}</option>)}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Title <span className="text-slate-600">— optional</span></label>
            <input type="text" value={title} onChange={e => setTitle(e.target.value)} placeholder="Block title…"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-sky-500 placeholder:text-slate-600" />
          </div>

          {blockType === "code" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-400">Language</label>
              <input type="text" value={language} onChange={e => setLanguage(e.target.value)} placeholder="python, javascript, bash…"
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white outline-none focus:border-sky-500 placeholder:text-slate-600" />
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-400">Content</label>
            <textarea value={content} onChange={e => setContent(e.target.value)} rows={6}
              placeholder={def.placeholder}
              className="w-full resize-none rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-white font-mono outline-none focus:border-sky-500 placeholder:text-slate-600" />
          </div>

          {error && (
            <p className="flex items-center gap-1.5 text-xs text-rose-400">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" />{error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-800 px-6 py-4">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-slate-400 hover:bg-slate-800 hover:text-white transition-colors">Cancel</button>
          <button onClick={() => { setError(null); if (!content.trim()) { setError("Content is required"); return; } mutation.mutate(); }}
            disabled={mutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-40 transition-colors">
            {mutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Render
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Block card
// ---------------------------------------------------------------------------

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
            {lang && <p className="mb-1 text-xs text-violet-400 font-mono">{lang}</p>}
            <pre className="text-xs text-slate-300 font-mono whitespace-pre">{code}</pre>
          </div>
        );
      }

      case "image": {
        const src = String(block.content);
        // eslint-disable-next-line @next/next/no-img-element
        return <img src={src} alt={block.title || "Canvas image"} className="max-w-full rounded" />;
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
                    <th key={i} className="border border-slate-700 px-2 py-1 text-left font-medium text-slate-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(t.rows ?? []).map((row, ri) => (
                  <tr key={ri}>
                    {row.map((cell, ci) => (
                      <td key={ci} className="border border-slate-700 px-2 py-1">{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }

      case "chart": {
        const ch = block.content as { chart_type?: string; labels?: string[]; values?: number[] } | null;
        if (!ch?.labels) return <p className="text-xs text-slate-500">Empty chart</p>;
        const max = Math.max(...(ch.values ?? [1]));
        return (
          <div className="space-y-1.5">
            <p className="text-xs text-slate-500 uppercase tracking-wide">{ch.chart_type}</p>
            {ch.labels.map((label, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-20 shrink-0 truncate text-xs text-slate-400">{label}</span>
                <div className="flex-1 rounded-full bg-slate-800 h-2">
                  <div className="h-2 rounded-full bg-violet-500" style={{ width: `${(((ch.values ?? [])[i] ?? 0) / max) * 100}%` }} />
                </div>
                <span className="text-xs text-slate-500 tabular-nums">{(ch.values ?? [])[i]}</span>
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

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CanvasPage() {
  const [fullscreen, setFullscreen] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showRender, setShowRender] = useState(false);
  const queryClient = useQueryClient();

  const { data: status } = useQuery<CanvasStatus>({
    queryKey: ["canvas", "status"],
    queryFn: async () => {
      const { data } = await api.get<CanvasStatus>("/canvas/status");
      return data;
    },
    refetchInterval: 10_000,
  });

  const { data: state, isLoading, refetch, isFetching } = useQuery<CanvasState>({
    queryKey: ["canvas", "state"],
    queryFn: async () => {
      const { data } = await api.get<CanvasState>("/canvas/state");
      return data;
    },
    refetchInterval: 5_000,
  });

  const clearMutation = useMutation({
    mutationFn: () => api.delete("/canvas/clear"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["canvas"] }),
  });

  const blocks = state?.blocks ?? [];

  return (
    <div className={`flex flex-col gap-4 ${fullscreen ? "fixed inset-0 z-50 bg-slate-950 p-4" : "h-full"}`}>
      {showGuide && <GuideModal onClose={() => setShowGuide(false)} />}
      {showRender && <RenderBlockModal onClose={() => setShowRender(false)} />}

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
              <Layout className="h-6 w-6 text-sky-400" />
              Canvas
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Live agent reasoning surface — blocks rendered by AI in real time
            </p>
          </div>
          <button
            onClick={() => setShowGuide(true)}
            className="relative mt-1 rounded-full p-1.5 text-slate-600 hover:bg-slate-800 hover:text-sky-400 transition-colors"
            title="How does Canvas work?"
          >
            <HelpCircle className="h-4 w-4" />
            <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-sky-500 animate-pulse" />
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {status && (
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span><span className="text-white font-medium">{state?.count ?? 0}</span> blocks</span>
              <span className={`flex items-center gap-1 rounded-full px-2.5 py-1 ${status.available ? "bg-emerald-900/40 text-emerald-400" : "bg-slate-800 text-slate-500"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${status.available ? "bg-emerald-400 animate-pulse" : "bg-slate-600"}`} />
                {status.available ? "Live" : "Idle"}
              </span>
            </div>
          )}
          <button
            onClick={() => setShowRender(true)}
            className="flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-500 transition-colors"
          >
            <Plus className="h-4 w-4" /> Render Block
          </button>
          {blocks.length > 0 && (
            <button
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-400 hover:border-rose-700 hover:text-rose-400 disabled:opacity-40 transition-colors"
            >
              {clearMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
              Clear
            </button>
          )}
          <button
            onClick={() => void refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 transition hover:border-sky-500 hover:text-white disabled:opacity-40"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
          <button
            onClick={() => setFullscreen((f) => !f)}
            className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 transition hover:border-sky-500 hover:text-white"
            title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
          >
            {fullscreen ? <X className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950 p-4">
        {isLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" /> Loading canvas…
          </div>
        ) : blocks.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <Layout className="h-12 w-12 text-slate-700" />
            <div>
              <p className="text-sm font-medium text-slate-400">Canvas is empty</p>
              <p className="mt-1.5 text-xs text-slate-600 max-w-sm">
                Click{" "}
                <button onClick={() => setShowRender(true)} className="text-sky-400 hover:text-sky-300 underline">Render Block</button>
                {" "}to add a block, ask the AI in Chat to render something,
                or click the{" "}
                <button onClick={() => setShowGuide(true)} className="text-sky-400 hover:text-sky-300 underline">guide</button>
                {" "}for more ways.
              </p>
              <code className="mt-3 block text-xs text-violet-400 font-mono">
                neuralcleave canvas render --text &quot;Hello&quot;
              </code>
            </div>
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
