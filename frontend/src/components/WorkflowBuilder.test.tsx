import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

// Mock React Flow — it requires canvas/browser APIs not available in jsdom
vi.mock("reactflow", () => ({
  default: ({ children }: { children?: React.ReactNode }) =>
    React.createElement("div", { "data-testid": "react-flow" }, children),
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  useNodesState: (initial: unknown[]) => {
    const [nodes, setNodes] = React.useState(initial);
    const onNodesChange = vi.fn();
    return [nodes, setNodes, onNodesChange];
  },
  useEdgesState: (initial: unknown[]) => {
    const [edges, setEdges] = React.useState(initial);
    const onEdgesChange = vi.fn();
    return [edges, setEdges, onEdgesChange];
  },
  addEdge: (params: unknown, edges: unknown[]) => [...edges, params],
}));

// Mock the API client
const mockPatch = vi.fn();
vi.mock("@/lib/api", () => ({
  default: { patch: mockPatch },
}));

// Import after mocks are in place
const { WorkflowBuilder } = await import("./WorkflowBuilder");

describe("WorkflowBuilder", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("renders without throwing", () => {
      expect(() => render(React.createElement(WorkflowBuilder, {}))).not.toThrow();
    });

    it("renders the React Flow canvas container", () => {
      render(React.createElement(WorkflowBuilder, {}));
      expect(screen.getByTestId("react-flow")).toBeDefined();
    });

    it("renders all four palette node types", () => {
      render(React.createElement(WorkflowBuilder, {}));
      expect(screen.getByText("Start")).toBeDefined();
      expect(screen.getByText("Task")).toBeDefined();
      expect(screen.getByText("Condition")).toBeDefined();
      expect(screen.getByText("End")).toBeDefined();
    });

    it("renders the 'Node Palette' palette header", () => {
      render(React.createElement(WorkflowBuilder, {}));
      expect(screen.getByText("Node Palette")).toBeDefined();
    });

    it("renders the Save DAG button when workflowId is provided", () => {
      render(React.createElement(WorkflowBuilder, { workflowId: "wf-abc" }));
      expect(screen.getByText("Save DAG")).toBeDefined();
    });

    it("renders 'Select a workflow to save' when no workflowId is provided", () => {
      render(React.createElement(WorkflowBuilder, {}));
      expect(screen.getByText("Select a workflow to save")).toBeDefined();
    });
  });

  describe("save behaviour", () => {
    it("calls API patch with dag_definition when Save DAG is clicked", async () => {
      mockPatch.mockResolvedValueOnce({ data: { ok: true } });
      const onSaved = vi.fn();

      render(
        React.createElement(WorkflowBuilder, {
          workflowId: "wf-123",
          onSaved,
        })
      );

      fireEvent.click(screen.getByText("Save DAG"));

      await waitFor(() => {
        expect(mockPatch).toHaveBeenCalledWith("/workflows/wf-123/dag", {
          dag_definition: expect.objectContaining({
            nodes: expect.any(Array),
            edges: expect.any(Array),
          }),
        });
      });
    });

    it("calls onSaved callback after successful save", async () => {
      mockPatch.mockResolvedValueOnce({ data: { ok: true } });
      const onSaved = vi.fn();

      render(
        React.createElement(WorkflowBuilder, {
          workflowId: "wf-123",
          onSaved,
        })
      );

      fireEvent.click(screen.getByText("Save DAG"));

      await waitFor(() => {
        expect(onSaved).toHaveBeenCalledOnce();
      });
    });

    it("shows 'Saved ✓' text after a successful save", async () => {
      mockPatch.mockResolvedValueOnce({ data: { ok: true } });

      render(
        React.createElement(WorkflowBuilder, { workflowId: "wf-xyz" })
      );

      fireEvent.click(screen.getByText("Save DAG"));

      await waitFor(() => {
        expect(screen.getByText("Saved ✓")).toBeDefined();
      });
    });

    it("shows 'Save failed' text when the API call fails", async () => {
      mockPatch.mockRejectedValueOnce(new Error("Network error"));

      render(
        React.createElement(WorkflowBuilder, { workflowId: "wf-xyz" })
      );

      fireEvent.click(screen.getByText("Save DAG"));

      await waitFor(() => {
        expect(screen.getByText("Save failed")).toBeDefined();
      });
    });

    it("does not call API when workflowId is not provided", async () => {
      render(React.createElement(WorkflowBuilder, {}));

      // No "Save DAG" button is rendered without workflowId — verify API not called
      await new Promise((r) => setTimeout(r, 50));
      expect(mockPatch).not.toHaveBeenCalled();
    });
  });
});
