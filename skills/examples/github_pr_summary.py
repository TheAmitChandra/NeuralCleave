import os

import httpx

SKILL_METADATA = {
    "name": "github_pr_summary",
    "description": "List open pull requests for a GitHub repo with author and status.",
    "version": "1.0.0",
    "trigger": "pull requests",
    "dependencies": ["httpx"],
}


async def run(args: dict) -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = args.get("repo", "")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    r = httpx.get(
        f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=10",
        headers=headers,
    )
    prs = r.json()
    if not prs:
        return f"No open PRs in {repo}"
    return "\n".join(
        f"#{p['number']} [{p['user']['login']}] {p['title']}" for p in prs
    )
