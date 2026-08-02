import { describe, it, expect, vi, afterEach } from "vitest";
import apiClient, { getVoiceDevices } from "../api";

afterEach(() => vi.restoreAllMocks());

describe("getVoiceDevices response – input list", () => {
  it("returns the input device array from the API response", async () => {
    const input = [{ index: 0, name: "Built-in Mic", channels: 1, sample_rate: 44100, is_default: true }];
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { input, output: [], active: { input_device: null, output_device: null } },
    });
    const result = await getVoiceDevices();
    expect(result.input).toEqual(input);
  });
});
