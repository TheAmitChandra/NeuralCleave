"""WriteSkillTool — lets the LLM propose a new skill for human review.

This is the key tool that enables NeuralCleave's self-modifying behaviour:
the agent can write new Python code during a conversation and queue it as a
named skill proposal — a human then approves or rejects it via
``neuralcleave skills review approve|reject`` (or the matching REST routes)
before it is ever written to disk or loaded. This review gate (P8 of the
2026-08-17 gap analysis) replaced immediate write+load: agent-authored code
no longer runs the moment the agent decides to write it.

The skill code must be valid Python. The module may contain:
- Plain functions (auto-wrapped as tools via :class:`DynamicFunctionTool`)
- An explicit :class:`~neuralcleave.plugins.base.Plugin` subclass

Blocked imports (``subprocess``, ``ctypes``, etc.) are rejected at proposal
time, before a human ever needs to review them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neuralcleave.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    from neuralcleave.skills.writer import SkillWriter


class WriteSkillTool(Tool):
    """Propose a new Python skill for human review — does not load it.

    Parameters
    ----------
    name : str
        Unique skill name (lowercase, underscores OK).
    code : str
        Complete Python source code for the skill.
    description : str (optional)
        Short description used when no docstring or Plugin.metadata is found.
    """

    name = "write_skill"
    description = (
        "Propose a new Python skill (tool) for human review. The code may "
        "contain plain functions or a Plugin subclass. Blocked imports "
        "(subprocess, ctypes) are rejected. The skill is NOT loaded until a "
        "human approves the proposal — this does not immediately grant new "
        "capabilities."
    )
    parameters: dict[str, dict[str, Any]] = {
        "name": {
            "type": "str",
            "description": "Unique skill name — lowercase letters, digits, underscores.",
            "required": True,
        },
        "code": {
            "type": "str",
            "description": "Complete Python source code for the skill module.",
            "required": True,
        },
        "description": {
            "type": "str",
            "description": "Optional one-line description of what the skill does.",
            "required": False,
        },
    }
    permissions: list[str] = ["filesystem:write"]

    def __init__(self, skill_writer: "SkillWriter") -> None:
        self._writer = skill_writer

    async def execute(self, **kwargs: Any) -> ToolResult:
        skill_name: str = kwargs.get("name", "")
        code: str = kwargs.get("code", "")
        description: str = kwargs.get("description", "")

        if not skill_name:
            return ToolResult(tool=self.name, output=None, error="'name' is required")
        if not code:
            return ToolResult(tool=self.name, output=None, error="'code' is required")

        try:
            proposal = self._writer.propose_skill(skill_name, code, description)
            message = (
                f"Skill '{skill_name}' proposed for review (id={proposal.id[:8]}). "
                "A human must approve it before it can run."
            )
            return ToolResult(tool=self.name, output=message)
        except (ValueError, RuntimeError, OSError) as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))


class ListSkillsTool(Tool):
    """List all user-written skills and whether they are currently loaded."""

    name = "list_skills"
    description = "List all user-written skills that have been saved to the skills directory."
    parameters: dict[str, dict[str, Any]] = {}
    permissions: list[str] = []

    def __init__(self, skill_writer: "SkillWriter") -> None:
        self._writer = skill_writer

    async def execute(self, **kwargs: Any) -> ToolResult:
        skills = self._writer.list_skills()
        if not skills:
            return ToolResult(tool=self.name, output="No user-written skills found.")
        lines = [f"- {s.name} ({'loaded' if s.loaded else 'not loaded'})" for s in skills]
        return ToolResult(tool=self.name, output="\n".join(lines))


class DeleteSkillTool(Tool):
    """Delete a user-written skill and unregister it from the gateway."""

    name = "delete_skill"
    description = "Delete a user-written skill by name and unload it from the gateway."
    parameters: dict[str, dict[str, Any]] = {
        "name": {
            "type": "str",
            "description": "Name of the skill to delete.",
            "required": True,
        }
    }
    permissions: list[str] = ["filesystem:write"]

    def __init__(self, skill_writer: "SkillWriter") -> None:
        self._writer = skill_writer

    async def execute(self, **kwargs: Any) -> ToolResult:
        skill_name: str = kwargs.get("name", "")
        if not skill_name:
            return ToolResult(tool=self.name, output=None, error="'name' is required")
        try:
            self._writer.delete_skill(skill_name)
            return ToolResult(tool=self.name, output=f"Skill '{skill_name}' deleted.")
        except FileNotFoundError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))
        except Exception as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))
