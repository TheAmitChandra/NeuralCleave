/**
 * In-app slash command definitions.
 *
 * Commands that start with "/" in the chat input are intercepted here.
 * "local" commands are handled entirely in the frontend (no network call).
 * "remote" commands are forwarded to the backend via WebSocket as plain
 * text so the agent can handle them (e.g. /memory → agent reads memory).
 */

export type CommandScope = "local" | "remote";

export interface Command {
  name: string;          // e.g. "reset"
  trigger: string;       // e.g. "/reset"
  description: string;
  scope: CommandScope;
  args?: string;         // placeholder hint shown after the trigger
}

export const COMMANDS: Command[] = [
  {
    name: "reset",
    trigger: "/reset",
    description: "Clear the current conversation history",
    scope: "local",
  },
  {
    name: "memory",
    trigger: "/memory",
    description: "Show recent long-term memory entries",
    scope: "remote",
  },
  {
    name: "compact",
    trigger: "/compact",
    description: "Summarise and compress the conversation context",
    scope: "remote",
  },
  {
    name: "status",
    trigger: "/status",
    description: "Show gateway status, uptime, and active channels",
    scope: "remote",
  },
  {
    name: "voice",
    trigger: "/voice",
    description: "Toggle voice input/output on or off",
    scope: "remote",
  },
  {
    name: "model",
    trigger: "/model",
    description: "Switch the active LLM provider or show current model",
    scope: "remote",
    args: "<provider>",
  },
  {
    name: "help",
    trigger: "/help",
    description: "List all available commands",
    scope: "local",
  },
];

/** Returns the commands whose trigger starts with the given prefix. */
export function matchCommands(prefix: string): Command[] {
  const lower = prefix.toLowerCase();
  return COMMANDS.filter((c) => c.trigger.startsWith(lower));
}

/** Returns the full Command for an exact trigger match, or null. */
export function findCommand(trigger: string): Command | null {
  return COMMANDS.find((c) => c.trigger === trigger.split(" ")[0]) ?? null;
}

/** Build the help text that the /help local handler returns. */
export function buildHelpText(): string {
  const lines = COMMANDS.map(
    (c) => `${c.trigger}${c.args ? " " + c.args : ""}  — ${c.description}`
  );
  return "Available commands:\n" + lines.join("\n");
}
