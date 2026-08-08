"""JSON-RPC 2.0 types and MCP-specific message models.

All classes are plain dataclasses — no external dependencies.

JSON-RPC 2.0 wire format (newline-delimited over stdio):

    Request:       {"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
    Notification:  {"jsonrpc":"2.0","method":"notifications/initialized"}
    Response:      {"jsonrpc":"2.0","id":1,"result":{...}}
    Error:         {"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"..."}}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── JSON-RPC 2.0 error codes ──────────────────────────────────────────────────

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ── MCP protocol version ──────────────────────────────────────────────────────

MCP_PROTOCOL_VERSION = "2024-11-05"


# ── Core JSON-RPC types ───────────────────────────────────────────────────────


@dataclass
class JsonRpcRequest:
    """Parsed JSON-RPC 2.0 request or notification.

    A message without ``id`` is a notification — the server must not reply.
    """

    method: str
    id: int | str | None = None
    params: dict[str, Any] | None = None

    @property
    def is_notification(self) -> bool:
        return self.id is None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JsonRpcRequest":
        if "method" not in data:
            raise ValueError("Missing 'method' field in JSON-RPC request")
        return cls(
            method=data["method"],
            id=data.get("id"),
            params=data.get("params"),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "method": self.method}
        if self.id is not None:
            d["id"] = self.id
        if self.params is not None:
            d["params"] = self.params
        return d


@dataclass
class JsonRpcError:
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass
class JsonRpcResponse:
    """JSON-RPC 2.0 response (success or error)."""

    id: int | str | None
    result: Any = None
    error: JsonRpcError | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d

    @classmethod
    def ok(cls, id: int | str | None, result: Any) -> "JsonRpcResponse":
        return cls(id=id, result=result)

    @classmethod
    def err(
        cls,
        id: int | str | None,
        code: int,
        message: str,
        data: Any = None,
    ) -> "JsonRpcResponse":
        return cls(id=id, error=JsonRpcError(code=code, message=message, data=data))


# ── MCP-specific types ────────────────────────────────────────────────────────


@dataclass
class McpContent:
    """A single content item in a tools/call response."""

    type: str  # "text" | "image" | "resource"
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.text:
            d["text"] = self.text
        return d


@dataclass
class McpToolDescriptor:
    """MCP tool descriptor returned in tools/list."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


@dataclass
class McpServerInfo:
    """Server identity block in the initialize response."""

    name: str = "neuralcleave"
    version: str = "2.1.5"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version}


@dataclass
class McpCapabilities:
    """Server capability advertisement."""

    tools: bool = True
    resources: bool = False
    prompts: bool = False

    def to_dict(self) -> dict[str, Any]:
        caps: dict[str, Any] = {}
        if self.tools:
            caps["tools"] = {}
        if self.resources:
            caps["resources"] = {}
        if self.prompts:
            caps["prompts"] = {}
        return caps
