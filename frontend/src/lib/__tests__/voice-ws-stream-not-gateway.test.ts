import { describe, it, expect } from "vitest";
import { voiceStreamWS } from "@/lib/voice-ws";
import { gatewayWS } from "@/lib/websocket";

describe("voiceStreamWS identity", () => {
  it("is a different instance from the shared gatewayWS", () => {
    expect(voiceStreamWS).not.toBe(gatewayWS);
  });
});
