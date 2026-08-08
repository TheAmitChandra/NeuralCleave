SKILL_METADATA = {
    "name": "figma_comments",
    "description": "List unresolved comments on a Figma file.",
    "version": "1.0.0",
    "trigger": "figma comments",
    "dependencies": ["httpx"],
}

import os
import httpx


async def run(args: dict) -> str:
    token = os.environ.get("FIGMA_TOKEN", "")
    file_key = args.get("file_key", "")
    r = httpx.get(
        f"https://api.figma.com/v1/files/{file_key}/comments",
        headers={"X-Figma-Token": token},
    )
    comments = [c for c in r.json().get("comments", []) if not c.get("resolved_at")]
    if not comments:
        return "No unresolved comments"
    return "\n".join(
        f"[{c['user']['handle']}] {c['message'][:120]}" for c in comments[:10]
    )
