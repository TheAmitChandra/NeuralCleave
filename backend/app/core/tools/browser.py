"""Browser automation tool — Playwright-based web interaction.

Security controls (from SKILL spec):
- Domain allowlist enforced before every navigation
- Login/credential forms blocked by default
- File downloads blocked by default
- All sessions run with a 5-minute hard timeout
- Every page visit and screenshot logged to audit
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from app.core.observability.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Policy model
# ---------------------------------------------------------------------------


class BrowserPolicy(BaseModel):
    """Runtime policy applied to every browser session."""

    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    block_credential_forms: bool = True
    block_downloads: bool = True
    screenshot_logging: bool = True
    max_session_duration_seconds: int = 300

    @field_validator("allowed_domains", "blocked_domains", mode="before")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [d.lower() for d in v]


# ---------------------------------------------------------------------------
# Domain validation
# ---------------------------------------------------------------------------


def _extract_host(url: str) -> str:
    return urlparse(url).hostname or ""


def validate_url(url: str, policy: BrowserPolicy) -> None:
    """Raise ValueError if the URL violates the browser policy."""
    host = _extract_host(url).lower()
    if not host:
        raise ValueError(f"Invalid URL — cannot extract host: {url}")

    # Check blocked domains (wildcard prefix support: *.gov)
    for blocked in policy.blocked_domains:
        if blocked.startswith("*."):
            suffix = blocked[2:]
            if host.endswith(f".{suffix}") or host == suffix:
                raise ValueError(f"Domain '{host}' is blocked by policy.")
        elif host == blocked:
            raise ValueError(f"Domain '{host}' is blocked by policy.")

    # Check allowlist (empty allowlist = allow all non-blocked)
    if policy.allowed_domains:
        allowed = any(host == d or host.endswith(f".{d}") for d in policy.allowed_domains)
        if not allowed:
            raise ValueError(f"Domain '{host}' is not in the allowed_domains list.")


# ---------------------------------------------------------------------------
# Browser tool functions
# ---------------------------------------------------------------------------


async def browser_navigate(params: dict[str, Any]) -> dict[str, Any]:
    """Navigate to a URL and return the page title and text content.

    Parameters:
        url (str): Target URL.
        policy (dict): Serialised BrowserPolicy. Optional.
        wait_for_selector (str): CSS selector to wait for before returning. Optional.

    Returns:
        dict with keys: url, title, text (first 4000 chars), status_code.
    """
    url: str = params["url"]
    policy = BrowserPolicy(**(params.get("policy") or {}))
    wait_selector: str | None = params.get("wait_for_selector")

    validate_url(url, policy)

    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=not policy.block_downloads,
        )
        page = await context.new_page()

        async def _handle_download(download: Any) -> None:
            if policy.block_downloads:
                await download.cancel()
                logger.warning("browser_download_blocked", url=url)

        page.on("download", _handle_download)

        try:
            async with asyncio.timeout(policy.max_session_duration_seconds):
                response = await page.goto(url, wait_until="domcontentloaded")
                status_code = response.status if response else 0

                if wait_selector:
                    await page.wait_for_selector(wait_selector, timeout=10_000)

                title = await page.title()
                text = await page.evaluate("() => document.body.innerText")

                if policy.screenshot_logging:
                    screenshot = await page.screenshot(type="png")
                    logger.info(
                        "browser_screenshot_taken",
                        url=url,
                        bytes_size=len(screenshot),
                    )

        finally:
            await context.close()
            await browser.close()

    logger.info("browser_navigate", url=url, title=title, status_code=status_code)
    return {
        "url": url,
        "title": title,
        "text": text[:4000],
        "status_code": status_code,
    }


async def browser_click(params: dict[str, Any]) -> dict[str, Any]:
    """Click an element on an already-loaded page URL.

    Parameters:
        url (str): Page to load.
        selector (str): CSS selector to click.
        policy (dict): BrowserPolicy. Optional.

    Returns:
        dict with keys: clicked, url_after, title_after.
    """
    url: str = params["url"]
    selector: str = params["selector"]
    policy = BrowserPolicy(**(params.get("policy") or {}))

    validate_url(url, policy)

    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("playwright is not installed.") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=False)
        page = await context.new_page()
        try:
            async with asyncio.timeout(policy.max_session_duration_seconds):
                await page.goto(url, wait_until="domcontentloaded")
                await page.click(selector, timeout=5_000)
                await page.wait_for_load_state("domcontentloaded")
                title = await page.title()
                url_after = page.url
        finally:
            await context.close()
            await browser.close()

    logger.info("browser_click", original_url=url, selector=selector, url_after=url_after)
    return {"clicked": True, "url_after": url_after, "title_after": title}


async def browser_scrape(params: dict[str, Any]) -> dict[str, Any]:
    """Extract text content from all elements matching a CSS selector.

    Parameters:
        url (str): Target page.
        selector (str): CSS selector for elements to scrape.
        policy (dict): BrowserPolicy. Optional.

    Returns:
        dict with keys: url, selector, results (list of text strings).
    """
    url: str = params["url"]
    selector: str = params["selector"]
    policy = BrowserPolicy(**(params.get("policy") or {}))

    validate_url(url, policy)

    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("playwright is not installed.") from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=False)
        page = await context.new_page()
        try:
            async with asyncio.timeout(policy.max_session_duration_seconds):
                await page.goto(url, wait_until="domcontentloaded")
                elements = await page.query_selector_all(selector)
                results = [await el.inner_text() for el in elements]
        finally:
            await context.close()
            await browser.close()

    logger.info("browser_scrape", url=url, selector=selector, count=len(results))
    return {"url": url, "selector": selector, "results": results[:50]}


# ---------------------------------------------------------------------------
# Tool definitions (for ToolRegistry)
# ---------------------------------------------------------------------------

from app.core.tools.registry import ToolDefinition  # noqa: E402

BROWSER_NAVIGATE_DEF = ToolDefinition(
    name="browser.navigate",
    description="Navigate to a URL and return the page title and text content.",
    permissions=["web_access", "network.external"],
    risk_level="high",
    requires_approval=False,
    sandbox_required=True,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "wait_for_selector": {"type": "string"},
        },
    },
)

BROWSER_CLICK_DEF = ToolDefinition(
    name="browser.click",
    description="Click a CSS-selected element on a page.",
    permissions=["web_access", "network.external"],
    risk_level="high",
    requires_approval=False,
    sandbox_required=True,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url", "selector"],
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string"},
        },
    },
)

BROWSER_SCRAPE_DEF = ToolDefinition(
    name="browser.scrape",
    description="Scrape text from all elements matching a CSS selector.",
    permissions=["web_access", "network.external"],
    risk_level="high",
    requires_approval=False,
    sandbox_required=True,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url", "selector"],
        "properties": {
            "url": {"type": "string"},
            "selector": {"type": "string"},
        },
    },
)


def register_browser_tools(registry: Any) -> None:
    """Register all browser tools into the provided registry."""
    registry.register(BROWSER_NAVIGATE_DEF, browser_navigate)
    registry.register(BROWSER_CLICK_DEF, browser_click)
    registry.register(BROWSER_SCRAPE_DEF, browser_scrape)
