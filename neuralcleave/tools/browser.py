"""Browser automation tool for CortexFlow — closes the Playwright gap vs OpenClaw.

Provides headless Chromium control via Playwright: navigate, screenshot,
click, fill, extract text and links, wait for elements, evaluate JavaScript.

Playwright is imported lazily (inside ``_ensure_browser``) so the module
loads without it installed.  If it is missing, every action returns a
``BrowserResult`` with ``success=False`` and a helpful install message.

Security
--------
- URL scheme restricted to ``http`` and ``https`` — no ``file://`` or ``data:``
- Optional ``allowed_domains`` allowlist rejects requests to unlisted hosts
- Text output capped at ``MAX_TEXT_BYTES`` (100 KB)
- Screenshots returned as base64 strings, not written to disk
- Browser always runs headless by default (no visible window)

Usage::

    tool = BrowserTool()
    result = await tool.navigate("https://example.com")
    print(result.title, result.url)

    snap = await tool.screenshot()
    # snap.screenshot_b64 is a base64-encoded PNG

    links = await tool.extract_links()
    print(links.links)

    await tool.close()
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from cortexflow_ai.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

TIMEOUT_DEFAULT_MS: int = 30_000      # 30 s in Playwright milliseconds
MAX_TEXT_BYTES: int = 100_000         # 100 KB text cap
_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class BrowserResult:
    """Structured result returned by every BrowserTool action."""
    success: bool
    action: str
    url: str | None = None
    title: str | None = None
    text: str | None = None
    screenshot_b64: str | None = None
    links: list[str] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Core browser client ───────────────────────────────────────────────────────

class BrowserTool:
    """Playwright-backed headless browser for CortexFlow.

    Maintains a single persistent browser/page across calls — call
    ``await tool.close()`` when done to release resources.

    Args:
        allowed_domains: If given, requests to any other hostname are blocked
                         before touching the network.
        timeout_ms:      Per-action Playwright timeout in milliseconds.
        headless:        Run without a visible browser window (default True).
    """

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        timeout_ms: int = TIMEOUT_DEFAULT_MS,
        headless: bool = True,
    ) -> None:
        self._allowed_domains = allowed_domains
        self._timeout_ms = timeout_ms
        self._headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _check_url(self, url: str) -> None:
        """Raise ValueError if *url* violates scheme or domain constraints."""
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            raise ValueError(
                f"URL scheme {parsed.scheme!r} is not allowed; use http or https"
            )
        if self._allowed_domains is not None and parsed.hostname not in self._allowed_domains:
            raise ValueError(
                f"Domain {parsed.hostname!r} is not in the allowed-domain list"
            )

    async def _ensure_browser(self) -> None:
        """Lazy-start Playwright + Chromium on the first call (idempotent)."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError(
                "playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        self._page.set_default_timeout(self._timeout_ms)
        logger.debug("browser.started headless=%s timeout_ms=%d", self._headless, self._timeout_ms)

    def _current_url(self) -> str | None:
        return self._page.url if self._page is not None else None

    async def _safe_title(self) -> str | None:
        try:
            return await self._page.title()
        except Exception:
            return None

    # ── Public actions ────────────────────────────────────────────────────────

    async def navigate(self, url: str) -> BrowserResult:
        """Navigate to *url*; return the final URL and page title."""
        try:
            self._check_url(url)
            await self._ensure_browser()
            response = await self._page.goto(url, timeout=self._timeout_ms)
            title = await self._safe_title()
            return BrowserResult(
                success=True,
                action="navigate",
                url=self._current_url(),
                title=title,
                metadata={"status": response.status if response else None},
            )
        except Exception as exc:
            logger.error("browser.navigate url=%r error=%s", url, exc)
            return BrowserResult(success=False, action="navigate", url=url, error=str(exc))

    async def screenshot(
        self,
        url: str | None = None,
        selector: str | None = None,
        *,
        full_page: bool = True,
    ) -> BrowserResult:
        """Capture a screenshot and return it as base64-encoded PNG.

        If *url* is given, navigate there first.
        If *selector* is given, only that element is captured.
        """
        try:
            if url is not None:
                nav = await self.navigate(url)
                if not nav.success:
                    return nav
            await self._ensure_browser()
            if selector:
                element = await self._page.wait_for_selector(selector, timeout=self._timeout_ms)
                data: bytes = await element.screenshot()
            else:
                data = await self._page.screenshot(full_page=full_page)
            return BrowserResult(
                success=True,
                action="screenshot",
                url=self._current_url(),
                title=await self._safe_title(),
                screenshot_b64=base64.b64encode(data).decode(),
                metadata={"bytes": len(data), "selector": selector},
            )
        except Exception as exc:
            logger.error("browser.screenshot error=%s", exc)
            return BrowserResult(
                success=False,
                action="screenshot",
                url=self._current_url(),
                error=str(exc),
            )

    async def click(self, selector: str) -> BrowserResult:
        """Click the first element matching *selector*."""
        try:
            await self._ensure_browser()
            await self._page.click(selector, timeout=self._timeout_ms)
            return BrowserResult(
                success=True,
                action="click",
                url=self._current_url(),
                metadata={"selector": selector},
            )
        except Exception as exc:
            logger.error("browser.click selector=%r error=%s", selector, exc)
            return BrowserResult(
                success=False,
                action="click",
                url=self._current_url(),
                error=str(exc),
                metadata={"selector": selector},
            )

    async def fill(self, selector: str, value: str) -> BrowserResult:
        """Clear and fill the input matching *selector* with *value*."""
        try:
            await self._ensure_browser()
            await self._page.fill(selector, value, timeout=self._timeout_ms)
            return BrowserResult(
                success=True,
                action="fill",
                url=self._current_url(),
                metadata={"selector": selector},
            )
        except Exception as exc:
            logger.error("browser.fill selector=%r error=%s", selector, exc)
            return BrowserResult(
                success=False,
                action="fill",
                url=self._current_url(),
                error=str(exc),
                metadata={"selector": selector},
            )

    async def extract_text(self, selector: str | None = None) -> BrowserResult:
        """Return visible text from *selector* (or ``<body>`` if None).

        Output is capped at ``MAX_TEXT_BYTES`` characters.
        """
        try:
            await self._ensure_browser()
            if selector:
                element = await self._page.wait_for_selector(selector, timeout=self._timeout_ms)
                raw: str = await element.inner_text()
            else:
                raw = await self._page.inner_text("body")
            truncated = len(raw) > MAX_TEXT_BYTES
            text = raw[:MAX_TEXT_BYTES]
            return BrowserResult(
                success=True,
                action="extract_text",
                url=self._current_url(),
                text=text,
                metadata={"selector": selector, "length": len(text), "truncated": truncated},
            )
        except Exception as exc:
            logger.error("browser.extract_text selector=%r error=%s", selector, exc)
            return BrowserResult(
                success=False,
                action="extract_text",
                url=self._current_url(),
                error=str(exc),
            )

    async def extract_links(self) -> BrowserResult:
        """Return all absolute http/https links on the current page."""
        try:
            await self._ensure_browser()
            all_links: list[str] = await self._page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.href)",
            )
            http_links = [lnk for lnk in all_links if lnk.startswith(("http://", "https://"))]
            return BrowserResult(
                success=True,
                action="extract_links",
                url=self._current_url(),
                links=http_links,
                metadata={"count": len(http_links)},
            )
        except Exception as exc:
            logger.error("browser.extract_links error=%s", exc)
            return BrowserResult(
                success=False,
                action="extract_links",
                url=self._current_url(),
                error=str(exc),
            )

    async def wait_for(self, selector: str, *, state: str = "visible") -> BrowserResult:
        """Wait until *selector* reaches *state* (visible/hidden/attached/detached)."""
        try:
            await self._ensure_browser()
            await self._page.wait_for_selector(selector, state=state, timeout=self._timeout_ms)
            return BrowserResult(
                success=True,
                action="wait_for",
                url=self._current_url(),
                metadata={"selector": selector, "state": state},
            )
        except Exception as exc:
            logger.error("browser.wait_for selector=%r state=%r error=%s", selector, state, exc)
            return BrowserResult(
                success=False,
                action="wait_for",
                url=self._current_url(),
                error=str(exc),
                metadata={"selector": selector, "state": state},
            )

    async def evaluate(self, expression: str) -> BrowserResult:
        """Evaluate a JavaScript *expression* and return its result."""
        try:
            await self._ensure_browser()
            result = await self._page.evaluate(expression)
            return BrowserResult(
                success=True,
                action="evaluate",
                url=self._current_url(),
                metadata={"expression": expression, "result": result},
            )
        except Exception as exc:
            logger.error("browser.evaluate expression=%r error=%s", expression, exc)
            return BrowserResult(
                success=False,
                action="evaluate",
                url=self._current_url(),
                error=str(exc),
                metadata={"expression": expression},
            )

    async def get_title(self) -> BrowserResult:
        """Return the current page title."""
        try:
            await self._ensure_browser()
            title = await self._page.title()
            return BrowserResult(success=True, action="get_title", url=self._current_url(), title=title)
        except Exception as exc:
            return BrowserResult(success=False, action="get_title", url=self._current_url(), error=str(exc))

    async def get_url(self) -> BrowserResult:
        """Return the current page URL."""
        try:
            await self._ensure_browser()
            return BrowserResult(success=True, action="get_url", url=self._current_url())
        except Exception as exc:
            return BrowserResult(success=False, action="get_url", error=str(exc))

    async def close(self) -> None:
        """Close the browser and free all Playwright resources (idempotent)."""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._page = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        logger.debug("browser.closed")


