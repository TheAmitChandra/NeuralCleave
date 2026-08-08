SKILL_METADATA = {
    "name": "github_issues",
    "description": "List open issues or create a new issue on any GitHub repo.",
    "version": "1.0.0",
    "trigger": "github issues",
    "dependencies": ["httpx"],
}

import os
import httpx


async def run(args: dict) -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = args.get("repo", "")
    action = args.get("action", "list")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    if action == "create":
        title = args.get("title", "New issue")
        body = args.get("body", "")
        r = httpx.post(
            f"https://api.github.com/repos/{repo}/issues",
            json={"title": title, "body": body},
            headers=headers,
        )
        issue = r.json()
        return f"Created #{issue['number']}: {issue['title']} — {issue['html_url']}"

    r = httpx.get(
        f"https://api.github.com/repos/{repo}/issues?state=open&per_page=10",
        headers=headers,
    )
    issues = r.json()
    if not issues:
        return f"No open issues in {repo}"
    return "\n".join(f"#{i['number']} {i['title']}" for i in issues[:10])
