import { describe, it, expect } from "vitest";
import { voiceStreamWS } from "@/lib/voice-ws";
import { ReconnectingWSClient } from "@/lib/websocket";

describe("voiceStreamWS type", () => {
  it("is an instance of ReconnectingWSClient", () => {
    expect(voiceStreamWS).toBeInstanceOf(ReconnectingWSClient);
  });
});
