"""SkillWriter — write, load, and manage user-defined skills at runtime.

Skills are Python modules stored in ``~/.NeuralCleave/skills/<name>/skill.py``.
Each module must contain either:

- **Plain functions** — any top-level callable is auto-wrapped as a
  :class:`~neuralcleave.skills.dynamic.DynamicFunctionTool`.
- **A Plugin subclass** — discovered and instantiated directly, giving full
  control over metadata, lifecycle hooks, and tool schemas.

Usage example::

    from neuralcleave.skills.writer import SkillWriter

    writer = SkillWriter(plugin_registry=registry)
    code = "def greet(name: str) -> str:\\n    return f'Hello, {name}!'"
    writer.write_skill(name="greet", code=code)
    await writer.load_into_registry("greet")

    for info in writer.list_skills():
        print(info.name, "loaded:", info.loaded)

    writer.delete_skill("greet")
"""

from __future__ import annotations

import ast
import importlib.util
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neuralcleave.plugins.base import Plugin
    from neuralcleave.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

_DEFAULT_SKILLS_DIR = Path.home() / ".NeuralCleave" / "skills"

# Top-level module names that user skills are not allowed to import.
_BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        "subprocess",
        "ctypes",
        "winreg",
        "msvcrt",
        "pty",
        "tty",
        "termios",
        "fcntl",
    }
)

_VALID_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


@dataclass
class SkillInfo:
    """Metadata about a user-written skill on disk."""

    name: str
    path: Path
    loaded: bool
    description: str = ""


def _validate_skill_name(name: str) -> str:
    """Return *name* if valid, otherwise raise :class:`ValueError`."""
    if not name:
        raise ValueError("Skill name must not be empty")
    name = name.lower().replace("-", "_")
    if not all(c in _VALID_NAME_CHARS for c in name):
        raise ValueError(
            f"Skill name '{name}' contains invalid characters — "
            "use lowercase letters, digits, and underscores only"
        )
    if name[0].isdigit():
        raise ValueError(f"Skill name '{name}' must not start with a digit")
    return name


