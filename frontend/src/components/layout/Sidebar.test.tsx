import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Sidebar } from "./Sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { status: "ok", version: "2.0.0" } }),
  },
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("Sidebar (mobile drawer)", () => {
  it("renders all nav items, including Channels", () => {
    renderWithQuery(<Sidebar open={false} onClose={vi.fn()} />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("Channels")).toBeInTheDocument();
    expect(screen.getByText("Observability")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("does not render enterprise-only nav items", () => {
    renderWithQuery(<Sidebar open={false} onClose={vi.fn()} />);
    expect(screen.queryByText("Agents")).not.toBeInTheDocument();
    expect(screen.queryByText("Workflows")).not.toBeInTheDocument();
    expect(screen.queryByText("Security")).not.toBeInTheDocument();
  });

  it("hides the mobile backdrop when closed", () => {
    const { container } = renderWithQuery(<Sidebar open={false} onClose={vi.fn()} />);
    expect(container.querySelector(".bg-black\\/60")).toBeNull();
  });

  it("shows a clickable mobile backdrop when open, and calls onClose", () => {
    const onClose = vi.fn();
    const { container } = renderWithQuery(<Sidebar open={true} onClose={onClose} />);
    const backdrop = container.querySelector(".bg-black\\/60");
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("translates the drawer off-screen when closed, on-screen when open", () => {
    const queryClient = new QueryClient();
    const { rerender, container } = render(
      <QueryClientProvider client={queryClient}>
        <Sidebar open={false} onClose={vi.fn()} />
      </QueryClientProvider>
    );
    expect(container.querySelector("aside")?.className).toContain(
      "-translate-x-full"
    );

    rerender(
      <QueryClientProvider client={queryClient}>
        <Sidebar open={true} onClose={vi.fn()} />
      </QueryClientProvider>
    );
    expect(container.querySelector("aside")?.className).toContain(
      "translate-x-0"
    );
  });

  it("calls onClose when a nav link is clicked", () => {
    const onClose = vi.fn();
    renderWithQuery(<Sidebar open={true} onClose={onClose} />);
    fireEvent.click(screen.getByText("Memory"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows the real gateway version from /status instead of a hardcoded string", async () => {
    renderWithQuery(<Sidebar open={false} onClose={vi.fn()} />);
    expect(await screen.findByText("CortexFlow-AI v2.0.0")).toBeInTheDocument();
  });
});
