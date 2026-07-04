/**
 * CortexFlow-AI WebSocket client
 *
 * Provides an auto-reconnecting WebSocket connection to the gateway's single
 * chat/event endpoint at /ws — see cortexflow_ai/gateway/websocket.py for the
 * message protocol (hello/ping/pong/subscribe/message_chunk/message_done/error
 * frames). Chat replies stream as zero or more "message_chunk" frames (each
 * carrying one incremental "delta") followed by exactly one "message_done"
 * frame with the full assembled "text" — there is no single-shot "message"
 * reply frame anymore.
 */

const SETTINGS_KEY = "cortexflow_settings";
const DEFAULT_WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:7432"
).replace(/^https?/, (p) => (p === "https" ? "wss" : "ws"));

// Matches the gateway's actual frames (cortexflow_ai/gateway/websocket.py) —
// every field besides `type` is flat on the top-level object, not nested
// under a `payload` key.
export type WSMessage = {
  type: string;
  text?: string;
  delta?: string;
  message?: string;
  message_id?: string;
  session_id?: string;
  channel?: string;
  version?: string;
  timestamp?: number;
};

type Subscriber = (msg: WSMessage) => void;

const MIN_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

export class ReconnectingWSClient {
  private ws: WebSocket | null = null;
  private readonly path: string;
  private subscribers = new Set<Subscriber>();
  private reconnectDelay = MIN_DELAY_MS;
  private shouldReconnect = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(path: string) {
    this.path = path;
  }

  private getConnectUrl(token?: string): string {
    try {
      const saved = localStorage.getItem(SETTINGS_KEY);
      if (saved) {
        const settings = JSON.parse(saved) as Record<string, Record<string, string>>;
        const wsUrl = settings?.api?.["WebSocket URL"];
        // Settings stores the full URL (e.g. "ws://host:7432/ws") — use it directly.
        if (wsUrl) return token ? `${wsUrl}?token=${encodeURIComponent(token)}` : wsUrl;
      }
    } catch {}
    const url = `${DEFAULT_WS_BASE}${this.path}`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  }

  /** Connect (or reconnect) with an optional bearer token sent as query param. */
  connect(token?: string): void {
    if (typeof window === "undefined") return; // SSR guard
    // Avoid opening a second socket if already open or connecting.
    if (this.ws !== null && this.ws.readyState !== WebSocket.CLOSED) return;

    this.shouldReconnect = true;
    const url = this.getConnectUrl(token);
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectDelay = MIN_DELAY_MS; // reset backoff on success
    };

    this.ws.onmessage = (event: MessageEvent) => {
      let msg: WSMessage;
      try {
        msg = JSON.parse(event.data as string) as WSMessage;
      } catch {
        return; // ignore malformed frames
      }
      this.subscribers.forEach((fn) => fn(msg));
    };

    this.ws.onclose = () => {
      if (this.shouldReconnect) {
        this.reconnectTimer = setTimeout(() => this.connect(token), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, MAX_DELAY_MS);
      }
    };

    this.ws.onerror = () => {
      this.ws?.close(); // triggers onclose → schedules reconnect
    };
  }

  /**
   * Subscribe to incoming messages.
   * Returns an unsubscribe function — call it to clean up (e.g. in useEffect).
   */
  subscribe(fn: Subscriber): () => void {
    this.subscribers.add(fn);
    return () => this.subscribers.delete(fn);
  }

  /**
   * Send a frame to the gateway. Returns false (and drops the frame)
   * if the socket isn't currently open — callers should surface that
   * rather than silently queue, since chat is inherently real-time.
   */
  send(frame: Record<string, unknown>): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(frame));
    return true;
  }

  /** Permanently close the socket and cancel any pending reconnect. */
  disconnect(): void {
    this.shouldReconnect = false;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Singleton — the gateway exposes exactly one WebSocket endpoint.
export const gatewayWS = new ReconnectingWSClient("/ws");
