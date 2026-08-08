SKILL_METADATA = {
    "name": "git_summary",
    "description": "Summarise the last N commits in a local git repository.",
    "version": "1.0.0",
    "trigger": "git summary",
}

import subprocess


async def run(args: dict) -> str:
    path = args.get("path", ".")
    n = int(args.get("n", 10))
    result = subprocess.run(
        ["git", "-C", path, "log", f"-{n}", "--oneline", "--no-decorate"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"git error: {result.stderr.strip()}"
    return result.stdout.strip() or "No commits found"
