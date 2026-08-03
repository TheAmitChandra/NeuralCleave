import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { MemoryEntry } from "@/store/memory";

// Mock memory store with empty search query
vi.mock("@/store/memory", () => ({
  useMemoryStore: vi.fn().mockReturnValue({
    searchQuery: "",
    setSearchQuery: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  default: { get: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

// Build 11 fake entries — exceeds PAGE_SIZE=10 so pagination controls appear
function makeEntry(id: number): MemoryEntry {
  return {
    id,
    session_id: "s1",
    content: `Memory entry ${id}`,
    importance_score: 0.5,
    memory_type: "general",
    tags: "",
    created_at: new Date(Date.now() - id * 60000).toISOString(),
    last_accessed_at: new Date().toISOString(),
  };
}
const ELEVEN_ENTRIES = Array.from({ length: 11 }, (_, i) => makeEntry(i + 1));

vi.mock("@tanstack/react-query", async (importActual) => {
  const actual = await importActual<typeof import("@tanstack/react-query")>();
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({
      data: ELEVEN_ENTRIES,
      isLoading: false,
    }),
    useMutation: vi.fn().mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    }),
    useQueryClient: vi.fn().mockReturnValue({ invalidateQueries: vi.fn() }),
  };
});

// Lazy import after mocks are set up
async function renderPage() {
  const { default: MemoryPage } = await import("@/app/(dashboard)/memory/page");
  return render(<MemoryPage />);
}

describe("MemoryPage — pagination", () => {
  it("shows Prev and Next buttons when entries exceed page size", async () => {
    await renderPage();
    expect(screen.getByText("Prev")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("starts on page 1 and advances to page 2 when Next is clicked", async () => {
    await renderPage();
    expect(screen.getByText(/Page 1 of 2/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Next"));
    expect(screen.getByText(/Page 2 of 2/i)).toBeInTheDocument();
  });

  it("Prev button is disabled on first page", async () => {
    await renderPage();
    const prevBtn = screen.getByText("Prev").closest("button") as HTMLButtonElement;
    expect(prevBtn.disabled).toBe(true);
  });
});
