"use client";
import { useCallback, useRef, useState } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
} from "reactflow";
import type { Connection, Edge, Node, ReactFlowInstance } from "reactflow";
import "reactflow/dist/style.css";
import { Save } from "lucide-react";
import api from "@/lib/api";

type WFNodeType = "start" | "task" | "condition" | "end";

interface WFNodeData {
  label: string;
  nodeType: WFNodeType;
}

const NODE_COLORS: Record<WFNodeType, string> = {
  start: "#10b981",
  task: "#6366f1",
  condition: "#f59e0b",
  end: "#f43f5e",
};

const PALETTE: { type: WFNodeType; label: string }[] = [
  { type: "start", label: "Start" },
  { type: "task", label: "Task" },
  { type: "condition", label: "Condition" },
  { type: "end", label: "End" },
];

let _nodeCounter = 10;
function nextId() {
  return `wf-${++_nodeCounter}`;
}

const INITIAL_NODES: Node<WFNodeData>[] = [
  {
    id: "wf-1",
    type: "default",
    position: { x: 60, y: 120 },
    data: { label: "Start", nodeType: "start" },
    style: { background: NODE_COLORS.start, color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px" },
  },
  {
    id: "wf-2",
    type: "default",
    position: { x: 260, y: 120 },
    data: { label: "Process Task", nodeType: "task" },
    style: { background: NODE_COLORS.task, color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px" },
  },
  {
    id: "wf-3",
    type: "default",
    position: { x: 460, y: 120 },
    data: { label: "Validate", nodeType: "condition" },
    style: { background: NODE_COLORS.condition, color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px" },
  },
  {
    id: "wf-4",
    type: "default",
    position: { x: 660, y: 120 },
    data: { label: "End", nodeType: "end" },
    style: { background: NODE_COLORS.end, color: "#fff", border: "none", borderRadius: 8, padding: "6px 12px" },
  },
];

const INITIAL_EDGES: Edge[] = [
  { id: "e1-2", source: "wf-1", target: "wf-2", animated: true },
  { id: "e2-3", source: "wf-2", target: "wf-3", animated: true },
  { id: "e3-4", source: "wf-3", target: "wf-4", animated: true },
];

interface WorkflowBuilderProps {
  workflowId?: string | null;
  onSaved?: () => void;
}

export function WorkflowBuilder({ workflowId, onSaved }: WorkflowBuilderProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(INITIAL_NODES);
  const [edges, setEdges, onEdgesChange] = useEdgesState(INITIAL_EDGES);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState(false);

  const onConnect = useCallback(
    (connection: Connection) =>
      setEdges((prev) => addEdge({ ...connection, animated: true }, prev)),
    [setEdges],
  );

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const nodeType = e.dataTransfer.getData("application/wf-type") as WFNodeType;
      const label = e.dataTransfer.getData("application/wf-label");
      if (!nodeType || !rfInstance || !wrapperRef.current) return;

      const rect = wrapperRef.current.getBoundingClientRect();
      const position = rfInstance.project({
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });

      setNodes((prev) => [
        ...prev,
        {
          id: nextId(),
          type: "default",
          position,
          data: { label, nodeType },
          style: {
            background: NODE_COLORS[nodeType],
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "6px 12px",
          },
        },
      ]);
    },
    [rfInstance, setNodes],
  );

  const handleSave = async () => {
    if (!workflowId) return;
    setSaving(true);
    setSaveError(false);
    try {
      await api.patch(`/workflows/${workflowId}/dag`, {
        dag_definition: { nodes, edges },
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
      onSaved?.();
    } catch {
      setSaveError(true);
      setTimeout(() => setSaveError(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-[480px] overflow-hidden rounded-xl border border-slate-700 bg-slate-950">
      {/* Palette sidebar */}
      <div className="flex w-44 flex-col gap-2 border-r border-slate-800 bg-slate-900 p-3">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Node Palette
        </p>
        {PALETTE.map(({ type, label }) => (
          <div
            key={type}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("application/wf-type", type);
              e.dataTransfer.setData("application/wf-label", label);
              e.dataTransfer.effectAllowed = "move";
            }}
            className="cursor-grab select-none rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-white transition-colors hover:border-slate-500 active:cursor-grabbing"
            style={{ borderLeftColor: NODE_COLORS[type], borderLeftWidth: 3 }}
          >
            {label}
          </div>
        ))}

        <div className="mt-auto space-y-2">
          {saveError && (
            <p className="text-center text-xs text-rose-400">Save failed</p>
          )}
          {workflowId ? (
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-60"
            >
              <Save className="h-3.5 w-3.5" />
              {saving ? "Saving…" : saved ? "Saved ✓" : "Save DAG"}
            </button>
          ) : (
            <p className="text-center text-xs text-slate-500">
              Select a workflow to save
            </p>
          )}
        </div>
      </div>

      {/* React Flow canvas */}
      <div ref={wrapperRef} className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onInit={setRfInstance}
          onDrop={onDrop}
          onDragOver={onDragOver}
          fitView
          deleteKeyCode="Delete"
          snapToGrid
          snapGrid={[16, 16]}
        >
          <Background color="#334155" gap={16} size={1} />
          <Controls />
          <MiniMap
            nodeColor={(n) =>
              NODE_COLORS[(n.data as WFNodeData)?.nodeType] ?? NODE_COLORS.task
            }
            style={{ background: "#0f172a" }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
