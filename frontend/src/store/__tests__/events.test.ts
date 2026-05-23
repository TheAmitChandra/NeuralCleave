import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useEventsStore } from "@/store/events";

// ── Mock the websocket module ───────────────────────────────────────────────
// vi.mock() is hoisted to the top, so factory values must be created with
// vi.hoisted() to avoid "cannot access before initialization" errors.

type Subscriber = (msg: { type: string; payload: unknown }) => void;

function makeFakeWS() {
  const subscribers = new Set<Subscriber>();
  return {
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn((fn: Subscriber) => {
      subscribers.add(fn);
      return () => subscribers.delete(fn);
    }),
    emit(data: { type: string; payload: unknown }) {
      subscribers.forEach((fn) => fn(data));
    },
    reset() {
      subscribers.clear();
      vi.clearAllMocks();
    },
  };
}

const { fakeAgentsWS, fakeWorkflowsWS, fakeEventsWS } = vi.hoisted(() => ({
  fakeAgentsWS:    makeFakeWS(),
  fakeWorkflowsWS: makeFakeWS(),
  fakeEventsWS:    makeFakeWS(),
}));

vi.mock("@/lib/websocket", () => ({
  agentsWS:    fakeAgentsWS,
  workflowsWS: fakeWorkflowsWS,
  eventsWS:    fakeEventsWS,
}));

// ── Tests ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  fakeAgentsWS.reset();
  fakeWorkflowsWS.reset();
  fakeEventsWS.reset();

  // Reset Zustand store to initial state between tests
  useEventsStore.setState({
    connected: false,
    agentEvents: [],
    workflowEvents: [],
    systemEvents: [],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

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
    expect(fakeAgentsWS.connect).toHaveBeenCalledWith("test-token");
    expect(fakeWorkflowsWS.connect).toHaveBeenCalledWith("test-token");
    expect(fakeEventsWS.connect).toHaveBeenCalledWith("test-token");
  });

  it("buffers incoming agent events", () => {
    useEventsStore.getState().connect("tok");

    fakeAgentsWS.emit({ type: "agent_update", payload: { agent_id: "a1", status: "running" } });

    const { agentEvents } = useEventsStore.getState();
    expect(agentEvents).toHaveLength(1);
    expect(agentEvents[0]).toMatchObject({ agent_id: "a1", status: "running" });
  });

  it("buffers incoming workflow events", () => {
    useEventsStore.getState().connect("tok");

    fakeWorkflowsWS.emit({ type: "workflow_update", payload: { workflow_id: "w1", status: "completed" } });

    const { workflowEvents } = useEventsStore.getState();
    expect(workflowEvents).toHaveLength(1);
    expect(workflowEvents[0]).toMatchObject({ workflow_id: "w1", status: "completed" });
  });

  it("buffers incoming system events", () => {
    useEventsStore.getState().connect("tok");

    fakeEventsWS.emit({ type: "system_alert", payload: { message: "disk full" } });

    const { systemEvents } = useEventsStore.getState();
    expect(systemEvents).toHaveLength(1);
    expect(systemEvents[0]).toMatchObject({ type: "system_alert" });
  });

  it("caps buffer at 100 events per channel", () => {
    useEventsStore.getState().connect("tok");

    for (let i = 0; i < 110; i++) {
      fakeAgentsWS.emit({ type: "a", payload: { agent_id: `a${i}`, status: "idle" } });
    }

    expect(useEventsStore.getState().agentEvents).toHaveLength(100);
  });

  it("clearEvents() empties all buffers", () => {
    useEventsStore.getState().connect("tok");

    fakeAgentsWS.emit({ type: "a", payload: { agent_id: "x", status: "idle" } });
    fakeWorkflowsWS.emit({ type: "w", payload: { workflow_id: "y", status: "done" } });

    useEventsStore.getState().clearEvents();

    const state = useEventsStore.getState();
    expect(state.agentEvents).toHaveLength(0);
    expect(state.workflowEvents).toHaveLength(0);
    expect(state.systemEvents).toHaveLength(0);
  });

  it("disconnect() calls disconnect on all WS clients", () => {
    useEventsStore.getState().connect("tok");
    useEventsStore.getState().disconnect();

    expect(fakeAgentsWS.disconnect).toHaveBeenCalled();
    expect(fakeWorkflowsWS.disconnect).toHaveBeenCalled();
    expect(fakeEventsWS.disconnect).toHaveBeenCalled();
    expect(useEventsStore.getState().connected).toBe(false);
  });
});

