"""Comprehensive tests for cortexflow_ai.tools.browser — BrowserTool.

Test categories
───────────────
 1.  BrowserResult dataclass                         (tests  1–  8)
 2.  _check_url — scheme & domain validation         (tests  9– 20)
 3.  _ensure_browser — init, idempotent, missing pkg (tests 21– 27)
 4.  navigate                                        (tests 28– 40)
 5.  screenshot                                      (tests 41– 52)
 6.  click                                           (tests 53– 60)
 7.  fill                                            (tests 61– 68)
 8.  extract_text                                    (tests 69– 80)
 9.  extract_links                                   (tests 81– 88)
10.  wait_for                                        (tests 89– 95)
11.  evaluate                                        (tests 96–103)
12.  get_title / get_url                             (tests 104–111)
13.  close                                           (tests 112–117)
14.  BrowserAutomationTool adapter                   (tests 118–130)
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.tools.browser import (
    _ALLOWED_SCHEMES,
    MAX_TEXT_BYTES,
    TIMEOUT_DEFAULT_MS,
    BrowserAutomationTool,
    BrowserResult,
    BrowserTool,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_element(text: str = "elem text", screenshot_bytes: bytes = b"\x89PNG\r\nelement") -> AsyncMock:
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    el.screenshot = AsyncMock(return_value=screenshot_bytes)
    return el


def _make_page(url: str = "https://example.com/") -> AsyncMock:
    page = AsyncMock()
    page.url = url
    page.set_default_timeout = MagicMock()
    page.title = AsyncMock(return_value="Example Domain")
    page.goto = AsyncMock(return_value=MagicMock(status=200))
    page.screenshot = AsyncMock(return_value=b"\x89PNG\r\npage_screenshot")
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.inner_text = AsyncMock(return_value="Hello World from body")
    page.eval_on_selector_all = AsyncMock(
        return_value=["https://alpha.com", "https://beta.com", "javascript:void(0)"]
    )
    page.wait_for_selector = AsyncMock(return_value=_make_element())
    page.evaluate = AsyncMock(return_value=42)
    return page


def _make_browser(page: AsyncMock | None = None) -> AsyncMock:
    browser = AsyncMock()
    browser.new_page = AsyncMock(return_value=page or _make_page())
    browser.close = AsyncMock()
    return browser


def _make_pw_obj(browser: AsyncMock | None = None) -> AsyncMock:
    pw_obj = AsyncMock()
    pw_obj.chromium = AsyncMock()
    pw_obj.chromium.launch = AsyncMock(return_value=browser or _make_browser())
    pw_obj.stop = AsyncMock()
    return pw_obj


def _make_pw_modules(pw_obj: AsyncMock | None = None):
    """Return (sys.modules patch dict, underlying objects dict)."""
    page = _make_page()
    browser = _make_browser(page)
    obj = pw_obj or _make_pw_obj(browser)

    ctx = MagicMock()
    ctx.start = AsyncMock(return_value=obj)

    async_api = MagicMock()
    async_api.async_playwright = MagicMock(return_value=ctx)

    modules = {
        "playwright": MagicMock(),
        "playwright.async_api": async_api,
    }
    return modules, {"page": page, "browser": browser, "pw_obj": obj, "ctx": ctx}


# ─────────────────────────────────────────────────────────────────────────────
# 1. BrowserResult dataclass
# ─────────────────────────────────────────────────────────────────────────────

def test_result_success_default() -> None:
    r = BrowserResult(success=True, action="navigate")
    assert r.success is True


def test_result_failure_default() -> None:
    r = BrowserResult(success=False, action="navigate", error="net::ERR_NAME_NOT_RESOLVED")
    assert r.success is False
    assert "ERR" in r.error


def test_result_defaults() -> None:
    r = BrowserResult(success=True, action="navigate")
    assert r.url is None
    assert r.title is None
    assert r.text is None
    assert r.screenshot_b64 is None
    assert r.links == []
    assert r.error is None
    assert r.metadata == {}


def test_result_links_default_is_empty_list() -> None:
    r1 = BrowserResult(success=True, action="a")
    r2 = BrowserResult(success=True, action="b")
    r1.links.append("https://x.com")
    assert r2.links == []  # independent list per instance


def test_result_metadata_stored() -> None:
    r = BrowserResult(success=True, action="navigate", metadata={"status": 200})
    assert r.metadata["status"] == 200


def test_result_screenshot_b64_stored() -> None:
    r = BrowserResult(success=True, action="screenshot", screenshot_b64="abc123")
    assert r.screenshot_b64 == "abc123"


def test_result_text_stored() -> None:
    r = BrowserResult(success=True, action="extract_text", text="hello")
    assert r.text == "hello"


def test_result_links_stored() -> None:
    links = ["https://a.com", "https://b.com"]
    r = BrowserResult(success=True, action="extract_links", links=links)
    assert r.links == links


# ─────────────────────────────────────────────────────────────────────────────
# 2. _check_url — scheme & domain validation
# ─────────────────────────────────────────────────────────────────────────────

def test_check_url_http_allowed() -> None:
    BrowserTool()._check_url("http://example.com/path")


def test_check_url_https_allowed() -> None:
    BrowserTool()._check_url("https://example.com/path")


def test_check_url_file_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        BrowserTool()._check_url("file:///etc/passwd")


def test_check_url_data_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        BrowserTool()._check_url("data:text/html,<h1>hi</h1>")


def test_check_url_javascript_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        BrowserTool()._check_url("javascript:alert(1)")


def test_check_url_ftp_rejected() -> None:
    with pytest.raises(ValueError, match="scheme"):
        BrowserTool()._check_url("ftp://example.com/file")


def test_check_url_no_domain_restriction_allows_any() -> None:
    tool = BrowserTool(allowed_domains=None)
    tool._check_url("https://anything.evil.com/")  # must not raise


def test_check_url_allowlist_blocks_other_domain() -> None:
    tool = BrowserTool(allowed_domains=["safe.com"])
    with pytest.raises(ValueError, match="allowed-domain"):
        tool._check_url("https://evil.com/")


def test_check_url_allowlist_passes_for_listed_domain() -> None:
    tool = BrowserTool(allowed_domains=["example.com"])
    tool._check_url("https://example.com/page")  # must not raise


def test_check_url_allowlist_blocks_subdomain() -> None:
    tool = BrowserTool(allowed_domains=["example.com"])
    with pytest.raises(ValueError, match="allowed-domain"):
        tool._check_url("https://sub.example.com/page")


def test_allowed_schemes_constant() -> None:
    assert "http" in _ALLOWED_SCHEMES
    assert "https" in _ALLOWED_SCHEMES
    assert "file" not in _ALLOWED_SCHEMES


def test_timeout_default_constant() -> None:
    assert TIMEOUT_DEFAULT_MS == 30_000


# ─────────────────────────────────────────────────────────────────────────────
# 3. _ensure_browser — init, idempotent, missing playwright
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_browser_sets_page() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        assert tool._page is objs["page"]


@pytest.mark.asyncio
async def test_ensure_browser_sets_browser() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        assert tool._browser is objs["browser"]


@pytest.mark.asyncio
async def test_ensure_browser_idempotent() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool._ensure_browser()  # second call must not re-launch
        objs["pw_obj"].chromium.launch.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_browser_calls_set_default_timeout() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool(timeout_ms=5_000)
        await tool._ensure_browser()
        objs["page"].set_default_timeout.assert_called_once_with(5_000)


@pytest.mark.asyncio
async def test_ensure_browser_headless_true_passed_to_launch() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool(headless=True)
        await tool._ensure_browser()
        objs["pw_obj"].chromium.launch.assert_awaited_once_with(headless=True)


@pytest.mark.asyncio
async def test_ensure_browser_headless_false_passed_to_launch() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool(headless=False)
        await tool._ensure_browser()
        objs["pw_obj"].chromium.launch.assert_awaited_once_with(headless=False)


@pytest.mark.asyncio
async def test_ensure_browser_playwright_not_installed() -> None:
    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
        tool = BrowserTool()
        with pytest.raises(RuntimeError, match="playwright is not installed"):
            await tool._ensure_browser()


# ─────────────────────────────────────────────────────────────────────────────
# 4. navigate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_navigate_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.success is True
        assert result.action == "navigate"


@pytest.mark.asyncio
async def test_navigate_calls_goto() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool.navigate("https://example.com")
        objs["page"].goto.assert_awaited_once()


@pytest.mark.asyncio
async def test_navigate_returns_title() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].title = AsyncMock(return_value="My Title")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.title == "My Title"


@pytest.mark.asyncio
async def test_navigate_returns_url() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].url = "https://example.com/final"
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.url == "https://example.com/final"


@pytest.mark.asyncio
async def test_navigate_stores_http_status() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].goto = AsyncMock(return_value=MagicMock(status=301))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.metadata["status"] == 301


@pytest.mark.asyncio
async def test_navigate_network_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].goto = AsyncMock(side_effect=Exception("net::ERR_NAME_NOT_RESOLVED"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://no-such-host.invalid")
        assert result.success is False
        assert "ERR_NAME_NOT_RESOLVED" in result.error


@pytest.mark.asyncio
async def test_navigate_blocked_scheme_returns_failure() -> None:
    tool = BrowserTool()
    result = await tool.navigate("file:///etc/passwd")
    assert result.success is False
    assert "scheme" in result.error


@pytest.mark.asyncio
async def test_navigate_blocked_domain_returns_failure() -> None:
    tool = BrowserTool(allowed_domains=["safe.com"])
    result = await tool.navigate("https://evil.com/")
    assert result.success is False
    assert "allowed-domain" in result.error


@pytest.mark.asyncio
async def test_navigate_playwright_missing_returns_failure() -> None:
    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.success is False
        assert "playwright" in result.error.lower()


@pytest.mark.asyncio
async def test_navigate_goto_none_response_status_is_none() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].goto = AsyncMock(return_value=None)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.navigate("https://example.com")
        assert result.success is True
        assert result.metadata["status"] is None


@pytest.mark.asyncio
async def test_navigate_passes_timeout_to_goto() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool(timeout_ms=10_000)
        await tool.navigate("https://example.com")
        _, kwargs = objs["page"].goto.call_args
        assert kwargs.get("timeout") == 10_000 or objs["page"].goto.call_args[0][1] == 10_000


@pytest.mark.asyncio
async def test_navigate_returns_original_url_on_error() -> None:
    tool = BrowserTool()
    result = await tool.navigate("javascript:alert(1)")
    assert result.url == "javascript:alert(1)"


# ─────────────────────────────────────────────────────────────────────────────
# 5. screenshot
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_screenshot_success_returns_b64() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot()
        assert result.success is True
        assert result.screenshot_b64 is not None


@pytest.mark.asyncio
async def test_screenshot_b64_is_valid_base64() -> None:
    import base64
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot()
        base64.b64decode(result.screenshot_b64)  # must not raise


@pytest.mark.asyncio
async def test_screenshot_calls_full_page_by_default() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.screenshot()
        objs["page"].screenshot.assert_awaited_once_with(full_page=True)


@pytest.mark.asyncio
async def test_screenshot_full_page_false() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.screenshot(full_page=False)
        objs["page"].screenshot.assert_awaited_once_with(full_page=False)


@pytest.mark.asyncio
async def test_screenshot_metadata_bytes() -> None:
    modules, objs = _make_pw_modules()
    raw = b"\x89PNG\r\nfakedata"
    objs["page"].screenshot = AsyncMock(return_value=raw)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot()
        assert result.metadata["bytes"] == len(raw)


@pytest.mark.asyncio
async def test_screenshot_with_url_navigates_first() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.screenshot(url="https://example.com")
        assert result.success is True
        objs["page"].goto.assert_awaited_once()


@pytest.mark.asyncio
async def test_screenshot_with_selector_uses_element_screenshot() -> None:
    modules, objs = _make_pw_modules()
    element = _make_element(screenshot_bytes=b"\x89PNGelement")
    objs["page"].wait_for_selector = AsyncMock(return_value=element)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot(selector="#hero")
        assert result.success is True
        element.screenshot.assert_awaited_once()
        objs["page"].screenshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_screenshot_selector_metadata_stores_selector() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot(selector=".hero")
        assert result.metadata["selector"] == ".hero"


@pytest.mark.asyncio
async def test_screenshot_url_navigate_failure_propagates() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].goto = AsyncMock(side_effect=Exception("connection refused"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        result = await tool.screenshot(url="https://down.example.com")
        assert result.success is False


@pytest.mark.asyncio
async def test_screenshot_page_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].screenshot = AsyncMock(side_effect=Exception("render error"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot()
        assert result.success is False
        assert "render error" in result.error


@pytest.mark.asyncio
async def test_screenshot_title_included() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].title = AsyncMock(return_value="Snap Title")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.screenshot()
        assert result.title == "Snap Title"


# ─────────────────────────────────────────────────────────────────────────────
# 6. click
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_click_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.click("button#submit")
        assert result.success is True


@pytest.mark.asyncio
async def test_click_calls_page_click() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.click("#btn")
        objs["page"].click.assert_awaited_once()


@pytest.mark.asyncio
async def test_click_stores_selector_in_metadata() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.click("#my-btn")
        assert result.metadata["selector"] == "#my-btn"


@pytest.mark.asyncio
async def test_click_element_not_found_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].click = AsyncMock(side_effect=Exception("Element not found"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.click("#missing")
        assert result.success is False
        assert "Element not found" in result.error


@pytest.mark.asyncio
async def test_click_action_field() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.click("#x")
        assert result.action == "click"


@pytest.mark.asyncio
async def test_click_returns_current_url() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].url = "https://example.com/after-click"
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.click("#nav-link")
        assert result.url == "https://example.com/after-click"


@pytest.mark.asyncio
async def test_click_passes_timeout() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool(timeout_ms=5_000)
        await tool._ensure_browser()
        await tool.click(".btn")
        _, kwargs = objs["page"].click.call_args
        assert kwargs.get("timeout") == 5_000


# ─────────────────────────────────────────────────────────────────────────────
# 7. fill
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fill_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.fill("input[name=email]", "user@example.com")
        assert result.success is True


@pytest.mark.asyncio
async def test_fill_calls_page_fill() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.fill("#q", "search term")
        objs["page"].fill.assert_awaited_once()


@pytest.mark.asyncio
async def test_fill_stores_selector_in_metadata() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.fill("#email", "x@y.com")
        assert result.metadata["selector"] == "#email"


@pytest.mark.asyncio
async def test_fill_element_missing_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].fill = AsyncMock(side_effect=Exception("No element found"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.fill("#ghost", "value")
        assert result.success is False
        assert "No element found" in result.error


@pytest.mark.asyncio
async def test_fill_action_field() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.fill("#x", "v")
        assert result.action == "fill"


@pytest.mark.asyncio
async def test_fill_passes_value_to_page_fill() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.fill("#input", "secret_value")
        args = objs["page"].fill.call_args[0]
        assert "secret_value" in args


# ─────────────────────────────────────────────────────────────────────────────
# 8. extract_text
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_text_body_success() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].inner_text = AsyncMock(return_value="Page body text")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.success is True
        assert result.text == "Page body text"


@pytest.mark.asyncio
async def test_extract_text_calls_inner_text_body() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.extract_text()
        objs["page"].inner_text.assert_awaited_once_with("body")


@pytest.mark.asyncio
async def test_extract_text_with_selector() -> None:
    modules, objs = _make_pw_modules()
    element = _make_element(text="Selected text")
    objs["page"].wait_for_selector = AsyncMock(return_value=element)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text(selector="h1")
        assert result.text == "Selected text"
        element.inner_text.assert_awaited_once()
        objs["page"].inner_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_extract_text_truncates_long_text() -> None:
    modules, objs = _make_pw_modules()
    long_text = "x" * (MAX_TEXT_BYTES + 500)
    objs["page"].inner_text = AsyncMock(return_value=long_text)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert len(result.text) == MAX_TEXT_BYTES


@pytest.mark.asyncio
async def test_extract_text_truncated_flag_true() -> None:
    modules, objs = _make_pw_modules()
    long_text = "y" * (MAX_TEXT_BYTES + 1)
    objs["page"].inner_text = AsyncMock(return_value=long_text)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_extract_text_truncated_flag_false_for_short_text() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.metadata["truncated"] is False


@pytest.mark.asyncio
async def test_extract_text_metadata_length() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].inner_text = AsyncMock(return_value="abc")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.metadata["length"] == 3


@pytest.mark.asyncio
async def test_extract_text_selector_in_metadata() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text(selector="p.lead")
        assert result.metadata["selector"] == "p.lead"


@pytest.mark.asyncio
async def test_extract_text_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].inner_text = AsyncMock(side_effect=Exception("DOM error"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.success is False
        assert "DOM error" in result.error


@pytest.mark.asyncio
async def test_extract_text_action_field() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.action == "extract_text"


@pytest.mark.asyncio
async def test_extract_text_exact_boundary_not_truncated() -> None:
    modules, objs = _make_pw_modules()
    exact_text = "z" * MAX_TEXT_BYTES
    objs["page"].inner_text = AsyncMock(return_value=exact_text)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_text()
        assert result.metadata["truncated"] is False
        assert len(result.text) == MAX_TEXT_BYTES


# ─────────────────────────────────────────────────────────────────────────────
# 9. extract_links
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_links_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.success is True
        assert result.action == "extract_links"


@pytest.mark.asyncio
async def test_extract_links_filters_javascript_hrefs() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(
        return_value=["https://a.com", "javascript:void(0)", "https://b.com"]
    )
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert all(lnk.startswith("http") for lnk in result.links)


@pytest.mark.asyncio
async def test_extract_links_count_in_metadata() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(
        return_value=["https://a.com", "https://b.com"]
    )
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.metadata["count"] == 2


@pytest.mark.asyncio
async def test_extract_links_empty_page() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(return_value=[])
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.links == []
        assert result.metadata["count"] == 0


@pytest.mark.asyncio
async def test_extract_links_all_javascript_gives_empty() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(
        return_value=["javascript:void(0)", "javascript:goBack()"]
    )
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.links == []


@pytest.mark.asyncio
async def test_extract_links_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(side_effect=Exception("eval error"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.success is False
        assert "eval error" in result.error


@pytest.mark.asyncio
async def test_extract_links_includes_https_links() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(
        return_value=["https://secure.com", "http://plain.com"]
    )
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert "https://secure.com" in result.links
        assert "http://plain.com" in result.links


@pytest.mark.asyncio
async def test_extract_links_url_included_in_result() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].url = "https://example.com/links-page"
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.extract_links()
        assert result.url == "https://example.com/links-page"


# ─────────────────────────────────────────────────────────────────────────────
# 10. wait_for
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wait_for_visible_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.wait_for("#modal")
        assert result.success is True
        assert result.action == "wait_for"


@pytest.mark.asyncio
async def test_wait_for_passes_selector_and_state() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.wait_for(".spinner", state="hidden")
        _, kwargs = objs["page"].wait_for_selector.call_args
        assert kwargs.get("state") == "hidden"


@pytest.mark.asyncio
async def test_wait_for_default_state_is_visible() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.wait_for(".content")
        _, kwargs = objs["page"].wait_for_selector.call_args
        assert kwargs.get("state") == "visible"


@pytest.mark.asyncio
async def test_wait_for_timeout_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].wait_for_selector = AsyncMock(side_effect=Exception("Timeout exceeded"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.wait_for("#never-appears")
        assert result.success is False
        assert "Timeout" in result.error


@pytest.mark.asyncio
async def test_wait_for_metadata_contains_selector_and_state() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.wait_for("#el", state="attached")
        assert result.metadata["selector"] == "#el"
        assert result.metadata["state"] == "attached"


@pytest.mark.asyncio
async def test_wait_for_failure_metadata_contains_selector() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.wait_for(".gone")
        assert result.metadata["selector"] == ".gone"


# ─────────────────────────────────────────────────────────────────────────────
# 11. evaluate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evaluate_success() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].evaluate = AsyncMock(return_value=42)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("1 + 41")
        assert result.success is True
        assert result.metadata["result"] == 42


@pytest.mark.asyncio
async def test_evaluate_calls_page_evaluate() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.evaluate("document.title")
        objs["page"].evaluate.assert_awaited_once_with("document.title")


@pytest.mark.asyncio
async def test_evaluate_string_result() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].evaluate = AsyncMock(return_value="Hello")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("'Hello'")
        assert result.metadata["result"] == "Hello"


@pytest.mark.asyncio
async def test_evaluate_js_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].evaluate = AsyncMock(side_effect=Exception("ReferenceError: x is not defined"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("x.y.z")
        assert result.success is False
        assert "ReferenceError" in result.error


@pytest.mark.asyncio
async def test_evaluate_action_field() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("true")
        assert result.action == "evaluate"


@pytest.mark.asyncio
async def test_evaluate_expression_in_metadata() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("window.location.href")
        assert result.metadata["expression"] == "window.location.href"


@pytest.mark.asyncio
async def test_evaluate_none_result() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].evaluate = AsyncMock(return_value=None)
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("undefined")
        assert result.success is True
        assert result.metadata["result"] is None


@pytest.mark.asyncio
async def test_evaluate_list_result() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].evaluate = AsyncMock(return_value=[1, 2, 3])
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.evaluate("[1, 2, 3]")
        assert result.metadata["result"] == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# 12. get_title / get_url
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_title_success() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].title = AsyncMock(return_value="My Page")
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.get_title()
        assert result.success is True
        assert result.title == "My Page"
        assert result.action == "get_title"


@pytest.mark.asyncio
async def test_get_title_error_returns_failure() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].title = AsyncMock(side_effect=Exception("title error"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.get_title()
        assert result.success is False


@pytest.mark.asyncio
async def test_get_url_success() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].url = "https://example.com/current"
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        result = await tool.get_url()
        assert result.success is True
        assert result.url == "https://example.com/current"
        assert result.action == "get_url"


@pytest.mark.asyncio
async def test_get_url_no_page_before_ensure_browser() -> None:
    tool = BrowserTool()
    assert tool._current_url() is None


@pytest.mark.asyncio
async def test_get_title_playwright_missing_returns_failure() -> None:
    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
        tool = BrowserTool()
        result = await tool.get_title()
        assert result.success is False


@pytest.mark.asyncio
async def test_get_url_playwright_missing_returns_failure() -> None:
    with patch.dict(sys.modules, {"playwright": None, "playwright.async_api": None}):
        tool = BrowserTool()
        result = await tool.get_url()
        assert result.success is False


# ─────────────────────────────────────────────────────────────────────────────
# 13. close
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_close_calls_browser_close() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.close()
        objs["browser"].close.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_calls_playwright_stop() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.close()
        objs["pw_obj"].stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_close_clears_browser_reference() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.close()
        assert tool._browser is None


@pytest.mark.asyncio
async def test_close_clears_page_reference() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.close()
        assert tool._page is None


@pytest.mark.asyncio
async def test_close_without_browser_is_idempotent() -> None:
    tool = BrowserTool()
    await tool.close()  # must not raise
    await tool.close()


@pytest.mark.asyncio
async def test_close_browser_error_is_suppressed() -> None:
    modules, objs = _make_pw_modules()
    objs["browser"].close = AsyncMock(side_effect=Exception("already closed"))
    with patch.dict(sys.modules, modules):
        tool = BrowserTool()
        await tool._ensure_browser()
        await tool.close()  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 14. BrowserAutomationTool adapter
# ─────────────────────────────────────────────────────────────────────────────

def test_adapter_name() -> None:
    assert BrowserAutomationTool.name == "browser"


def test_adapter_has_description() -> None:
    assert len(BrowserAutomationTool.description) > 10


def test_adapter_has_required_parameters() -> None:
    params = BrowserAutomationTool.parameters
    assert "action" in params
    assert "url" in params
    assert "selector" in params
    assert "value" in params
    assert "expression" in params


def test_adapter_action_is_required() -> None:
    assert BrowserAutomationTool.parameters["action"]["required"] is True


@pytest.mark.asyncio
async def test_adapter_navigate_success() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="navigate", url="https://example.com")
        assert result.success is True


@pytest.mark.asyncio
async def test_adapter_navigate_missing_url_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="navigate")
        assert result.success is False
        assert result.error is not None


@pytest.mark.asyncio
async def test_adapter_click_missing_selector_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="click")
        assert result.success is False


@pytest.mark.asyncio
async def test_adapter_fill_missing_value_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="fill", selector="#q")
        assert result.success is False


@pytest.mark.asyncio
async def test_adapter_evaluate_missing_expression_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="evaluate")
        assert result.success is False


@pytest.mark.asyncio
async def test_adapter_unknown_action_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="teleport")
        assert result.success is False
        assert "teleport" in result.error


@pytest.mark.asyncio
async def test_adapter_extract_links_result_contains_metadata() -> None:
    modules, objs = _make_pw_modules()
    objs["page"].eval_on_selector_all = AsyncMock(return_value=["https://a.com"])
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="extract_links")
        assert result.success is True


@pytest.mark.asyncio
async def test_adapter_get_schema_returns_valid_schema() -> None:
    adapter = BrowserAutomationTool()
    schema = adapter.get_schema()
    assert schema["name"] == "browser"
    assert "parameters" in schema


@pytest.mark.asyncio
async def test_adapter_screenshot_with_url() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="screenshot", url="https://example.com")
        assert result.success is True


@pytest.mark.asyncio
async def test_adapter_wait_for_missing_selector_returns_error() -> None:
    modules, objs = _make_pw_modules()
    with patch.dict(sys.modules, modules):
        adapter = BrowserAutomationTool()
        result = await adapter.execute(action="wait_for")
        assert result.success is False
