import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { voiceStreamWS, onAudioReply } from "@/lib/voice-ws";
import { gatewayWS } from "@/lib/websocket";

describe("onAudioReply does not use gatewayWS", () => {
  let gatewaySpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.spyOn(voiceStreamWS, "subscribeBinary").mockReturnValue(() => {});
    gatewaySpy = vi.spyOn(gatewayWS, "subscribeBinary").mockReturnValue(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not call gatewayWS.subscribeBinary()", () => {
    onAudioReply(vi.fn());
    expect(gatewaySpy).not.toHaveBeenCalled();
  });
});
