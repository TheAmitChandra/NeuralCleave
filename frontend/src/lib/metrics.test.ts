import { describe, it, expect } from "vitest";
import { sumMetric, avgHistogram, tokensByModel, type MetricsSnapshot } from "./metrics";

const snapshot: MetricsSnapshot = {
  messages_total: {
    type: "counter",
    description: "Total inbound messages",
    values: { "channel=telegram": 5, "channel=discord": 2 },
  },
  generation_latency_ms: {
    type: "histogram",
    description: "LLM generation latency",
    values: {
      "model=gemini-2.0-flash": { sum: 825, count: 3, buckets: [] },
      "model=claude-opus-4-8": { sum: 1200, count: 1, buckets: [] },
    },
  },
  active_sessions: {
    type: "gauge",
    description: "Active sessions",
    values: { "": 4 },
  },
  tokens_total: {
    type: "counter",
    description: "Tokens consumed",
    values: {
      "direction=input,model=gemini-2.0-flash": 120,
      "direction=output,model=gemini-2.0-flash": 45,
      "direction=input,model=claude-opus-4-8": 300,
      "direction=output,model=claude-opus-4-8": 90,
    },
  },
};

describe("sumMetric", () => {
  it("sums a counter across all label combinations", () => {
    expect(sumMetric(snapshot, "messages_total")).toBe(7);
  });

  it("reads an unlabelled gauge value", () => {
    expect(sumMetric(snapshot, "active_sessions")).toBe(4);
  });

  it("returns 0 for a missing metric", () => {
    expect(sumMetric(snapshot, "does_not_exist")).toBe(0);
  });

  it("returns 0 for a histogram (wrong type)", () => {
    expect(sumMetric(snapshot, "generation_latency_ms")).toBe(0);
  });

  it("returns 0 when snapshot is undefined", () => {
    expect(sumMetric(undefined, "messages_total")).toBe(0);
  });
});

describe("avgHistogram", () => {
  it("averages sum/count across all label combinations", () => {
    // (825 + 1200) / (3 + 1) = 506.25
    expect(avgHistogram(snapshot, "generation_latency_ms")).toBe(506.25);
  });

  it("returns null for a missing metric", () => {
    expect(avgHistogram(snapshot, "does_not_exist")).toBeNull();
  });

  it("returns null for a counter (wrong type)", () => {
    expect(avgHistogram(snapshot, "messages_total")).toBeNull();
  });
});

describe("tokensByModel", () => {
  it("groups input/output tokens by model", () => {
    const rows = tokensByModel(snapshot);
    expect(rows).toHaveLength(2);
    expect(rows.find((r) => r.model === "gemini-2.0-flash")).toEqual({
      model: "gemini-2.0-flash",
      input: 120,
      output: 45,
    });
    expect(rows.find((r) => r.model === "claude-opus-4-8")).toEqual({
      model: "claude-opus-4-8",
      input: 300,
      output: 90,
    });
  });

  it("sorts rows by total tokens descending", () => {
    const rows = tokensByModel(snapshot);
    expect(rows[0].model).toBe("claude-opus-4-8"); // 390 > 165
  });

  it("returns an empty array when tokens_total is absent", () => {
    expect(tokensByModel({})).toEqual([]);
  });

  it("returns an empty array when snapshot is undefined", () => {
    expect(tokensByModel(undefined)).toEqual([]);
  });
});
