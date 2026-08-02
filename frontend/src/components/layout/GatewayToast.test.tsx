import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GatewayToast } from "./GatewayToast";

/**
 * GatewayToast uses `enabled: false` on its own query so it only reads
 * from the cache.  To test the transition logic we prime the cache
 * directly via queryClient.setQueryData and then update it to simulate
 * online ↔ offline transitions.
 */
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithClient(client: QueryClient) {
  return render(
    <QueryClientProvider client={client}>
      <GatewayToast />
    </QueryClientProvider>
  );
}

describe("GatewayToast", () => {
  it("renders nothing on initial mount (no transition yet)", () => {
    const client = makeClient();
    const { container } = renderWithClient(client);
    // No toast should be visible before any transition.
    expect(container.firstChild).toBeNull();
  });

  it("shows 'Gateway is online' toast when gateway comes online", async () => {
    const client = makeClient();
    // Baseline: offline (no cache entry)
    renderWithClient(client);

    // Simulate gateway coming online.
    client.setQueryData(["gateway-status"], { status: "ok" });

    await waitFor(() =>
      expect(screen.getByText("NeuralCleave is ready")).toBeInTheDocument()
    );
  });

  it("shows 'Gateway connection lost' toast when gateway goes offline", async () => {
    const client = makeClient();
    // Baseline: online
    client.setQueryData(["gateway-status"], { status: "ok" });
    renderWithClient(client);

    // Simulate going offline by setting a non-ok status.
    client.setQueryData(["gateway-status"], { status: "error" });

    await waitFor(() =>
      expect(screen.getByText("Gateway connection lost")).toBeInTheDocument()
    );
  });

  it("does not show a toast if the gateway was already online at mount", async () => {
    const client = makeClient();
    // The query cache already has a good status before the component mounts.
    client.setQueryData(["gateway-status"], { status: "ok" });

    const { container } = renderWithClient(client);

    // Wait a tick and confirm no toast appeared.
    await new Promise((r) => setTimeout(r, 50));
    // No toast shown for the initial state — only transitions trigger it.
    expect(screen.queryByText("Gateway is online")).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });
});
