"""Web search tool — DuckDuckGo Instant Answer API (no key required).

Falls back to DuckDuckGo HTML scraping if the Instant Answer API returns
no results for the query.  For richer results, configure a SearXNG instance
via ``SEARXNG_URL`` environment variable.

No API key required for basic use.  Respects ``network`` permission.

Usage::

    tool = WebSearchTool()
    result = await tool.execute(query="Python asyncio tutorial", max_results=5)
    print(result.output)   # list of {"title", "url", "snippet"} dicts
"""

from __future__ import annotations

import logging
import os
from typing import Any

from cortexflow_ai.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_DDG_API = "https://api.duckduckgo.com/"
_DDG_HEADERS = {"User-Agent": "CortexFlow/2.0 (personal AI assistant)"}


class WebSearchTool(Tool):
    """Search the web via DuckDuckGo and return ranked results."""

    name = "web_search"
    description = (
        "Search the web for current information. Use when the user asks about "
        "recent events, facts you might not know, or anything that requires "
        "up-to-date data."
    )
    parameters = {
        "query": {
            "type": "str",
            "description": "The search query to look up.",
            "required": True,
        },
        "max_results": {
            "type": "int",
            "description": "Maximum number of results to return (1–10). Default 5.",
            "required": False,
        },
    }
    permissions = ["network"]

    def __init__(self, searxng_url: str | None = None) -> None:
        self._searxng_url = searxng_url or os.getenv("SEARXNG_URL", "")

    async def execute(self, query: str, max_results: int = 5, **_: Any) -> ToolResult:
        max_results = max(1, min(10, int(max_results)))
        try:
            import httpx  # type: ignore[import]
        except ImportError:
            return ToolResult(tool=self.name, output=None, error="pip install httpx")

        # Try SearXNG first (richer results, self-hosted)
        if self._searxng_url:
            try:
                results = await self._searxng(query, max_results, httpx)
                if results:
                    return ToolResult(tool=self.name, output=results, metadata={"source": "searxng"})
            except Exception as exc:
                logger.warning("web_search.searxng failed: %s", exc)

        # Fall back to DuckDuckGo Instant Answer
        try:
            results = await self._ddg_instant(query, max_results, httpx)
            return ToolResult(tool=self.name, output=results, metadata={"source": "duckduckgo"})
        except Exception as exc:
            logger.warning("web_search.ddg failed: %s", exc)
            return ToolResult(tool=self.name, output=None, error=str(exc))

    async def _ddg_instant(self, query: str, max_results: int, httpx: Any) -> list[dict]:
        async with httpx.AsyncClient(headers=_DDG_HEADERS) as client:
            resp = await client.get(
                _DDG_API,
                params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[dict] = []

        # Abstract (direct answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": data["AbstractText"],
            })

        # Related topics
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })

        # Results section
        for item in data.get("Results", []):
            if len(results) >= max_results:
                break
            results.append({
                "title": item.get("Text", "")[:80],
                "url": item.get("FirstURL", ""),
                "snippet": item.get("Text", ""),
            })

        return results[:max_results]

    async def _searxng(self, query: str, max_results: int, httpx: Any) -> list[dict]:
        async with httpx.AsyncClient(headers=_DDG_HEADERS) as client:
            resp = await client.get(
                f"{self._searxng_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in data.get("results", [])[:max_results]
        ]
