import { describe, it, expect, beforeEach } from "vitest";
import { act } from "@testing-library/react";
import { useAuthStore } from "./auth";

// Zustand with persist middleware uses localStorage — jsdom provides it.
// Reset store state between tests to avoid cross-test pollution.
function resetStore() {
  useAuthStore.setState({ accessToken: null, user: null });
}

const MOCK_USER = {
  id: "user-123",
  email: "agent@cortexflow.ai",
  full_name: "Agent One",
  role: "operator",
};

const MOCK_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock.signature";

describe("useAuthStore", () => {
  beforeEach(() => {
    resetStore();
    localStorage.clear();
  });

  it("starts with null accessToken and user", () => {
    const state = useAuthStore.getState();
    expect(state.accessToken).toBeNull();
    expect(state.user).toBeNull();
  });

  it("setAuth stores token and user", () => {
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe(MOCK_TOKEN);
    expect(state.user).toEqual(MOCK_USER);
  });

  it("setAuth overwrites previous auth state", () => {
    act(() => {
      useAuthStore.getState().setAuth("old-token", { ...MOCK_USER, email: "old@example.com" });
    });
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });

    const state = useAuthStore.getState();
    expect(state.accessToken).toBe(MOCK_TOKEN);
    expect(state.user?.email).toBe("agent@cortexflow.ai");
  });

  it("logout clears accessToken", () => {
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });
    act(() => {
      useAuthStore.getState().logout();
    });

    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("logout clears user", () => {
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });
    act(() => {
      useAuthStore.getState().logout();
    });

    expect(useAuthStore.getState().user).toBeNull();
  });

  it("user object has all expected fields after setAuth", () => {
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });

    const { user } = useAuthStore.getState();
    expect(user?.id).toBe("user-123");
    expect(user?.email).toBe("agent@cortexflow.ai");
    expect(user?.full_name).toBe("Agent One");
    expect(user?.role).toBe("operator");
  });

  it("logout can be called on already-cleared state without error", () => {
    expect(() => {
      act(() => {
        useAuthStore.getState().logout();
      });
    }).not.toThrow();
  });

  it("setAuth accepts different roles", () => {
    const roles = ["admin", "developer", "operator", "viewer", "auditor"] as const;
    for (const role of roles) {
      act(() => {
        useAuthStore.getState().setAuth(MOCK_TOKEN, { ...MOCK_USER, role });
      });
      expect(useAuthStore.getState().user?.role).toBe(role);
    }
  });

  it("accessToken is a string after setAuth", () => {
    act(() => {
      useAuthStore.getState().setAuth(MOCK_TOKEN, MOCK_USER);
    });
    expect(typeof useAuthStore.getState().accessToken).toBe("string");
  });
});
