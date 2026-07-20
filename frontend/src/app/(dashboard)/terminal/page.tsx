"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Terminal as TerminalIcon, SquareX, Zap } from "lucide-react";

const SETTINGS_KEY = "NeuralCleave_settings";
const DEFAULT_WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:7432"
).replace(/^https?/, (p) => (p === "https" ? "wss" : "ws"));

function getTerminalWsUrl(): string {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      const settings = JSON.parse(saved) as Record<string, Record<string, string>>;
      const apiBase = settings?.api?.["API Base URL"];
      if (apiBase) {
        const wsBase = apiBase.replace(/^https?/, (p: string) =>
          p === "https" ? "wss" : "ws"
        );
        return `${wsBase.replace(/\/api\/v1$/, "")}/ws/terminal`;
      }
    }
  } catch {}
  return `${DEFAULT_WS_BASE}/ws/terminal`;
}

const QUICK_ACTIONS = [
  { label: "status", cmd: "cortex status" },
  { label: "channels list", cmd: "cortex channels list" },
  { label: "skills list", cmd: "cortex skills list" },
  { label: "plugins list", cmd: "cortex plugins list" },
  { label: "memory stats", cmd: "cortex memory stats" },
  { label: "--version", cmd: "cortex --version" },
  { label: "--help", cmd: "cortex --help" },
];

export default function TerminalPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<unknown>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [running, setRunning] = useState(false);
  const fitAddonRef = useRef<unknown>(null);

  const writeToTerm = useCallback((text: string) => {
    if (termRef.current) {
      (termRef.current as { write: (t: string) => void }).write(text);
    }
  }, []);

  // Connect WebSocket
  useEffect(() => {
    if (typeof window === "undefined") return;
    const ws = new WebSocket(getTerminalWsUrl());
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      setRunning(false);
      writeToTerm("\r\n\x1b[33m[Disconnected from gateway]\x1b[0m\r\n");
    };
    ws.onerror = () => {
      writeToTerm("\r\n\x1b[31m[WebSocket error — is the gateway running?]\x1b[0m\r\n");
    };
    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data as string) as Record<string, unknown>;
        if (msg.type === "ready") {
          setRunning(false);
          writeToTerm("\x1b[32m$ \x1b[0m");
        } else if (msg.type === "output") {
          const data = (msg.data as string) ?? "";
          writeToTerm(data.replace(/\n/g, "\r\n"));
        } else if (msg.type === "exit") {
          const code = msg.code as number;
          const color = code === 0 ? "\x1b[32m" : "\x1b[31m";
          writeToTerm(`\r\n${color}[exit ${code}]\x1b[0m\r\n`);
        } else if (msg.type === "error") {
          writeToTerm(`\r\n\x1b[31m[Error: ${msg.message as string}]\x1b[0m\r\n`);
        }
      } catch {}
    };

    return () => ws.close();
  }, [writeToTerm]);

  // Initialize xterm.js (browser-only dynamic import)
  useEffect(() => {
    if (!containerRef.current) return;
    let term: { write: (t: string) => void; dispose: () => void } | null = null;

    (async () => {
      const { Terminal } = await import("@xterm/xterm");
      const { FitAddon } = await import("@xterm/addon-fit");
      await import("@xterm/xterm/css/xterm.css");

      term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
        theme: {
          background: "#0a0a0f",
          foreground: "#e2e8f0",
          cursor: "#7c3aed",
          selectionBackground: "#7c3aed44",
          black: "#1e1e2e",
          red: "#f38ba8",
          green: "#a6e3a1",
          yellow: "#f9e2af",
          blue: "#89b4fa",
          magenta: "#cba6f7",
          cyan: "#89dceb",
          white: "#cdd6f4",
          brightBlack: "#45475a",
          brightRed: "#f38ba8",
          brightGreen: "#a6e3a1",
          brightYellow: "#f9e2af",
          brightBlue: "#89b4fa",
          brightMagenta: "#cba6f7",
          brightCyan: "#89dceb",
          brightWhite: "#cdd6f4",
        },
        rows: 30,
        cols: 100,
        scrollback: 1000,
      });

      const fit = new FitAddon();
      fitAddonRef.current = fit;
      term.loadAddon(fit);
      term.open(containerRef.current!);
      fit.fit();

      termRef.current = term;
      term.write("\x1b[1;35mNeuralCleave Terminal\x1b[0m\r\n");
      term.write("Connecting to gateway…\r\n");

      const observer = new ResizeObserver(() => {
        try { fit.fit(); } catch {}
      });
      if (containerRef.current) observer.observe(containerRef.current);

      return () => observer.disconnect();
    })();

    return () => {
      if (term) term.dispose();
    };
  }, []);

  const sendCmd = useCallback(
    (cmd: string) => {
      if (!connected || running || !cmd.trim()) return;
      writeToTerm(`\x1b[36m${cmd}\x1b[0m\r\n`);
      setRunning(true);
      wsRef.current?.send(JSON.stringify({ type: "run", cmd }));
      setInput("");
    },
    [connected, running, writeToTerm]
  );

  const handleInterrupt = () => {
    wsRef.current?.send(JSON.stringify({ type: "interrupt" }));
    writeToTerm("\r\n\x1b[33m^C\x1b[0m\r\n");
    setRunning(false);
  };

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white">
            <TerminalIcon className="h-6 w-6 text-violet-400" />
            Terminal
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Run commands directly against your NeuralCleave gateway
          </p>
        </div>
        <span
          className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
            connected
              ? "bg-emerald-900/40 text-emerald-400"
              : "bg-red-900/40 text-red-400"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connected ? "bg-emerald-400" : "bg-red-400"
            }`}
          />
          {connected ? "Connected" : "Disconnected"}
        </span>
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-2">
        <span className="flex items-center gap-1 text-xs text-slate-500">
          <Zap className="h-3 w-3" /> Quick:
        </span>
        {QUICK_ACTIONS.map((a) => (
          <button
            key={a.cmd}
            onClick={() => sendCmd(a.cmd)}
            disabled={!connected || running}
            className="rounded-md border border-slate-700 bg-slate-800 px-2.5 py-1 text-xs text-slate-300 transition hover:border-violet-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* xterm.js pane */}
      <div className="flex-1 overflow-hidden rounded-xl border border-slate-800 bg-[#0a0a0f] p-3">
        <div ref={containerRef} className="h-full w-full" />
      </div>

      {/* Command input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendCmd(input);
        }}
        className="flex gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            connected ? (running ? "Command running…" : "Enter command…") : "Not connected"
          }
          disabled={!connected || running}
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white placeholder-slate-600 focus:border-violet-500 focus:outline-none disabled:opacity-40"
        />
        {running ? (
          <button
            type="button"
            onClick={handleInterrupt}
            className="flex items-center gap-1.5 rounded-lg border border-red-700 bg-red-900/30 px-4 py-2 text-sm text-red-400 transition hover:bg-red-900/60"
          >
            <SquareX className="h-4 w-4" /> Interrupt
          </button>
        ) : (
          <button
            type="submit"
            disabled={!connected || !input.trim()}
            className="rounded-lg border border-violet-600 bg-violet-700 px-4 py-2 text-sm text-white transition hover:bg-violet-600 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Run
          </button>
        )}
      </form>
    </div>
  );
}
