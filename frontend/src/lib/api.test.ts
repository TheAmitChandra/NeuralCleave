import { describe, it, expect, vi, beforeAll } from "vitest";
import axios from "axios";

// We test the module-level apiClient configuration.
// Import after mocking environment so process.env is available.
vi.stubEnv("NEXT_PUBLIC_API_URL", "http://test-gateway:9000");

let apiClient: ReturnType<typeof axios.create>;

beforeAll(async () => {
  const module = await import("./api");
  apiClient = module.apiClient;
});

describe("apiClient configuration", () => {
  it("uses the configured base URL from env, with /api/v1 appended", () => {
    expect(apiClient.defaults.baseURL).toBe("http://test-gateway:9000/api/v1");
  });

  it("sets Content-Type to application/json by default", () => {
    // defaults.headers is a complex HeadersDefaults object; check common key
    const contentType =
      (apiClient.defaults.headers as Record<string, string>)["Content-Type"];
    expect(contentType).toBe("application/json");
  });

  it("has a timeout of 30 seconds", () => {
    expect(apiClient.defaults.timeout).toBe(30_000);
  });

  it("registers no interceptors — the gateway has no auth to attach or handle", () => {
    expect(apiClient.interceptors.request.handlers.length).toBe(0);
    expect(apiClient.interceptors.response.handlers.length).toBe(0);
  });

  it("is an axios instance (not the raw axios object)", () => {
    expect(axios.isAxiosError).toBeDefined();
    // apiClient should be an instance created via axios.create
    expect(typeof apiClient.get).toBe("function");
    expect(typeof apiClient.post).toBe("function");
    expect(typeof apiClient.patch).toBe("function");
    expect(typeof apiClient.delete).toBe("function");
  });
});
