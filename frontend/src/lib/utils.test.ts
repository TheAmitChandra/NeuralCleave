import { describe, it, expect } from "vitest";
import { cn } from "./utils";

describe("cn (class name merger)", () => {
  it("returns a single class name unchanged", () => {
    expect(cn("foo")).toBe("foo");
  });

  it("merges multiple class names with a space", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("deduplicates conflicting Tailwind classes (last wins)", () => {
    // twMerge resolves conflicts — padding-4 should win over padding-2
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("removes falsy values", () => {
    expect(cn("foo", false, undefined, null, "bar")).toBe("foo bar");
  });

  it("supports conditional object syntax", () => {
    expect(cn({ hidden: true, block: false })).toBe("hidden");
  });

  it("combines conditionals and plain strings", () => {
    expect(cn("base", { active: true, disabled: false }, "extra")).toBe(
      "base active extra"
    );
  });

  it("returns an empty string when no classes provided", () => {
    expect(cn()).toBe("");
  });

  it("handles array inputs", () => {
    expect(cn(["foo", "bar"])).toBe("foo bar");
  });

  it("resolves text-color conflicts correctly", () => {
    expect(cn("text-red-500", "text-blue-500")).toBe("text-blue-500");
  });

  it("resolves bg-color conflicts correctly", () => {
    expect(cn("bg-white", "bg-slate-900")).toBe("bg-slate-900");
  });
});
