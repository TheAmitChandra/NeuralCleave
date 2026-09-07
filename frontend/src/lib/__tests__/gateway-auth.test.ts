import { afterEach, describe, expect, it } from "vitest";
import { getGatewayWSUrl } from "../websocket";
import { apiClient } from "../api";

afterEach(() => localStorage.clear());

describe("configured gateway credentials", () => {
  it("uses distinct authenticated socket paths behind a proxy", () => {
    localStorage.setItem("NeuralCleave_settings", JSON.stringify({ api: {
      "WebSocket URL": "wss://gateway.example/personal/ws?mode=live",
      "Gateway API Key": "a +/&=b",
    } }));
    for (const path of ["/ws", "/ws/voice", "/ws/terminal", "/ws/canvas"]) {
      const url = new URL(getGatewayWSUrl(path));
      expect(url.pathname).toBe(`/personal${path}`);
      expect(url.searchParams.get("token")).toBe("a +/&=b");
      expect(url.searchParams.get("mode")).toBe("live");
      expect(url.searchParams.get("client_id")).toBeTruthy();
    }
  });

  it("rereads credentials and keeps browser identity on reconnect", () => {
    const first = new URL(getGatewayWSUrl("/ws"));
    localStorage.setItem("NeuralCleave_settings", JSON.stringify({ api: { "Gateway API Key": "new" } }));
    const next = new URL(getGatewayWSUrl("/ws"));
    expect(next.searchParams.get("client_id")).toBe(first.searchParams.get("client_id"));
    expect(next.searchParams.get("token")).toBe("new");
    expect(new URL(getGatewayWSUrl("/ws", "explicit")).searchParams.get("token")).toBe("explicit");
  });

  it("adds and removes the REST key on actual outgoing requests", async () => {
    const headers: unknown[] = [];
    // Axios' custom adapter observes the request after interceptors without network I/O.
    for (const key of ["first", "second", ""]) {
      localStorage.setItem("NeuralCleave_settings", JSON.stringify({ api: { "Gateway API Key": key } }));
      await apiClient.get("/status", { adapter: async (config) => {
        headers.push(config.headers.get("X-API-Key"));
        return { data: {}, status: 200, statusText: "OK", headers: {}, config };
      } });
    }
    expect(headers).toEqual(["first", "second", undefined]);
  });
});
