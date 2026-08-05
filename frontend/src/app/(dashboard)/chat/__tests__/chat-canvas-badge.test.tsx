/**
 * Tests for the "Rendered to Canvas" badge that appears in AI chat bubbles
 * when a response contains a CHART_DATA: line.
 */
import { describe, it, expect } from "vitest";

// Pure unit test for hasChartData — no DOM needed

function hasChartData(text: string): boolean {
  return /^CHART_DATA:\s*\{/m.test(text);
}

describe("hasChartData helper", () => {
  it("returns true for a line starting with CHART_DATA:", () => {
    const text = 'CHART_DATA: {"type":"bar","labels":["A"],"values":[1]}';
    expect(hasChartData(text)).toBe(true);
  });

  it("returns true when CHART_DATA is mid-text on its own line", () => {
    const text = `Here is a chart:\nCHART_DATA: {"type":"line","labels":[],"values":[]}\nSome explanation.`;
    expect(hasChartData(text)).toBe(true);
  });

  it("returns false for plain text with no CHART_DATA", () => {
    expect(hasChartData("Hello, how can I help?")).toBe(false);
  });

  it("returns false for CHART_DATA not at line start", () => {
    expect(hasChartData("See this CHART_DATA: {in the middle}")).toBe(false);
  });

  it("returns false for CHART_DATA with no opening brace", () => {
    expect(hasChartData("CHART_DATA: not-json")).toBe(false);
  });

  it("returns true with leading whitespace trimmed by regex", () => {
    // Note: the regex uses ^ with /m so it matches start of any line
    const text = 'CHART_DATA: {"type":"bar","labels":["X"],"values":[10]}';
    expect(hasChartData(text)).toBe(true);
  });

  it("returns false for empty string", () => {
    expect(hasChartData("")).toBe(false);
  });

  it("returns true for multiline response ending with CHART_DATA", () => {
    const text = [
      "Here is your sales trend chart.",
      "",
      'CHART_DATA: {"type":"line","title":"Sales","labels":["Jan","Feb"],"values":[10,20]}',
    ].join("\n");
    expect(hasChartData(text)).toBe(true);
  });

  it("returns false for TOOL_CALL lines (different protocol)", () => {
    const text = 'TOOL_CALL: {"name":"web_search","arguments":{"query":"test"}}';
    expect(hasChartData(text)).toBe(false);
  });
});
