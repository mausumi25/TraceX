"""
TraceX — Syntax Checker
Detects syntax errors BEFORE execution using language-native tools.

Python      → compile()
C/C++       → gcc/g++ -fsyntax-only
Java        → javac
JavaScript  → skipped (no native checker)

Key design: for LeetCode-style code (class Solution, no #include / no main),
we inject the necessary boilerplate before the syntax check so that valid
LeetCode code is never flagged as a false-positive error.
"""

import subprocess
import tempfile
import os
import re
from dataclasses import dataclass


@dataclass
class SyntaxError_:
    line: int        # 1-based line number (-1 if unknown)
    col: int         # 1-based column (-1 if unknown)
    message: str     # human-readable error message
    language: str


# ── Python ────────────────────────────────────────────────────

def check_python(source: str) -> SyntaxError_ | None:
    """Use compile() to catch SyntaxError before execution."""
    try:
        compile(source, "<string>", "exec")
        return None
    except SyntaxError as e:
        return SyntaxError_(
            line=e.lineno or -1,
            col=e.offset or -1,
            message=e.msg,
            language="Python",
        )
    except Exception as e:
        return SyntaxError_(line=-1, col=-1, message=str(e), language="Python")


# ── Subprocess helper ─────────────────────────────────────────

def _run_compiler(cmd: list[str]) -> tuple[str, str, int]:
    """Run a compiler command. Returns (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout, result.stderr, result.returncode
    except FileNotFoundError:
        return "", f"Compiler not found: {cmd[0]}", -1
    except subprocess.TimeoutExpired:
        return "", "Compiler timed out", -1


# ── C ─────────────────────────────────────────────────────────

def check_c(source: str) -> SyntaxError_ | None:
    """Use gcc -fsyntax-only to detect C syntax errors."""
    with tempfile.NamedTemporaryFile(suffix=".c", delete=False, mode="w") as f:
        f.write(source)
        fname = f.name
    try:
        _, stderr, rc = _run_compiler(["gcc", "-fsyntax-only", fname])
        if rc == 0:
            return None
        return _parse_gcc_error(stderr, "C")
    finally:
        os.unlink(fname)


# ── C++ ───────────────────────────────────────────────────────

def _prepare_cpp(source: str) -> tuple[str, int]:
    """
    For LeetCode-style C++ (class Solution, no headers, no main):
    prepend #include <bits/stdc++.h> and append a stub main().
    Returns (normalized_source, number_of_header_lines_prepended).
    """
    has_include  = "#include" in source
    has_main     = bool(re.search(r"\bmain\s*\(", source))
    is_lc_style  = bool(re.search(r"\bclass\s+Solution\b", source))

    prefix = ""
    if not has_include:
        prefix = "#include <bits/stdc++.h>\nusing namespace std;\n"

    suffix = ""
    if is_lc_style and not has_main:
        suffix = "\nint main() { return 0; }\n"

    normalized  = prefix + source + suffix
    extra_lines = len(prefix.splitlines())
    return normalized, extra_lines


def check_cpp(source: str) -> SyntaxError_ | None:
    """
    Use g++ -fsyntax-only -std=c++17 to detect C++ syntax errors.
    Normalizes LeetCode-style code first to avoid false-positives.
    """
    normalized, extra_lines = _prepare_cpp(source)

    with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False, mode="w") as f:
        f.write(normalized)
        fname = f.name
    try:
        _, stderr, rc = _run_compiler(
            ["g++", "-fsyntax-only", "-std=c++17", fname]
        )
        if rc == 0:
            return None
        err = _parse_gcc_error(stderr, "C++")
        # Shift reported line back to the user's original source
        if err.line > 0:
            err.line = max(1, err.line - extra_lines)
        return err
    finally:
        os.unlink(fname)


# ── Java ──────────────────────────────────────────────────────

def _prepare_java(source: str) -> str:
    """
    If the Java source has no main() (bare class Solution),
    inject a stub main() so javac compiles without 'no main method'.
    """
    if re.search(r"\bmain\s*\(", source):
        return source
    stub = "\n    public static void main(String[] args) {}\n"
    last = source.rfind("}")
    if last != -1:
        return source[:last] + stub + source[last:]
    return source


def check_java(source: str) -> SyntaxError_ | None:
    """Use javac to detect Java syntax errors."""
    normalized = _prepare_java(source)
    m = re.search(r"(?:public\s+)?class\s+(\w+)", normalized)
    class_name = m.group(1) if m else "Solution"

    with tempfile.TemporaryDirectory() as tmpdir:
        fname = os.path.join(tmpdir, f"{class_name}.java")
        with open(fname, "w") as f:
            f.write(normalized)
        _, stderr, rc = _run_compiler(["javac", fname])
        if rc == 0:
            return None
        return _parse_javac_error(stderr, fname)


# ── Error parsers ─────────────────────────────────────────────

def _parse_gcc_error(stderr: str, language: str) -> SyntaxError_:
    """Parse gcc/g++ error output: filename:line:col: error: msg"""
    match = re.search(r":(\d+):(\d+):\s*error:\s*(.+)", stderr)
    if match:
        return SyntaxError_(
            line=int(match.group(1)),
            col=int(match.group(2)),
            message=match.group(3).strip(),
            language=language,
        )
    first = stderr.strip().splitlines()[0] if stderr.strip() else "Unknown error"
    return SyntaxError_(line=-1, col=-1, message=first, language=language)


def _parse_javac_error(stderr: str, fname: str) -> SyntaxError_:
    """Parse javac error output: filename:line: error: msg"""
    match = re.search(r":(\d+):\s*error:\s*(.+)", stderr)
    if match:
        return SyntaxError_(
            line=int(match.group(1)),
            col=-1,
            message=match.group(2).strip(),
            language="Java",
        )
    first = stderr.strip().splitlines()[0] if stderr.strip() else "Unknown error"
    return SyntaxError_(line=-1, col=-1, message=first, language="Java")


# ── Public API ────────────────────────────────────────────────

_CHECKERS = {
    "Python":     check_python,
    "C":          check_c,
    "C++":        check_cpp,
    "Java":       check_java,
    "JavaScript": lambda _: None,   # No native checker — Node is too slow
}


def check_syntax(source: str, language: str) -> SyntaxError_ | None:
    """
    Returns SyntaxError_ if a syntax error is found, else None.
    """
    checker = _CHECKERS.get(language)
    if checker is None:
        return None
    return checker(source.strip())
