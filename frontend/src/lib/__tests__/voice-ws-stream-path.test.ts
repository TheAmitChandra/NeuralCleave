import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS } from "@/lib/voice-ws";

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  send() {}
  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

describe("voiceStreamWS path", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    const WS = vi.fn(() => new MockWebSocket()) as unknown as typeof WebSocket;
    (WS as unknown as Record<string, number>).OPEN = 1;
    (WS as unknown as Record<string, number>).CLOSED = 3;
    vi.stubGlobal("WebSocket", WS);
    vi.stubGlobal("window", {});
    vi.stubGlobal("localStorage", { getItem: () => null });
  });

  afterEach(() => {
    voiceStreamWS.disconnect();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("connects to a URL containing /ws/voice", () => {
    voiceStreamWS.connect();
    const url = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).toContain("/ws/voice");
  });

  it("does not connect to the /ws chat endpoint", () => {
    voiceStreamWS.connect();
    const url = (WebSocket as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(url).not.toMatch(/\/ws$/);
  });
});
