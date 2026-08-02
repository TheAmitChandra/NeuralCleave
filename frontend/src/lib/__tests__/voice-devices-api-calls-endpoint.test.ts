import { describe, it, expect, vi, afterEach } from "vitest";
import apiClient, { getVoiceDevices } from "../api";

const EMPTY_RESPONSE = {
  input: [],
  output: [],
  active: { input_device: null, output_device: null },
};

afterEach(() => vi.restoreAllMocks());

describe("getVoiceDevices", () => {
  it("calls GET /voice/devices on the api client", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: EMPTY_RESPONSE });
    await getVoiceDevices();
    expect(apiClient.get).toHaveBeenCalledWith("/voice/devices");
  });
});
