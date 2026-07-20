"""GitHubEventsTool — lists recent public events for a GitHub repository."""

from __future__ import annotations

from NeuralCleave_sdk import Tool, ToolResult

_API_URL = "https://api.github.com/repos/{owner}/{repo}/events"


class GitHubEventsTool(Tool):
    """Fetches recent events (pushes, PRs, issues, stars) for a repo."""

    name = "github_events"
    description = "List recent GitHub events (pushes, PRs, issues) for a repository."
    parameters = {
        "owner": {"type": "str", "description": "Repository owner/org", "required": True},
        "repo": {"type": "str", "description": "Repository name", "required": True},
        "limit": {"type": "int", "description": "Max events to return (default 10)", "required": False},
    }
    permissions = ["network"]

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    async def execute(self, owner: str, repo: str, limit: int = 10, **_) -> ToolResult:
        try:
            import httpx
        except ImportError:
            return ToolResult(tool=self.name, output=None, error="pip install httpx")

        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        url = _API_URL.format(owner=owner, repo=repo)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url, headers=headers, params={"per_page": min(limit, 100)}, timeout=10.0,
                )
                resp.raise_for_status()
                events = resp.json()
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        formatted = [
            {
                "type": e.get("type", "Unknown"),
                "actor": (e.get("actor") or {}).get("login", "unknown"),
                "created_at": e.get("created_at", ""),
            }
            for e in events[:limit]
        ]
        return ToolResult(
            tool=self.name,
            output=formatted,
            metadata={"repo": f"{owner}/{repo}", "count": len(formatted)},
        )
