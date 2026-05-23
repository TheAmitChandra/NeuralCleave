import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ReconnectingWSClient } from "@/lib/websocket";

// ------------------------------------------------------------------
// Minimal WebSocket mock — jsdom ships one but its readyState
// transitions aren't automatic, so we use a manual mock.
// ------------------------------------------------------------------

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

  /** Test helper: simulate a message arriving from the server. */
  triggerMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  /** Test helper: simulate the connection opening. */
  triggerOpen() {
    this.onopen?.();
  }
}

let mockWs: MockWebSocket;

beforeEach(() => {
  vi.useFakeTimers();
  mockWs = new MockWebSocket();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const WS = vi.fn(() => mockWs) as any;
  WS.OPEN   = MockWebSocket.OPEN;
  WS.CLOSED = MockWebSocket.CLOSED;
  vi.stubGlobal("WebSocket", WS);
  // Stub window so the SSR guard is bypassed
  vi.stubGlobal("window", {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ------------------------------------------------------------------

describe("ReconnectingWSClient", () => {
  it("connects and subscribes to messages", () => {
    const client = new ReconnectingWSClient("/ws/test");
    const received: unknown[] = [];

    client.connect();
    client.subscribe((msg) => received.push(msg));

    mockWs.triggerMessage({ type: "ping", payload: "hello" });

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ type: "ping", payload: "hello" });
  });

  it("ignores malformed (non-JSON) frames", () => {
    const client = new ReconnectingWSClient("/ws/test");
    const received: unknown[] = [];
    client.connect();
    client.subscribe((msg) => received.push(msg));

    // Simulate a non-JSON frame
    mockWs.onmessage?.({ data: "not-valid-json{{" });

    expect(received).toHaveLength(0);
  });

  it("unsubscribes correctly", () => {
    const client = new ReconnectingWSClient("/ws/test");
    const received: unknown[] = [];

    client.connect();
    const unsub = client.subscribe((msg) => received.push(msg));

    mockWs.triggerMessage({ type: "a", payload: 1 });
    unsub(); // stop listening
    mockWs.triggerMessage({ type: "b", payload: 2 });

    expect(received).toHaveLength(1);
  });

  it("schedules reconnect with exponential backoff on close", () => {
    const client = new ReconnectingWSClient("/ws/test");
    client.connect();

    // Close triggers reconnect after 1 s
    mockWs.close();
    vi.advanceTimersByTime(1000);
    expect(WebSocket).toHaveBeenCalledTimes(2); // initial + 1 reconnect

    // Next close → 2 s
    mockWs.close();
    vi.advanceTimersByTime(2000);
    expect(WebSocket).toHaveBeenCalledTimes(3);
  });

  it("resets backoff delay after a successful open", () => {
    const client = new ReconnectingWSClient("/ws/test");
    client.connect();

    // Simulate failed connection
    mockWs.close();
    vi.advanceTimersByTime(1000); // reconnect fires

    // Simulate the new connection succeeding
    mockWs.triggerOpen();

    // Close again — delay should be back to 1 s
    mockWs.close();
    vi.advanceTimersByTime(1000);
    expect(WebSocket).toHaveBeenCalledTimes(3); // initial + 2 reconnects
  });

  it("does not reconnect after disconnect()", () => {
    const client = new ReconnectingWSClient("/ws/test");
    client.connect();
    client.disconnect();

    vi.advanceTimersByTime(5000);
    // Only the initial connection, no reconnect
    expect(WebSocket).toHaveBeenCalledTimes(1);
  });

  it("appends token as query param when provided", () => {
    const client = new ReconnectingWSClient("/ws/test");
    client.connect("my-jwt-token");

    const constructedUrl = (WebSocket as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(constructedUrl).toContain("token=my-jwt-token");
  });

  it("reports isConnected correctly", () => {
    const client = new ReconnectingWSClient("/ws/test");
    client.connect();

    // Mock returns OPEN readyState
    expect(client.isConnected).toBe(true);

    client.disconnect();
    expect(client.isConnected).toBe(false);
  });
});
