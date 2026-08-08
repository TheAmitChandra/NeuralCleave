import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sidebar } from "@/components/layout/Sidebar";

vi.mock("next/navigation", () => ({ usePathname: vi.fn().mockReturnValue("/chat") }));
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn().mockReturnValue({ data: { status: "ok", version: "2.1.5" } }),
}));
vi.mock("@/lib/api", () => ({
  default: { get: vi.fn().mockResolvedValue({ data: { status: "ok" } }) },
}));
vi.mock("@/lib/utils", () => ({ cn: (...args: string[]) => args.filter(Boolean).join(" ") }));

describe("Sidebar", () => {
  it("includes a Voice navigation link", () => {
    render(<Sidebar open={false} onClose={vi.fn()} />);
    expect(screen.getByRole("link", { name: /Voice/i })).toBeInTheDocument();
  });
});
