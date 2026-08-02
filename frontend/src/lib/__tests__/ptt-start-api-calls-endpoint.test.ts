import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, startPtt } from "@/lib/api";

beforeEach(() => {
  vi.spyOn(apiClient, "post").mockResolvedValue({ data: { started: true } } as never);
});

afterEach(() => { vi.restoreAllMocks(); });

describe("startPtt", () => {
  it("calls POST /voice/ptt/start", async () => {
    await startPtt();
    expect(apiClient.post).toHaveBeenCalledWith("/voice/ptt/start");
  });

  it("returns started field", async () => {
    const result = await startPtt();
    expect(result.started).toBe(true);
  });
});
