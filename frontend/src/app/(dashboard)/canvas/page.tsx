"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Layout, RefreshCw, Maximize2, Loader2 } from "lucide-react";
import api from "@/lib/api";

interface CanvasStatus {
  active: boolean;
  mode?: string;
  node_count?: number;
  edge_count?: number;
  last_updated?: string;
}

interface CanvasSnapshot {
  html?: string;
  svg?: string;
  json?: unknown;
}

export default function CanvasPage() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const { data: status, isLoading: statusLoading } = useQuery<CanvasStatus>({
    queryKey: ["canvas", "status"],
    queryFn: async () => {
      const { data } = await api.get<CanvasStatus>("/canvas/status");
      return data;
    },
    refetchInterval: 10_000,
  });

  const {
    data: snapshot,
    isLoading: snapshotLoading,
    refetch,
    isFetching,
  } = useQuery<CanvasSnapshot>({
    queryKey: ["canvas", "snapshot"],
    queryFn: async () => {
      const { data } = await api.get<CanvasSnapshot>("/canvas/snapshot");
      return data;
    },
    refetchInterval: 15_000,
  });

  // Inject snapshot HTML into the iframe (CSP-safe — no cross-origin fetch)
  useEffect(() => {
    if (!iframeRef.current || !snapshot?.html) return;
    const doc = iframeRef.current.contentDocument;
    if (!doc) return;
    doc.open();
    doc.write(snapshot.html);
    doc.close();
  }, [snapshot?.html]);

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
            Live visual representation of the agent reasoning graph
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!statusLoading && status && (
            <div className="flex items-center gap-3 text-xs text-slate-400">
              {status.node_count !== undefined && (
                <span>
                  <span className="text-white font-medium">{status.node_count}</span> nodes
                </span>
              )}
              {status.edge_count !== undefined && (
                <span>
                  <span className="text-white font-medium">{status.edge_count}</span> edges
                </span>
              )}
              <span
                className={`flex items-center gap-1 rounded-full px-2.5 py-1 ${
                  status.active
                    ? "bg-emerald-900/40 text-emerald-400"
                    : "bg-slate-800 text-slate-500"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    status.active ? "bg-emerald-400 animate-pulse" : "bg-slate-600"
                  }`}
                />
                {status.active ? "Live" : "Idle"}
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
            title="Toggle fullscreen"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Canvas viewport */}
      <div className="flex-1 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
        {snapshotLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading canvas snapshot…
          </div>
        ) : snapshot?.html ? (
          <iframe
            ref={iframeRef}
            title="Canvas"
            sandbox="allow-scripts"
            className="h-full w-full border-0"
          />
        ) : snapshot?.svg ? (
          <div
            className="h-full w-full overflow-auto"
            dangerouslySetInnerHTML={{ __html: snapshot.svg }}
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <Layout className="h-12 w-12 text-slate-700" />
            <p className="text-sm text-slate-500">No canvas snapshot available yet.</p>
            <p className="text-xs text-slate-600">
              The canvas renders when an agent reasoning graph is active.
            </p>
          </div>
        )}
      </div>

      {status?.last_updated && (
        <p className="text-right text-xs text-slate-600">
          Last updated: {new Date(status.last_updated).toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}
