import { describe, it, expect, vi, afterEach } from "vitest";
import { voiceStreamWS, onAudioReply } from "@/lib/voice-ws";
import { gatewayWS } from "@/lib/websocket";

describe("onAudioReply does not use gatewayWS", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not call gatewayWS.subscribeBinary()", () => {
    vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(() => {});
    const gatewaySpy = vi.spyOn(gatewayWS, "subscribeBinary").mockReturnValue(() => {});
    onAudioReply(vi.fn());
    expect(gatewaySpy).not.toHaveBeenCalled();
  });
});
