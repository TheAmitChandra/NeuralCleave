"use client";

/**
 * AgentGraph — live React Flow visualization of active agents and their
 * communication links, streamed from the /ws/agents WebSocket channel.
 *
 * Nodes  → agents (coloured by status)
 * Edges  → agent-to-agent communication relationships
 */

import { useEffect, useCallback, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";
import { useAuthStore } from "@/store/auth";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentState {
  agent_id: string;
  name: string;
  agent_type: string;
  status: "IDLE" | "PLANNING" | "EXECUTING" | "VALIDATING" | "REFLECTING" | "PAUSED" | "TERMINATED";
  links?: string[]; // agent_ids this agent communicates with
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, string> = {
  IDLE: "#64748b",
  PLANNING: "#6366f1",
  EXECUTING: "#10b981",
  VALIDATING: "#f59e0b",
  REFLECTING: "#8b5cf6",
  PAUSED: "#f97316",
  TERMINATED: "#ef4444",
};

function agentToNode(agent: AgentState, index: number): Node {
  const cols = 4;
  const x = (index % cols) * 220 + 60;
  const y = Math.floor(index / cols) * 140 + 60;

  return {
    id: agent.agent_id,
    type: "default",
    position: { x, y },
    data: { label: agentLabel(agent) },
    style: {
      background: "#0f172a",
      border: `2px solid ${STATUS_COLORS[agent.status] ?? "#64748b"}`,
      borderRadius: "12px",
      color: "#f1f5f9",
      fontSize: "12px",
      padding: "10px 14px",
      minWidth: 160,
    },
  };
}

function agentLabel(agent: AgentState): React.ReactNode {
  return (
    <div>
      <div className="font-semibold truncate" style={{ maxWidth: 140 }}>
        {agent.name}
      </div>
      <div style={{ color: STATUS_COLORS[agent.status] ?? "#94a3b8", fontSize: 11 }}>
        {agent.agent_type} · {agent.status}
      </div>
    </div>
  );
}

function buildEdges(agents: AgentState[]): Edge[] {
  const edges: Edge[] = [];
  const seen = new Set<string>();
  for (const agent of agents) {
    for (const targetId of agent.links ?? []) {
      const key = [agent.agent_id, targetId].sort().join("--");
      if (!seen.has(key)) {
        seen.add(key);
        edges.push({
          id: key,
          source: agent.agent_id,
          target: targetId,
          animated: true,
          style: { stroke: "#475569", strokeWidth: 1.5 },
        });
      }
    }
  }
  return edges;
}

// ---------------------------------------------------------------------------
// Demo seed — shown when no live agents are connected
// ---------------------------------------------------------------------------

const DEMO_AGENTS: AgentState[] = [
  { agent_id: "planner-demo", name: "PlannerAgent", agent_type: "planner", status: "PLANNING", links: ["router-demo"] },
  { agent_id: "router-demo", name: "RouterAgent", agent_type: "router", status: "IDLE", links: ["executor-1-demo", "executor-2-demo"] },
  { agent_id: "executor-1-demo", name: "Executor #1", agent_type: "executor", status: "EXECUTING", links: ["validator-demo"] },
  { agent_id: "executor-2-demo", name: "Executor #2", agent_type: "executor", status: "IDLE", links: ["validator-demo"] },
  { agent_id: "validator-demo", name: "ValidatorAgent", agent_type: "validator", status: "VALIDATING", links: ["critic-demo"] },
  { agent_id: "critic-demo", name: "CriticAgent", agent_type: "critic", status: "REFLECTING", links: [] },
  { agent_id: "security-demo", name: "SecurityAgent", agent_type: "security", status: "IDLE", links: [] },
  { agent_id: "observer-demo", name: "ObserverAgent", agent_type: "observer", status: "IDLE", links: [] },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function AgentGraph() {
  const token = useAuthStore((s) => s.token);
  const [agents, setAgents] = useState<AgentState[]>(DEMO_AGENTS);
  const [connected, setConnected] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node[]>(
    DEMO_AGENTS.map((a, i) => agentToNode(a, i))
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge[]>(
    buildEdges(DEMO_AGENTS)
  );

  const onConnect = useCallback(
    (connection: Connection) => setEdges((eds) => addEdge(connection, eds)),
    [setEdges]
  );

  // Sync nodes/edges whenever agent state changes
  useEffect(() => {
    setNodes(agents.map((a, i) => agentToNode(a, i)));
    setEdges(buildEdges(agents));
  }, [agents, setNodes, setEdges]);

  // Connect to ws/agents for live data
  useEffect(() => {
    if (typeof window === "undefined") return;

    const wsUrl =
      (process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000") + "/ws/agents";
    const url = token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl;

    let ws: WebSocket;
    let alive = true;

    function connect() {
      ws = new WebSocket(url);

      ws.onopen = () => {
        if (alive) setConnected(true);
      };

      ws.onmessage = (ev) => {
        if (!alive) return;
        try {
          const msg = JSON.parse(ev.data as string) as {
            type: string;
            data: { states?: AgentState[] };
          };
          if (
            (msg.type === "agent.heartbeat" || msg.type === "agent.state_change") &&
            Array.isArray(msg.data?.states) &&
            msg.data.states.length > 0
          ) {
            setAgents(msg.data.states);
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (alive) {
          setConnected(false);
          setTimeout(connect, 3000);
        }
      };
    }

    connect();

    return () => {
      alive = false;
      ws?.close();
    };
  }, [token]);

  return (
    <div className="relative h-[520px] w-full overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      {/* Status badge */}
      <div className="absolute left-3 top-3 z-10 flex items-center gap-1.5 rounded-full bg-slate-900 px-3 py-1 text-xs">
        <span
          className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-amber-400"}`}
        />
        <span className="text-slate-400">
          {connected ? "Live" : "Demo"}
        </span>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#1e293b" gap={20} />
        <Controls
          style={{ background: "#0f172a", border: "1px solid #1e293b", color: "#94a3b8" }}
        />
        <MiniMap
          style={{ background: "#0f172a", border: "1px solid #1e293b" }}
          nodeColor={(n) => {
            const status = (n.data as { label: React.ReactNode })?.label
              ? "#6366f1"
              : "#64748b";
            return status;
          }}
        />
      </ReactFlow>
    </div>
  );
}
