"""Unit tests for cortexflow_ai.hub.scanner — PackageScanner + ScanResult."""

from __future__ import annotations

import textwrap

import pytest

from cortexflow_ai.hub.scanner import PackageScanner, ScanResult


@pytest.fixture()
def scanner():
    return PackageScanner()


# ---------------------------------------------------------------------------
# ScanResult
# ---------------------------------------------------------------------------


def test_scan_result_defaults():
    r = ScanResult(safe=True)
    assert r.warnings == []
    assert r.errors == []
    assert r.scanned_files == 0


def test_scan_result_to_dict():
    r = ScanResult(safe=False, errors=["e1"], warnings=["w1"], scanned_files=2)
    d = r.to_dict()
    assert d == {"safe": False, "errors": ["e1"], "warnings": ["w1"], "scanned_files": 2}


# ---------------------------------------------------------------------------
# Clean code
# ---------------------------------------------------------------------------


def test_clean_code_is_safe(scanner):
    code = textwrap.dedent("""\
        def greet(name: str) -> str:
            return f"Hello, {name}!"
    """)
    result = scanner.scan_code(code)
    assert result.safe is True
    assert result.errors == []
    assert result.scanned_files == 1


# ---------------------------------------------------------------------------
# Blocked imports — AST pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("import_line,module", [
    ("import subprocess", "subprocess"),
    ("import ctypes", "ctypes"),
    ("import winreg", "winreg"),
    ("import msvcrt", "msvcrt"),
    ("import multiprocessing", "multiprocessing"),
    ("import _thread", "_thread"),
    ("import mmap", "mmap"),
    ("import cffi", "cffi"),
    ("import cython", "cython"),
    ("import fcntl", "fcntl"),
    ("import termios", "termios"),
    ("import tty", "tty"),
    ("import pty", "pty"),
])
def test_blocked_direct_import(scanner, import_line, module):
    result = scanner.scan_code(import_line)
    assert result.safe is False
    assert any(module in e for e in result.errors)


def test_blocked_from_import(scanner):
    result = scanner.scan_code("from subprocess import run")
    assert result.safe is False
    assert any("subprocess" in e for e in result.errors)


def test_blocked_submodule_import(scanner):
    result = scanner.scan_code("import multiprocessing.pool")
    assert result.safe is False
    assert any("multiprocessing" in e for e in result.errors)


def test_unblocked_import_is_safe(scanner):
    result = scanner.scan_code("import os\nimport sys\nimport json")
    assert result.safe is True


# ---------------------------------------------------------------------------
# Blocked patterns — regex pass (warnings)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code,expected_fragment", [
    ("result = eval(user_input)", "eval"),
    ("exec(code_str)", "exec"),
    ("mod = __import__('os')", "__import__"),
    ("obj = compile(src, '', 'exec')", "compile"),
    ("os.system('ls')", "os.system"),
    ("os.popen('cat /etc/passwd')", "os.popen"),
    ("socket.connect(('evil.com', 443))", "socket.connect"),
    ("urllib.request.urlopen(url)", "urllib.request"),
    ("requests.get(url)", "requests"),
    ("httpx.post(url, json=data)", "httpx"),
    ("f = open('out.txt', 'w')", "write mode"),
    ("k = getattr(obj, '__dict__')", "getattr with dunder"),
    ("token = os.environ.get('OPENAI_API_KEY')", "credential"),
])
def test_blocked_pattern_produces_warning(scanner, code, expected_fragment):
    result = scanner.scan_code(code)
    assert any(expected_fragment.lower() in w.lower() for w in result.warnings), (
        f"Expected warning containing {expected_fragment!r}, got: {result.warnings}"
    )


def test_comment_line_skipped(scanner):
    code = "# eval('danger')\n# exec('rm -rf /')"
    result = scanner.scan_code(code)
    assert result.safe is True
    assert result.warnings == []


def test_blocked_pattern_does_not_mark_unsafe(scanner):
    result = scanner.scan_code("eval(x)")
    assert result.safe is True
    assert result.warnings != []
    assert result.errors == []


# ---------------------------------------------------------------------------
# Syntax error
# ---------------------------------------------------------------------------


def test_syntax_error_produces_error(scanner):
    result = scanner.scan_code("def broken(")
    assert result.safe is False
    assert any("syntax error" in e.lower() for e in result.errors)
    assert result.scanned_files == 1


# ---------------------------------------------------------------------------
# Multiple blocked imports in one file
# ---------------------------------------------------------------------------


def test_multiple_blocked_imports_all_reported(scanner):
    code = "import subprocess\nimport ctypes\n"
    result = scanner.scan_code(code)
    assert result.safe is False
    assert len(result.errors) == 2


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------


def test_scan_directory_no_py_files(scanner, tmp_path):
    result = scanner.scan_directory(tmp_path)
    assert result.safe is True
    assert any("No .py files" in w for w in result.warnings)


def test_scan_directory_clean_files(scanner, tmp_path):
    (tmp_path / "skill.py").write_text("def hi(): return 'hi'")
    result = scanner.scan_directory(tmp_path)
    assert result.safe is True
    assert result.scanned_files == 1


def test_scan_directory_blocked_import(scanner, tmp_path):
    (tmp_path / "bad.py").write_text("import subprocess\n")
    result = scanner.scan_directory(tmp_path)
    assert result.safe is False
    assert result.scanned_files == 1


def test_scan_directory_merges_multiple_files(scanner, tmp_path):
    (tmp_path / "a.py").write_text("import subprocess\n")
    (tmp_path / "b.py").write_text("import ctypes\n")
    result = scanner.scan_directory(tmp_path)
    assert result.safe is False
    assert result.scanned_files == 2
    assert len(result.errors) == 2


def test_scan_directory_recursive(scanner, tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.py").write_text("import winreg\n")
    result = scanner.scan_directory(tmp_path)
    assert result.safe is False
    assert result.scanned_files == 1


def test_scan_directory_mixed_safe_and_blocked(scanner, tmp_path):
    (tmp_path / "safe.py").write_text("def hello(): pass\n")
    (tmp_path / "danger.py").write_text("import ctypes\n")
    result = scanner.scan_directory(tmp_path)
    assert result.safe is False
    assert result.scanned_files == 2
