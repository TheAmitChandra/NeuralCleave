import { describe, it, expect, vi, afterEach } from "vitest";
import apiClient, { getVoiceDevices } from "../api";

afterEach(() => vi.restoreAllMocks());

describe("getVoiceDevices response – active devices", () => {
  it("returns the active input_device and output_device from the API response", async () => {
    const active = { input_device: "Built-in Mic", output_device: "Headphones" };
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { input: [], output: [], active },
    });
    const result = await getVoiceDevices();
    expect(result.active).toEqual(active);
  });
});
