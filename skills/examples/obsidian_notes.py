SKILL_METADATA = {
    "name": "obsidian_notes",
    "description": "Search your local Obsidian vault for notes matching a query.",
    "version": "1.0.0",
    "trigger": "obsidian",
}

import os
from pathlib import Path


async def run(args: dict) -> str:
    vault = Path(args.get("vault", os.path.expanduser("~/Documents/Obsidian")))
    query = args.get("query", "").lower()
    if not vault.exists():
        return f"Vault not found at {vault}"
    matches = []
    for md in vault.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8")
            if query in text.lower() or query in md.stem.lower():
                excerpt = next(
                    (l.strip() for l in text.splitlines() if query in l.lower()), ""
                )
                matches.append(f"{md.stem}: {excerpt[:100]}")
                if len(matches) >= 10:
                    break
        except Exception:
            continue
    return "\n".join(matches) if matches else f"No notes matching '{query}'"
