import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient, { startPtt } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/api")>();
  return { ...mod, default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } };
});

const mockedPost = vi.mocked(apiClient.post);

beforeEach(() => {
  mockedPost.mockResolvedValue({ data: { started: true } });
});

describe("startPtt", () => {
  it("calls POST /voice/ptt/start", async () => {
    await startPtt();
    expect(mockedPost).toHaveBeenCalledWith("/voice/ptt/start");
  });

  it("returns started field", async () => {
    const result = await startPtt();
    expect(result.started).toBe(true);
  });
});