# ── Tool adapter (for agent pipeline integration) ─────────────────────────────

class BrowserAutomationTool(Tool):
    """Agent-pipeline adapter wrapping ``BrowserTool``.

    Exposes a single ``execute(action, url, selector, value, expression)``
    entry point so the LLM can drive the browser via the standard tool call
    interface.
    """

    name = "browser"
    description = (
        "Headless browser automation: navigate pages, take screenshots, "
        "click elements, fill forms, extract text and links, run JavaScript."
    )
    parameters = {
        "action": {
            "type": "str",
            "description": (
                "One of: navigate, screenshot, click, fill, extract_text, "
                "extract_links, wait_for, evaluate, get_title, get_url"
            ),
            "required": True,
        },
        "url": {
            "type": "str",
            "description": "Target URL (required for navigate; optional for screenshot).",
            "required": False,
        },
        "selector": {
            "type": "str",
            "description": "CSS selector (required for click, fill, wait_for; optional for screenshot and extract_text).",
            "required": False,
        },
        "value": {
            "type": "str",
            "description": "Text value to fill (required for fill action).",
            "required": False,
        },
        "expression": {
            "type": "str",
            "description": "JavaScript expression to evaluate (required for evaluate action).",
            "required": False,
        },
    }
    permissions = ["network", "browser"]

    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        timeout_ms: int = TIMEOUT_DEFAULT_MS,
        headless: bool = True,
    ) -> None:
        self._client = BrowserTool(
            allowed_domains=allowed_domains,
            timeout_ms=timeout_ms,
            headless=headless,
        )

    async def execute(
        self,
        action: str,
        url: str | None = None,
        selector: str | None = None,
        value: str | None = None,
        expression: str | None = None,
        **_: Any,
    ) -> ToolResult:
        """Dispatch to the appropriate BrowserTool method."""
        try:
            br = await self._dispatch(action, url=url, selector=selector, value=value, expression=expression)
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        if not br.success:
            return ToolResult(tool=self.name, output=None, error=br.error, metadata=br.metadata)

        output = br.text or br.title or br.url or br.metadata.get("result") or str(br.links)
        meta: dict[str, Any] = {k: v for k, v in {
            "url": br.url,
            "title": br.title,
            "links": br.links or None,
            "screenshot_b64": br.screenshot_b64,
            **br.metadata,
        }.items() if v is not None}
        return ToolResult(tool=self.name, output=output, metadata=meta)

    async def _dispatch(
        self,
        action: str,
        *,
        url: str | None,
        selector: str | None,
        value: str | None,
        expression: str | None,
    ) -> BrowserResult:
        c = self._client
        match action:
            case "navigate":
                if not url:
                    raise ValueError("'url' is required for the navigate action")
                return await c.navigate(url)
            case "screenshot":
                return await c.screenshot(url=url, selector=selector)
            case "click":
                if not selector:
                    raise ValueError("'selector' is required for the click action")
                return await c.click(selector)
            case "fill":
                if not selector or value is None:
                    raise ValueError("'selector' and 'value' are required for the fill action")
                return await c.fill(selector, value)
            case "extract_text":
                return await c.extract_text(selector=selector)
            case "extract_links":
                return await c.extract_links()
            case "wait_for":
                if not selector:
                    raise ValueError("'selector' is required for the wait_for action")
                return await c.wait_for(selector)
            case "evaluate":
                if not expression:
                    raise ValueError("'expression' is required for the evaluate action")
                return await c.evaluate(expression)
            case "get_title":
                return await c.get_title()
            case "get_url":
                return await c.get_url()
            case _:
                raise ValueError(
                    f"Unknown browser action {action!r}. Valid actions: "
                    "navigate, screenshot, click, fill, extract_text, extract_links, "
                    "wait_for, evaluate, get_title, get_url"
                )
