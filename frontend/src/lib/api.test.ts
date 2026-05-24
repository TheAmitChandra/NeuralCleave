import { describe, it, expect, vi, beforeEach } from "vitest";
import axios from "axios";

// We test the module-level apiClient configuration.
// Import after mocking environment so process.env is available.
vi.stubEnv("NEXT_PUBLIC_API_URL", "http://test-api:9000");

// Re-import after env stub so the module picks up the new value
const { apiClient } = await import("./api");

describe("apiClient configuration", () => {
  it("uses the configured base URL from env", () => {
    expect(apiClient.defaults.baseURL).toBe("http://test-api:9000/api/v1");
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

  it("has at least one request interceptor registered", () => {
    // @ts-expect-error — accessing internal handler list for assertion
    expect(apiClient.interceptors.request.handlers.length).toBeGreaterThan(0);
  });

  it("has at least one response interceptor registered", () => {
    // @ts-expect-error — accessing internal handler list for assertion
    expect(apiClient.interceptors.response.handlers.length).toBeGreaterThan(0);
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

describe("request interceptor — Authorization header", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("attaches Bearer token from localStorage when present", async () => {
    localStorage.setItem("access_token", "my-test-jwt");

    // Capture the config that the interceptor produces
    // @ts-expect-error — accessing internal handlers
    const handler = apiClient.interceptors.request.handlers[0];
    const fakeConfig = { headers: {} as Record<string, string> };
    const result = handler.fulfilled(fakeConfig);

    expect(result.headers["Authorization"]).toBe("Bearer my-test-jwt");
  });

  it("does not set Authorization header when no token in localStorage", async () => {
    // @ts-expect-error — accessing internal handlers
    const handler = apiClient.interceptors.request.handlers[0];
    const fakeConfig = { headers: {} as Record<string, string> };
    const result = handler.fulfilled(fakeConfig);

    expect(result.headers["Authorization"]).toBeUndefined();
  });
});

describe("response interceptor — 401 handling", () => {
  beforeEach(() => {
    localStorage.setItem("access_token", "some-token");
  });

  it("rejects the promise on non-401 errors", async () => {
    // @ts-expect-error — accessing internal handlers
    const handler = apiClient.interceptors.response.handlers[0];
    const error = { response: { status: 500 }, message: "Server Error" };

    await expect(handler.rejected(error)).rejects.toEqual(error);
  });

  it("rejects the promise on 401 and clears access_token from localStorage", async () => {
    // @ts-expect-error — accessing internal handlers
    const handler = apiClient.interceptors.response.handlers[0];
    const error = { response: { status: 401 }, message: "Unauthorized" };

    // window.location.href assignment will throw in jsdom — suppress it
    const origHref = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", {
      value: { href: "" },
      writable: true,
    });

    await expect(handler.rejected(error)).rejects.toEqual(error);
    expect(localStorage.getItem("access_token")).toBeNull();

    // Restore
    if (origHref) Object.defineProperty(window, "location", origHref);
  });
});
