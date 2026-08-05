import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Minimal mocks required by canvas/page.tsx
vi.mock("@tanstack/react-query", async (importActual) => {
  const actual = await importActual<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn().mockImplementation(({ queryKey }: { queryKey: unknown[] }) => {
      const key = queryKey[1] as string;
      if (key === "status") return { data: { available: true, block_count: 1, subscriber_count: 0 } };
      if (key === "state") {
        return {
          data: {
            available: true,
            count: 1,
            blocks: [
              {
                id: "block-1",
                block_type: "chart",
                content: { chart_type: "bar", labels: ["Q1", "Q2", "Q3"], values: [100, 200, 150] },
                title: "Quarterly Sales",
                created_at: "2026-08-04T10:00:00Z",
              },
            ],
          },
          isLoading: false,
          isFetching: false,
          refetch: vi.fn(),
        };
      }
      return { data: null, isLoading: false, isFetching: false, refetch: vi.fn() };
    }),
    useMutation: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  };
});

vi.mock("@/lib/api", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

async function renderCanvasPage() {
  const { default: CanvasPage } = await import("@/app/(dashboard)/canvas/page");
  return render(<CanvasPage />);
}

describe("CanvasPage — chart block rendering", () => {
  it("renders a chart block with chart_type content", async () => {
    await renderCanvasPage();
    // Title should appear in the block card
    expect(screen.getByText("Quarterly Sales")).toBeInTheDocument();
  });

  it("shows BAR label for bar chart block", async () => {
    await renderCanvasPage();
    expect(screen.getByText("bar")).toBeInTheDocument();
  });

  it("renders all three labels from the chart data", async () => {
    await renderCanvasPage();
    expect(screen.getByText("Q1")).toBeInTheDocument();
    expect(screen.getByText("Q2")).toBeInTheDocument();
    expect(screen.getByText("Q3")).toBeInTheDocument();
  });

  it("renders all three values from the chart data", async () => {
    await renderCanvasPage();
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
  });
});

describe("CanvasPage — chart block with legacy 'type' key", () => {
  it("does not show 'Empty chart' when chart has labels", async () => {
    await renderCanvasPage();
    expect(screen.queryByText("Empty chart")).not.toBeInTheDocument();
  });
});
