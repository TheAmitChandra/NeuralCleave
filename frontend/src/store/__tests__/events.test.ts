import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useEventsStore } from "@/store/events";

// ── Minimal WebSocket stub ──────────────────────────────────────────────────

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

const instances: MockWebSocket[] = [];

beforeEach(() => {
  instances.length = 0;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.stubGlobal("WebSocket", vi.fn(() => { const ws = new MockWebSocket(); instances.push(ws); return ws; }) as any);
  vi.stubGlobal("window", {});

  // Reset Zustand store to initial state between tests
  useEventsStore.setState({
    connected: false,
    agentEvents: [],
    workflowEvents: [],
    systemEvents: [],
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Returns the MockWebSocket created for /ws/agents (index 0). */
const agentSocket = () => instances[0];
/** Returns the MockWebSocket created for /ws/workflows (index 1). */
const workflowSocket = () => instances[1];
/** Returns the MockWebSocket created for /ws/events (index 2). */
const eventsSocket = () => instances[2];

// ── Tests ────────────────────────────────────────────────────────────────────

describe("useEventsStore", () => {
  it("starts with empty state", () => {
    const state = useEventsStore.getState();
    expect(state.connected).toBe(false);
    expect(state.agentEvents).toHaveLength(0);
    expect(state.workflowEvents).toHaveLength(0);
    expect(state.systemEvents).toHaveLength(0);
  });

  it("connect() opens three WebSocket connections", () => {
    useEventsStore.getState().connect("test-token");
    expect(WebSocket).toHaveBeenCalledTimes(3);
  });

  it("buffers incoming agent events", () => {
    useEventsStore.getState().connect("tok");

    agentSocket().emit({ type: "agent_update", payload: { agent_id: "a1", status: "running" } });

    const { agentEvents } = useEventsStore.getState();
    expect(agentEvents).toHaveLength(1);
    expect(agentEvents[0]).toMatchObject({ agent_id: "a1", status: "running" });
  });

  it("buffers incoming workflow events", () => {
    useEventsStore.getState().connect("tok");

    workflowSocket().emit({ type: "workflow_update", payload: { workflow_id: "w1", status: "completed" } });

    const { workflowEvents } = useEventsStore.getState();
    expect(workflowEvents).toHaveLength(1);
    expect(workflowEvents[0]).toMatchObject({ workflow_id: "w1", status: "completed" });
  });

  it("buffers incoming system events", () => {
    useEventsStore.getState().connect("tok");

    eventsSocket().emit({ type: "system_alert", payload: { message: "disk full" } });

    const { systemEvents } = useEventsStore.getState();
    expect(systemEvents).toHaveLength(1);
    expect(systemEvents[0]).toMatchObject({ type: "system_alert" });
  });

  it("caps buffer at 100 events per channel", () => {
    useEventsStore.getState().connect("tok");

    for (let i = 0; i < 110; i++) {
      agentSocket().emit({ type: "a", payload: { agent_id: `a${i}`, status: "idle" } });
    }

    expect(useEventsStore.getState().agentEvents).toHaveLength(100);
  });

  it("clearEvents() empties all buffers", () => {
    useEventsStore.getState().connect("tok");

    agentSocket().emit({ type: "a", payload: { agent_id: "x", status: "idle" } });
    workflowSocket().emit({ type: "w", payload: { workflow_id: "y", status: "done" } });

    useEventsStore.getState().clearEvents();

    const state = useEventsStore.getState();
    expect(state.agentEvents).toHaveLength(0);
    expect(state.workflowEvents).toHaveLength(0);
    expect(state.systemEvents).toHaveLength(0);
  });

  it("disconnect() sets connected to false", () => {
    useEventsStore.getState().connect("tok");
    expect(useEventsStore.getState().connected).toBe(true);

    useEventsStore.getState().disconnect();
    expect(useEventsStore.getState().connected).toBe(false);
  });
});
