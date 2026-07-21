"""NotionSearchTool — searches Notion pages and databases by query."""

from __future__ import annotations

from typing import Any

from neuralcleave_sdk import Tool, ToolResult

_SEARCH_URL = "https://api.notion.com/v1/search"
_NOTION_VERSION = "2022-06-28"


def _extract_title(result: dict[str, Any]) -> str:
    """Pull the plain-text title out of a Notion page/database object."""
    for prop in result.get("properties", {}).values():
        if prop.get("type") == "title":
            texts = prop.get("title", [])
            return "".join(t.get("plain_text", "") for t in texts) or "(untitled)"
    return "(untitled)"


class NotionSearchTool(Tool):
    """Searches Notion pages and databases shared with the integration."""

    name = "notion_search"
    description = "Search Notion pages and databases by query text."
    parameters = {
        "query": {"type": "str", "description": "Search text", "required": True},
        "limit": {"type": "int", "description": "Max results to return (default 10)", "required": False},
    }
    permissions = ["network"]

    def __init__(self, token: str | None = None) -> None:
        self._token = token

    async def execute(self, query: str, limit: int = 10, **_) -> ToolResult:
        if not self._token:
            return ToolResult(tool=self.name, output=None, error="NOTION_TOKEN not set")

        try:
            import httpx
        except ImportError:
            return ToolResult(tool=self.name, output=None, error="pip install httpx")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _SEARCH_URL,
                    headers=headers,
                    json={"query": query, "page_size": min(limit, 100)},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        results = [
            {
                "id": r.get("id", ""),
                "type": r.get("object", "unknown"),
                "url": r.get("url", ""),
                "title": _extract_title(r),
            }
            for r in data.get("results", [])[:limit]
        ]
        return ToolResult(
            tool=self.name,
            output=results,
            metadata={"query": query, "count": len(results)},
        )
