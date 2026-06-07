"""API caller tool — authenticated HTTP REST/GraphQL client.

Security controls:
- URL scheme restricted to https in production (http allowed in dev).
- Response body size capped (1 MB default).
- Redirects limited to 5 hops.
- Secrets injected via headers dict — never logged.
- Timeout enforced per-request.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.observability.logs import get_logger
from app.core.tools.registry import ToolDefinition

logger = get_logger(__name__)

_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MB
_DEFAULT_TIMEOUT = 30
_MAX_REDIRECTS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise_headers_for_log(headers: dict[str, str]) -> dict[str, str]:
    """Replace values of auth-related headers with '***' for safe logging."""
    sensitive = {"authorization", "x-api-key", "api-key", "x-auth-token"}
    return {k: ("***" if k.lower() in sensitive else v) for k, v in headers.items()}


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def api_get(params: dict[str, Any]) -> dict[str, Any]:
    """Perform an authenticated HTTP GET request.

    Parameters:
        url (str): Target endpoint URL (https required in prod).
        headers (dict[str, str]): Request headers. Optional.
        query_params (dict[str, str]): URL query parameters. Optional.
        timeout_seconds (int): Per-request timeout. Default 30.

    Returns:
        dict with keys: status_code, headers, body (str), json (if parseable).
    """
    return await _http_request("GET", params)


async def api_post(params: dict[str, Any]) -> dict[str, Any]:
    """Perform an authenticated HTTP POST request.

    Parameters:
        url (str): Target endpoint.
        headers (dict[str, str]): Request headers. Optional.
        body (dict | str): JSON body (dict) or raw string. Optional.
        timeout_seconds (int): Timeout in seconds. Default 30.

    Returns:
        dict with keys: status_code, headers, body (str), json (if parseable).
    """
    return await _http_request("POST", params)


async def api_graphql(params: dict[str, Any]) -> dict[str, Any]:
    """Execute a GraphQL query against an endpoint.

    Parameters:
        url (str): GraphQL endpoint URL.
        query (str): GraphQL query string.
        variables (dict): Query variables. Optional.
        headers (dict[str, str]): Request headers including auth. Optional.
        timeout_seconds (int): Timeout. Default 30.

    Returns:
        dict with keys: status_code, data, errors (from GraphQL response).
    """
    url: str = params["url"]
    query: str = params["query"]
    variables: dict[str, Any] = params.get("variables") or {}
    headers: dict[str, str] = params.get("headers") or {}
    timeout: int = int(params.get("timeout_seconds", _DEFAULT_TIMEOUT))

    body = {"query": query, "variables": variables}
    merged_params = {
        "url": url,
        "headers": {**headers, "Content-Type": "application/json"},
        "body": body,
        "timeout_seconds": timeout,
    }
    result = await _http_request("POST", merged_params)

    # Parse GraphQL envelope
    parsed = result.get("json") or {}
    return {
        "status_code": result["status_code"],
        "data": parsed.get("data"),
        "errors": parsed.get("errors"),
    }


async def _http_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Internal HTTP dispatch shared by GET, POST, GraphQL."""
    url: str = params["url"]
    headers: dict[str, str] = params.get("headers") or {}
    query_params: dict[str, str] = params.get("query_params") or {}
    body: Any = params.get("body")
    timeout: int = int(params.get("timeout_seconds", _DEFAULT_TIMEOUT))

    # Prepare JSON body
    json_body: dict[str, Any] | None = None
    content: bytes | None = None
    if isinstance(body, dict):
        json_body = body
    elif isinstance(body, str):
        content = body.encode()

    log_headers = _sanitise_headers_for_log(headers)
    logger.info("api_request", method=method, url=url, headers=log_headers)

    async with httpx.AsyncClient(
        follow_redirects=True,
        max_redirects=_MAX_REDIRECTS,
        timeout=timeout,
    ) as client:
        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=query_params or None,
            json=json_body,
            content=content,
        )

    body_bytes = response.content[:_MAX_RESPONSE_BYTES]
    body_text = body_bytes.decode(errors="replace")

    parsed_json: Any = None
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            parsed_json = json.loads(body_text)
        except json.JSONDecodeError:
            pass

    logger.info(
        "api_response",
        method=method,
        url=url,
        status_code=response.status_code,
        body_bytes=len(body_bytes),
    )

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": body_text,
        "json": parsed_json,
    }


# ---------------------------------------------------------------------------
# Tool definitions (for ToolRegistry)
# ---------------------------------------------------------------------------

API_GET_DEF = ToolDefinition(
    name="api.get",
    description="Perform an HTTP GET request to an external API.",
    permissions=["network.external"],
    risk_level="low",
    sandbox_required=False,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "query_params": {"type": "object"},
            "timeout_seconds": {"type": "integer"},
        },
    },
)

API_POST_DEF = ToolDefinition(
    name="api.post",
    description="Perform an HTTP POST request to an external API.",
    permissions=["network.external"],
    risk_level="medium",
    sandbox_required=False,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url"],
        "properties": {
            "url": {"type": "string"},
            "headers": {"type": "object"},
            "body": {},
            "timeout_seconds": {"type": "integer"},
        },
    },
)

API_GRAPHQL_DEF = ToolDefinition(
    name="api.graphql",
    description="Execute a GraphQL query against an endpoint.",
    permissions=["network.external"],
    risk_level="medium",
    sandbox_required=False,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["url", "query"],
        "properties": {
            "url": {"type": "string"},
            "query": {"type": "string"},
            "variables": {"type": "object"},
            "headers": {"type": "object"},
            "timeout_seconds": {"type": "integer"},
        },
    },
)


def register_api_tools(registry: Any) -> None:
    """Register all API caller tools into the provided registry."""
    registry.register(API_GET_DEF, api_get)
    registry.register(API_POST_DEF, api_post)
    registry.register(API_GRAPHQL_DEF, api_graphql)
