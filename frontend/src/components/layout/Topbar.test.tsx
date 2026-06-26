import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Topbar } from "./Topbar";

vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { status: "ok" } }),
  },
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe("Topbar (mobile menu button)", () => {
  it("renders a menu button that calls onMenuClick", () => {
    const onMenuClick = vi.fn();
    renderWithQuery(<Topbar onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByLabelText("Open navigation menu"));
    expect(onMenuClick).toHaveBeenCalledTimes(1);
  });

  it("renders without a user/logout block — v2 has no auth", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    expect(screen.queryByText("Sign out")).not.toBeInTheDocument();
  });
});
