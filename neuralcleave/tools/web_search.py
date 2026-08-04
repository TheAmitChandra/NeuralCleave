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
import re as _re
from typing import Any
from urllib.parse import unquote

from neuralcleave.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

_DDG_API = "https://api.duckduckgo.com/"
_DDG_HTML = "https://html.duckduckgo.com/html/"
_DDG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NeuralCleave/2.0",
    "Accept-Language": "en-US,en;q=0.9",
}

# Regexes for scraping DDG HTML results (no BeautifulSoup dependency).
_LINK_RE = _re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', _re.S)
_SNIPPET_RE = _re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', _re.S)
_TAG_RE = _re.compile(r"<[^>]+>")


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
                    return ToolResult(tool=self.name, output=self._dedup(results), metadata={"source": "searxng"})
            except Exception as exc:
                logger.warning("web_search.searxng failed: %s", exc)

        # Try DuckDuckGo Instant Answer (structured data, direct answers, Wikipedia)
        try:
            results = await self._ddg_instant(query, max_results, httpx)
            if results:
                return ToolResult(tool=self.name, output=self._dedup(results), metadata={"source": "duckduckgo_instant"})
        except Exception as exc:
            logger.warning("web_search.ddg_instant failed: %s", exc)

        # Fall back to DDG HTML search — scrapes actual web results.
        # The Instant Answer API only returns structured data (Wikipedia, direct
        # facts) and is empty for most real research queries.
        try:
            results = await self._ddg_html(query, max_results, httpx)
            return ToolResult(tool=self.name, output=self._dedup(results), metadata={"source": "duckduckgo_html"})
        except Exception as exc:
            logger.warning("web_search.ddg_html failed: %s", exc)
            return ToolResult(tool=self.name, output=None, error=str(exc))

    @staticmethod
    def _dedup(results: list[dict]) -> list[dict]:
        """Remove duplicate results by URL, preserving insertion order."""
        seen: set[str] = set()
        unique: list[dict] = []
        for r in results:
            url = r.get("url", "")
            if url not in seen:
                seen.add(url)
                unique.append(r)
        return unique

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

        # Direct answer field — DDG populates this for unit conversions, currency
        # rates, simple calculations, etc. (e.g. "1 INR = 0.01196 USD").
        if data.get("Answer"):
            results.append({
                "title": "Direct Answer",
                "url": data.get("AbstractURL", ""),
                "snippet": data["Answer"],
            })

        # Abstract (Wikipedia summary or other structured source)
        if data.get("AbstractText") and len(results) < max_results:
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": data["AbstractText"],
            })

        # Definition
        if data.get("Definition") and len(results) < max_results:
            results.append({
                "title": "Definition",
                "url": data.get("DefinitionURL", ""),
                "snippet": data["Definition"],
            })

        # Related topics — DDG sometimes embeds HTML anchor tags in Text fields.
        for topic in data.get("RelatedTopics", []):
            if len(results) >= max_results:
                break
            if isinstance(topic, dict) and topic.get("Text"):
                text = _TAG_RE.sub("", topic["Text"]).strip()
                results.append({
                    "title": text[:80],
                    "url": topic.get("FirstURL", ""),
                    "snippet": text,
                })

        # Results section
        for item in data.get("Results", []):
            if len(results) >= max_results:
                break
            text = _TAG_RE.sub("", item.get("Text", "")).strip()
            results.append({
                "title": text[:80],
                "url": item.get("FirstURL", ""),
                "snippet": text,
            })

        return results[:max_results]

    async def _ddg_html(self, query: str, max_results: int, httpx: Any) -> list[dict]:
        """Scrape DuckDuckGo HTML search for actual web results.

        The DDG Instant Answer API only covers structured/fact queries.  For
        real research queries (market data, comparisons, how-to guides) the
        HTML endpoint returns ranked web links with snippets.
        """
        async with httpx.AsyncClient(
            headers={**_DDG_HEADERS, "Accept": "text/html,application/xhtml+xml"},
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                _DDG_HTML,
                data={"q": query, "b": "", "kl": "wt-wt"},
                timeout=15.0,
            )
            resp.raise_for_status()

        html = resp.text
        links = _LINK_RE.findall(html)
        snippets = _SNIPPET_RE.findall(html)

        results: list[dict] = []
        for i, (raw_url, raw_title) in enumerate(links[:max_results]):
            title = _TAG_RE.sub("", raw_title).strip()
            snippet = _TAG_RE.sub("", snippets[i]).strip() if i < len(snippets) else ""
            # DDG wraps result URLs through its own redirect tracker.
            # Extract the real destination from the uddg= query param.
            url = raw_url
            if "uddg=" in raw_url:
                start = raw_url.index("uddg=") + 5
                url = unquote(raw_url[start:].split("&")[0])
            if title:
                results.append({"title": title, "url": url, "snippet": snippet})

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
