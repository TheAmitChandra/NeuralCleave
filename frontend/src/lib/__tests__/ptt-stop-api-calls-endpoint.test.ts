import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient, { stopPtt } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return { ...mod, default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } };
});

const mockedPost = vi.mocked(apiClient.post);

beforeEach(() => {
  mockedPost.mockResolvedValue({ data: { transcript: "hello world", response: "Hi!" } });
});

describe("stopPtt", () => {
  it("calls POST /voice/ptt/stop", async () => {
    await stopPtt();
    expect(mockedPost).toHaveBeenCalledWith("/voice/ptt/stop");
  });

  it("returns transcript and response fields", async () => {
    const result = await stopPtt();
    expect(result.transcript).toBe("hello world");
    expect(result.response).toBe("Hi!");
  });
});
