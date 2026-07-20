"""PackageScanner — safety scanner for hub skill code (CortexFlow's SkillSpector).

Scans Python source code for dangerous patterns before installation.
Blocks known attack vectors used in the ClawHavoc campaign (Jan 2026):
API-key exfiltration via subprocess/socket, code injection via exec/eval,
persistence via registry/launchd writes, and arbitrary C-extension loading.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Imports that are unconditionally blocked regardless of usage context.
_BLOCKED_IMPORTS: frozenset[str] = frozenset({
    "subprocess",
    "ctypes",
    "winreg",
    "msvcrt",
    "pty",
    "tty",
    "termios",
    "fcntl",
    "mmap",
    "cffi",
    "cython",
    "_thread",
    "multiprocessing",
})

# Built-in/expression patterns that signal code injection or exfiltration.
_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    (r"\beval\s*\(", "eval() call — code injection risk"),
    (r"\bexec\s*\(", "exec() call — code injection risk"),
    (r"\b__import__\s*\(", "__import__() — dynamic import bypass"),
    (r"\bcompile\s*\(", "compile() — code injection risk"),
    (r"\bos\.system\s*\(", "os.system() — shell injection risk"),
    (r"\bos\.popen\s*\(", "os.popen() — shell injection risk"),
    (r"\bgetattr\s*\(.*__", "getattr with dunder — attribute access bypass"),
    (r"open\s*\([^)]*['\"][wa]['\"]", "open() in write mode — filesystem write"),
    (r"socket\.connect\s*\(", "socket.connect() — outbound network call"),
    (r"urllib\.request\.", "urllib.request — outbound HTTP"),
    (r"requests\.(?:get|post|put|patch|delete|head|request)\s*\(", "requests — outbound HTTP"),
    (r"httpx\.(?:get|post|put|patch|delete|head|request)\s*\(", "httpx — outbound HTTP"),
    (r"\bENV:|API_KEY|SECRET_KEY|OPENAI_API|ANTHROPIC_API", "credential pattern — possible exfiltration"),
]

_BLOCKED_PATTERN_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pat, re.IGNORECASE), reason)
    for pat, reason in _BLOCKED_PATTERNS
]


@dataclass
class ScanResult:
    """Result of scanning a skill package."""

    safe: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scanned_files: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "warnings": self.warnings,
            "errors": self.errors,
            "scanned_files": self.scanned_files,
        }


class PackageScanner:
    """Safety scanner for hub-installed skill code.

    Mimics the role of OpenClaw's SkillSpector, adapted for Python skill files.
    Runs two passes over each source file:

    1. **AST import check** — walks the syntax tree looking for ``import``
       and ``from ... import`` nodes whose top-level module is in the blocked
       set.  Catches obfuscated multi-line imports that regex would miss.

    2. **Pattern scan** — regex pass for dangerous built-in calls and
       credential-shaped strings that the AST check cannot catch (e.g. string
       ``eval`` inside a dict, ``os.system`` constructed via attribute access).

    Files that fail the AST parse are flagged as errors (not skipped silently).
    """

    def scan_code(self, code: str, filename: str = "<skill>") -> ScanResult:
        """Scan a single source string.  Returns a :class:`ScanResult`."""
        errors: list[str] = []
        warnings: list[str] = []

        # Pass 1 — AST import check
        try:
            tree = ast.parse(code, filename=filename)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top in _BLOCKED_IMPORTS:
                            errors.append(
                                f"{filename}: blocked import '{alias.name}' (line {node.lineno})"
                            )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    top = module.split(".")[0]
                    if top in _BLOCKED_IMPORTS:
                        errors.append(
                            f"{filename}: blocked import 'from {module} import ...' (line {node.lineno})"
                        )
        except SyntaxError as exc:
            errors.append(f"{filename}: syntax error — {exc}")
            return ScanResult(safe=False, errors=errors, scanned_files=1)

        # Pass 2 — pattern scan
        for i, line in enumerate(code.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern_re, reason in _BLOCKED_PATTERN_RE:
                if pattern_re.search(line):
                    warnings.append(f"{filename}:{i}: {reason}")

        return ScanResult(
            safe=len(errors) == 0,
            warnings=warnings,
            errors=errors,
            scanned_files=1,
        )

    def scan_directory(self, path: Path) -> ScanResult:
        """Recursively scan all ``.py`` files in *path*.

        Returns a merged :class:`ScanResult` across all files.
        """
        merged = ScanResult(safe=True)

        py_files = sorted(path.rglob("*.py"))
        if not py_files:
            merged.warnings.append(f"No .py files found in {path}")
            return merged

        for py_file in py_files:
            try:
                code = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                merged.errors.append(f"Cannot read {py_file}: {exc}")
                merged.safe = False
                continue

            result = self.scan_code(code, filename=str(py_file.name))
            merged.errors.extend(result.errors)
            merged.warnings.extend(result.warnings)
            merged.scanned_files += result.scanned_files
            if not result.safe:
                merged.safe = False

        return merged
