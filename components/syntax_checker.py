"""
TraceX — Syntax Checker
Detects syntax errors BEFORE execution using language-native tools.

Python  → compile()
C/C++   → gcc/g++ -fsyntax-only (if available)
Java    → javac (if available)
"""

import subprocess
import tempfile
import os
from dataclasses import dataclass


@dataclass
class SyntaxError_:
    line: int        # 1-based line number (-1 if unknown)
    col: int         # 1-based column (-1 if unknown)
    message: str     # human-readable error message
    language: str


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


def _run_compiler(cmd: list[str]) -> tuple[str, str, int]:
    """Run a compiler command, return (stdout, stderr, returncode)."""
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


def check_cpp(source: str) -> SyntaxError_ | None:
    """Use g++ -fsyntax-only to detect C++ syntax errors."""
    with tempfile.NamedTemporaryFile(suffix=".cpp", delete=False, mode="w") as f:
        f.write(source)
        fname = f.name
    try:
        _, stderr, rc = _run_compiler(["g++", "-fsyntax-only", fname])
        if rc == 0:
            return None
        return _parse_gcc_error(stderr, "C++")
    finally:
        os.unlink(fname)


def check_java(source: str) -> SyntaxError_ | None:
    """Use javac to detect Java syntax errors."""
    with tempfile.NamedTemporaryFile(
        suffix=".java", delete=False, mode="w", prefix="Main"
    ) as f:
        f.write(source)
        fname = f.name
    try:
        _, stderr, rc = _run_compiler(["javac", fname])
        if rc == 0:
            return None
        return _parse_javac_error(stderr, fname)
    finally:
        os.unlink(fname)


def _parse_gcc_error(stderr: str, language: str) -> SyntaxError_:
    """Parse gcc/g++ error output: filename:line:col: error: msg"""
    import re
    match = re.search(r":(\d+):(\d+):\s*error:\s*(.+)", stderr)
    if match:
        return SyntaxError_(
            line=int(match.group(1)),
            col=int(match.group(2)),
            message=match.group(3).strip(),
            language=language,
        )
    # Fallback
    first_line = stderr.strip().splitlines()[0] if stderr.strip() else "Unknown error"
    return SyntaxError_(line=-1, col=-1, message=first_line, language=language)


def _parse_javac_error(stderr: str, fname: str) -> SyntaxError_:
    """Parse javac error output: filename:line: error: msg"""
    import re
    match = re.search(r":(\d+):\s*error:\s*(.+)", stderr)
    if match:
        return SyntaxError_(
            line=int(match.group(1)),
            col=-1,
            message=match.group(2).strip(),
            language="Java",
        )
    first_line = stderr.strip().splitlines()[0] if stderr.strip() else "Unknown error"
    return SyntaxError_(line=-1, col=-1, message=first_line, language="Java")


_CHECKERS = {
    "Python":     check_python,
    "C":          check_c,
    "C++":        check_cpp,
    "Java":       check_java,
    "JavaScript": lambda _: None,   # No native checker yet
}


def check_syntax(source: str, language: str) -> SyntaxError_ | None:
    """
    Main entry point. Returns SyntaxError_ if a syntax error is found,
    or None if the code is syntactically valid.
    """
    checker = _CHECKERS.get(language)
    if checker is None:
        return None
    return checker(source.strip())
