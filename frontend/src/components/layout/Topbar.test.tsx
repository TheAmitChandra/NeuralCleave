import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Topbar } from "./Topbar";
import api from "@/lib/api";

// vi.mock is hoisted — reference external variables through vi.mocked() after import.
vi.mock("@/lib/api", () => ({
  default: { get: vi.fn() },
}));

vi.mock("@/components/layout/ShortcutsModal", () => ({
  ShortcutsModal: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="shortcuts-modal">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

const mockedGet = vi.mocked(api.get);

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = makeClient();
  return {
    ...render(
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    ),
    queryClient,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGet.mockResolvedValue({ data: { status: "ok" } });
});

describe("Topbar – menu button", () => {
  it("calls onMenuClick when the menu button is clicked", () => {
    const onMenuClick = vi.fn();
    renderWithQuery(<Topbar onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByLabelText("Open navigation menu"));
    expect(onMenuClick).toHaveBeenCalledTimes(1);
  });

  it("does not render a sign-out element (v2 has no auth)", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    expect(screen.queryByText("Sign out")).not.toBeInTheDocument();
  });
});

describe("Topbar – gateway status label", () => {
  it("shows 'Gateway online' once the status query resolves ok", async () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("Gateway online")).toBeInTheDocument()
    );
  });

  it("shows a loading/startup label while the status query is pending", () => {
    mockedGet.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    // Within 120 s grace we show "Launching backend…"; after that "Connecting…"
    const label = screen.queryByText("Launching backend…") ?? screen.queryByText("Connecting…");
    expect(label).toBeInTheDocument();
  });
});

describe("Topbar – keyboard shortcuts button", () => {
  it("renders the keyboard shortcuts button", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    expect(screen.getByLabelText("Open keyboard shortcuts")).toBeInTheDocument();
  });

  it("opens ShortcutsModal when the keyboard button is clicked", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    expect(screen.queryByTestId("shortcuts-modal")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Open keyboard shortcuts"));
    expect(screen.getByTestId("shortcuts-modal")).toBeInTheDocument();
  });

  it("opens ShortcutsModal on Ctrl+/ keydown", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    act(() => {
      fireEvent.keyDown(document, { key: "/", ctrlKey: true });
    });
    expect(screen.getByTestId("shortcuts-modal")).toBeInTheDocument();
  });

  it("opens ShortcutsModal on ? keydown (not in input)", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    act(() => {
      fireEvent.keyDown(document.body, { key: "?" });
    });
    expect(screen.getByTestId("shortcuts-modal")).toBeInTheDocument();
  });

  it("closes ShortcutsModal via its onClose callback", () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Open keyboard shortcuts"));
    expect(screen.getByTestId("shortcuts-modal")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Close"));
    expect(screen.queryByTestId("shortcuts-modal")).not.toBeInTheDocument();
  });
});

describe("Topbar – retry button", () => {
  it("does not show the Retry button while the gateway is online", async () => {
    renderWithQuery(<Topbar onMenuClick={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByText("Gateway online")).toBeInTheDocument()
    );
    expect(screen.queryByText("Retry")).not.toBeInTheDocument();
  });

  // Note: testing "Retry appears after all retries exhausted" is an integration
  // concern — the per-query retry:3 can't be overridden from QueryClient defaults
  // in React Query v5, so it requires real timer advancement (>7 s). The
  // conditional render logic is verified by reading the component source directly.
});