class SkillWriter:
    """Write, load, and manage user-defined skills stored under *skills_dir*.

    Args:
        plugin_registry: :class:`~neuralcleave.plugins.registry.PluginRegistry`
                         to register loaded skills into. May be ``None`` for
                         standalone / test use.
        skills_dir:      Root directory for skill storage. Defaults to
                         ``~/.NeuralCleave/skills``.
    """

    def __init__(
        self,
        plugin_registry: "PluginRegistry | None" = None,
        skills_dir: Path | None = None,
    ) -> None:
        self._registry = plugin_registry
        self._skills_dir = skills_dir or _DEFAULT_SKILLS_DIR
        self._loaded_skills: dict[str, "Plugin"] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_skill(
        self,
        name: str,
        code: str,
        description: str = "",
    ) -> str:
        """Validate *code*, persist it, and load it into the registry.

        Args:
            name:        Unique skill name (lowercase, underscores allowed).
            code:        Python source code for the skill.
            description: Optional description used when the code contains no
                         docstring / Plugin.metadata.

        Returns:
            Human-readable success message listing loaded tool names.

        Raises:
            ValueError: If the name is invalid, the code has syntax errors,
                        or blocked imports are found.
        """
        name = _validate_skill_name(name)
        errors = self.validate_code(code)
        if errors:
            raise ValueError(f"Skill code validation failed: {'; '.join(errors)}")

        skill_path = self._skill_path(name)
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        skill_path.write_text(code, encoding="utf-8")
        logger.info("skill.written name=%s path=%s", name, skill_path)

        plugin = self._load_skill_module(name, skill_path, description)
        self._loaded_skills[name] = plugin

        if self._registry is not None:
            if name in {p.metadata.name for p in self._registry.all_plugins}:
                self._registry.unregister(name)
            self._registry.register(plugin)

        tool_names = [t.name for t in plugin.get_tools()]
        logger.info("skill.loaded name=%s tools=%s", name, tool_names)
        suffix = ", ".join(tool_names) if tool_names else "(none)"
        return f"Skill '{name}' written and loaded. Tools: {suffix}"

    async def load_into_registry(self, name: str) -> bool:
        """Call :meth:`~PluginRegistry.reload_plugin` for *name*.

        Returns ``True`` on success, ``False`` if the skill is not yet written
        or the registry is not set.
        """
        if self._registry is None:
            return False
        if name not in self._loaded_skills:
            return False
        return await self._registry.reload_plugin(name)

    def list_skills(self) -> list[SkillInfo]:
        """Return metadata for all user-written skills found on disk."""
        if not self._skills_dir.exists():
            return []
        result: list[SkillInfo] = []
        for skill_dir in sorted(self._skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_path = skill_dir / "skill.py"
            if skill_path.exists():
                name = skill_dir.name
                plugin = self._loaded_skills.get(name)
                desc = plugin.metadata.description if plugin else ""
                result.append(
                    SkillInfo(
                        name=name,
                        path=skill_path,
                        loaded=name in self._loaded_skills,
                        description=desc,
                    )
                )
        return result

    def get_skill_code(self, name: str) -> str:
        """Return the source code of skill *name*.

        Raises:
            FileNotFoundError: If the skill does not exist on disk.
        """
        path = self._skill_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Skill '{name}' not found at {path}")
        return path.read_text(encoding="utf-8")

    def delete_skill(self, name: str) -> None:
        """Delete skill *name* from disk and unregister it from the registry.

        Raises:
            FileNotFoundError: If the skill does not exist on disk.
        """
        skill_path = self._skill_path(name)
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill '{name}' not found")

        self._loaded_skills.pop(name, None)
        if self._registry is not None:
            self._registry.unregister(name)

        mod_key = f"_NeuralCleave_skill_{name}"
        sys.modules.pop(mod_key, None)

        shutil.rmtree(skill_path.parent, ignore_errors=True)
        logger.info("skill.deleted name=%s", name)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_code(self, code: str) -> list[str]:
        """Return a list of validation error strings (empty = valid).

        Checks:
        - Valid Python syntax (AST parse).
        - No blocked imports (``subprocess``, ``ctypes``, etc.).
        """
        errors: list[str] = []

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            errors.append(f"SyntaxError at line {exc.lineno}: {exc.msg}")
            return errors

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in _BLOCKED_IMPORTS:
                        errors.append(f"Blocked import: '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in _BLOCKED_IMPORTS:
                        errors.append(f"Blocked import: 'from {node.module} import ...'")

        return errors

    # ------------------------------------------------------------------
    # Module loading internals
    # ------------------------------------------------------------------

    def _skill_path(self, name: str) -> Path:
        return self._skills_dir / name / "skill.py"

    def _load_skill_module(
        self,
        name: str,
        skill_path: Path,
        description: str = "",
    ) -> "Plugin":
        """Load *skill_path* as a Python module and return a Plugin instance."""
        mod_name = f"_NeuralCleave_skill_{name}"
        sys.modules.pop(mod_name, None)

        spec = importlib.util.spec_from_file_location(mod_name, skill_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot create module spec for {skill_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            sys.modules.pop(mod_name, None)
            raise RuntimeError(f"Error executing skill module '{name}': {exc}") from exc

        plugin_cls = self._find_plugin_class(module)
        if plugin_cls is not None:
            return plugin_cls()

        return self._wrap_functions_as_plugin(module, name, description)

    def _find_plugin_class(self, module: Any) -> type | None:
        """Return the first Plugin subclass in *module*, or ``None``."""
        from neuralcleave.plugins.base import Plugin

        for attr_name in dir(module):
            obj = getattr(module, attr_name, None)
            if (
                obj is not None
                and isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
                and hasattr(obj, "metadata")
            ):
                return obj
        return None

    def _wrap_functions_as_plugin(
        self,
        module: Any,
        name: str,
        description: str,
    ) -> "Plugin":
        """Wrap all public callables in *module* as a :class:`DynamicPlugin`."""
        from neuralcleave.skills.dynamic import DynamicFunctionTool, DynamicPlugin

        tools = []
        mod_name = getattr(module, "__name__", "")
        for attr_name in sorted(dir(module)):
            if attr_name.startswith("_"):
                continue
            obj = getattr(module, attr_name, None)
            if obj is None or isinstance(obj, type):
                continue
            if not callable(obj):
                continue
            fn_module = getattr(obj, "__module__", "")
            if fn_module == mod_name or fn_module.startswith("_NeuralCleave_skill_"):
                tools.append(DynamicFunctionTool(obj))

        fallback = f"User-written skill: {name}"
        return DynamicPlugin(
            name=name,
            description=description or fallback,
            tools=tools,
        )
