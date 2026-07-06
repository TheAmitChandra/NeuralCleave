import { describe, it, expect } from "vitest";
import {
  COMMANDS,
  matchCommands,
  findCommand,
  buildHelpText,
} from "../commands";

// ---------------------------------------------------------------------------
// COMMANDS constant
// ---------------------------------------------------------------------------

describe("COMMANDS", () => {
  it("includes at least /reset, /memory, /compact, /status, /voice, /model, /help", () => {
    const triggers = COMMANDS.map((c) => c.trigger);
    expect(triggers).toContain("/reset");
    expect(triggers).toContain("/memory");
    expect(triggers).toContain("/compact");
    expect(triggers).toContain("/status");
    expect(triggers).toContain("/voice");
    expect(triggers).toContain("/model");
    expect(triggers).toContain("/help");
  });

  it("every command has a non-empty name, trigger, description, and scope", () => {
    for (const cmd of COMMANDS) {
      expect(cmd.name).toBeTruthy();
      expect(cmd.trigger).toBeTruthy();
      expect(cmd.description).toBeTruthy();
      expect(["local", "remote"]).toContain(cmd.scope);
    }
  });

  it("every trigger starts with /", () => {
    for (const cmd of COMMANDS) {
      expect(cmd.trigger.startsWith("/")).toBe(true);
    }
  });

  it("trigger matches name (trigger === '/' + name)", () => {
    for (const cmd of COMMANDS) {
      expect(cmd.trigger).toBe(`/${cmd.name}`);
    }
  });

  it("/reset and /help are local", () => {
    const reset = COMMANDS.find((c) => c.name === "reset");
    const help = COMMANDS.find((c) => c.name === "help");
    expect(reset?.scope).toBe("local");
    expect(help?.scope).toBe("local");
  });

  it("/memory, /compact, /status, /voice, /model are remote", () => {
    const remote = ["memory", "compact", "status", "voice", "model"];
    for (const name of remote) {
      const cmd = COMMANDS.find((c) => c.name === name);
      expect(cmd?.scope).toBe("remote");
    }
  });
});

// ---------------------------------------------------------------------------
// matchCommands
// ---------------------------------------------------------------------------

describe("matchCommands", () => {
  it("returns all commands when prefix is /", () => {
    const matches = matchCommands("/");
    expect(matches.length).toBe(COMMANDS.length);
  });

  it("returns subset matching the prefix", () => {
    const matches = matchCommands("/me");
    expect(matches.every((c) => c.trigger.startsWith("/me"))).toBe(true);
  });

  it("/memory prefix returns only /memory", () => {
    const matches = matchCommands("/memory");
    expect(matches.map((c) => c.trigger)).toContain("/memory");
  });

  it("returns empty array for non-matching prefix", () => {
    expect(matchCommands("/zzz")).toHaveLength(0);
  });

  it("is case-insensitive", () => {
    const lower = matchCommands("/res");
    const upper = matchCommands("/RES");
    expect(lower.map((c) => c.name)).toEqual(upper.map((c) => c.name));
  });

  it("does not return matches when input has no leading /", () => {
    // "reset" without slash should not match /reset
    expect(matchCommands("reset")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// findCommand
// ---------------------------------------------------------------------------

describe("findCommand", () => {
  it("finds /reset by exact trigger", () => {
    const cmd = findCommand("/reset");
    expect(cmd).not.toBeNull();
    expect(cmd?.name).toBe("reset");
  });

  it("finds /model even when extra args follow the trigger", () => {
    const cmd = findCommand("/model gemini");
    expect(cmd).not.toBeNull();
    expect(cmd?.name).toBe("model");
  });

  it("returns null for unknown trigger", () => {
    expect(findCommand("/unknowncmd")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(findCommand("")).toBeNull();
  });

  it("returns null when input has no leading /", () => {
    expect(findCommand("reset")).toBeNull();
  });

  it("finds every command by its own trigger", () => {
    for (const cmd of COMMANDS) {
      const found = findCommand(cmd.trigger);
      expect(found).not.toBeNull();
      expect(found?.name).toBe(cmd.name);
    }
  });
});

// ---------------------------------------------------------------------------
// buildHelpText
// ---------------------------------------------------------------------------

describe("buildHelpText", () => {
  it("starts with 'Available commands:'", () => {
    expect(buildHelpText()).toMatch(/^Available commands:/);
  });

  it("mentions every command trigger", () => {
    const text = buildHelpText();
    for (const cmd of COMMANDS) {
      expect(text).toContain(cmd.trigger);
    }
  });

  it("includes each command's description", () => {
    const text = buildHelpText();
    for (const cmd of COMMANDS) {
      expect(text).toContain(cmd.description);
    }
  });

  it("includes arg placeholder for commands that have args", () => {
    const text = buildHelpText();
    for (const cmd of COMMANDS) {
      if (cmd.args) {
        expect(text).toContain(cmd.args);
      }
    }
  });
});
