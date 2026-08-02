import { describe, it, expect, vi, afterEach } from "vitest";
import apiClient, { getVoiceDevices } from "../api";

afterEach(() => vi.restoreAllMocks());

describe("getVoiceDevices response – output list", () => {
  it("returns the output device array from the API response", async () => {
    const output = [{ index: 1, name: "Headphones", channels: 2, sample_rate: 48000, is_default: false }];
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { input: [], output, active: { input_device: null, output_device: null } },
    });
    const result = await getVoiceDevices();
    expect(result.output).toEqual(output);
  });
});
