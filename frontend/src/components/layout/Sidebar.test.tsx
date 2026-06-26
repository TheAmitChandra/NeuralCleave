import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Sidebar } from "./Sidebar";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("Sidebar (mobile drawer)", () => {
  it("renders all nav items, including Channels", () => {
    render(<Sidebar open={false} onClose={vi.fn()} />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
    expect(screen.getByText("Channels")).toBeInTheDocument();
    expect(screen.getByText("Observability")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("does not render enterprise-only nav items", () => {
    render(<Sidebar open={false} onClose={vi.fn()} />);
    expect(screen.queryByText("Agents")).not.toBeInTheDocument();
    expect(screen.queryByText("Workflows")).not.toBeInTheDocument();
    expect(screen.queryByText("Security")).not.toBeInTheDocument();
  });

  it("hides the mobile backdrop when closed", () => {
    const { container } = render(<Sidebar open={false} onClose={vi.fn()} />);
    expect(container.querySelector(".bg-black\\/60")).toBeNull();
  });

  it("shows a clickable mobile backdrop when open, and calls onClose", () => {
    const onClose = vi.fn();
    const { container } = render(<Sidebar open={true} onClose={onClose} />);
    const backdrop = container.querySelector(".bg-black\\/60");
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("translates the drawer off-screen when closed, on-screen when open", () => {
    const { rerender, container } = render(
      <Sidebar open={false} onClose={vi.fn()} />
    );
    expect(container.querySelector("aside")?.className).toContain(
      "-translate-x-full"
    );

    rerender(<Sidebar open={true} onClose={vi.fn()} />);
    expect(container.querySelector("aside")?.className).toContain(
      "translate-x-0"
    );
  });

  it("calls onClose when a nav link is clicked", () => {
    const onClose = vi.fn();
    render(<Sidebar open={true} onClose={onClose} />);
    fireEvent.click(screen.getByText("Memory"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
