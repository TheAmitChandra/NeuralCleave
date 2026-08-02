import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, stopPtt } from "@/lib/api";

beforeEach(() => {
  vi.spyOn(apiClient, "post").mockResolvedValue({ data: { transcript: "hello world", response: "Hi!" } } as never);
});

afterEach(() => { vi.restoreAllMocks(); });

describe("stopPtt", () => {
  it("calls POST /voice/ptt/stop", async () => {
    await stopPtt();
    expect(apiClient.post).toHaveBeenCalledWith("/voice/ptt/stop");
  });

  it("returns transcript and response fields", async () => {
    const result = await stopPtt();
    expect(result.transcript).toBe("hello world");
    expect(result.response).toBe("Hi!");
  });
});
