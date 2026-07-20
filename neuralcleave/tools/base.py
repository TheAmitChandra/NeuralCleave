"""Tool abstract base class and shared data types.

A Tool is a discrete capability the agent can invoke during a pipeline run.
Tools are:
  - Declared with a name, description, and typed parameter schema
  - Invoked with a plain dict of arguments (validated before execution)
  - Sandboxed: each tool declares what permissions it needs
  - Stateless: tools must not store state between calls

Tool authors subclass ``Tool`` and implement ``execute``.

Example::

    class MyTool(Tool):
        name = "my_tool"
        description = "Does something useful."
        parameters = {
            "query": {"type": "str", "description": "The search query"},
        }
        permissions = ["network"]

        async def execute(self, query: str) -> ToolResult:
            result = await some_api(query)
            return ToolResult(output=result, tool=self.name)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Returned by every tool execution."""

    tool: str
    output: Any
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None

    def to_prompt_block(self) -> str:
        """Serialise for injection into the LLM prompt."""
        if self.error:
            return f"[TOOL:{self.tool} ERROR] {self.error}"
        output = str(self.output) if not isinstance(self.output, str) else self.output
        return f"[TOOL:{self.tool}]\n{output}"


class Tool(ABC):
    """Abstract base for all NeuralCleave tools.

    Class attributes (declare on subclass):
        name:        Unique tool identifier, snake_case.
        description: One sentence used by the LLM to decide when to call it.
        parameters:  Dict of {param_name: {"type": str, "description": str, "required": bool}}.
        permissions: List of required permission strings, e.g. ["network", "filesystem:read"].
    """

    name: str
    description: str
    parameters: dict[str, dict[str, Any]] = {}
    permissions: list[str] = []

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Run the tool with the given arguments.

        Args should match the keys declared in ``parameters``.
        Returns a ToolResult — never raises; wrap errors in ToolResult.error.
        """
        ...

    def get_schema(self) -> dict[str, Any]:
        """Return JSON Schema describing the tool for LLM function calling."""
        props: dict[str, Any] = {}
        required: list[str] = []
        for param_name, spec in self.parameters.items():
            props[param_name] = {
                "type": _py_to_json_type(spec.get("type", "str")),
                "description": spec.get("description", ""),
            }
            if spec.get("required", True):
                required.append(param_name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


def _py_to_json_type(py_type: str) -> str:
    mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
    }
    return mapping.get(py_type, "string")
