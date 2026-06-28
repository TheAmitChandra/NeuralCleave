/**
 * CortexFlow-AI WebSocket client
 *
 * Provides an auto-reconnecting WebSocket connection to the gateway's single
 * chat/event endpoint at /ws — see cortexflow_ai/gateway/websocket.py for the
 * message protocol (hello/ping/pong/subscribe/message/error frames).
 */

const WS_BASE = (
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:7432"
).replace(/^https?/, (p) => (p === "https" ? "wss" : "ws"));

// Matches the gateway's actual frames (cortexflow_ai/gateway/websocket.py) —
// every field besides `type` is flat on the top-level object, not nested
// under a `payload` key.
export type WSMessage = {
  type: string;
  text?: string;
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
  private readonly url: string;
  private subscribers = new Set<Subscriber>();
  private reconnectDelay = MIN_DELAY_MS;
  private shouldReconnect = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(path: string) {
    this.url = `${WS_BASE}${path}`;
  }

  /** Connect (or reconnect) with an optional bearer token sent as query param. */
  connect(token?: string): void {
    if (typeof window === "undefined") return; // SSR guard

    this.shouldReconnect = true;
    const url = token ? `${this.url}?token=${encodeURIComponent(token)}` : this.url;
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
