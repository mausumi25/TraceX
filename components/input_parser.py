"""
TraceX — LeetCode Input Parser
Uses Python AST to detect functions, extract parameters,
parse user input strings, and inject test-call code.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FunctionSignature:
    name: str
    params: list[str]
    type_hints: dict[str, str]   # param → hint string (may be empty)
    return_hint: str             # return type hint string (may be empty)
    is_method: bool = False      # True if inside a class (e.g. Solution)
    class_name: str = ""


# ── AST Detection ─────────────────────────────────────────────

def detect_functions(source: str) -> list[FunctionSignature]:
    """
    Parse `source` with AST and return all top-level or
    class-method function signatures (skipping __init__, __dunder__).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    sigs: list[FunctionSignature] = []

    def _hint(annotation) -> str:
        if annotation is None:
            return ""
        return ast.unparse(annotation)

    def _extract(func_node: ast.FunctionDef, is_method: bool, class_name: str):
        params = []
        hints  = {}
        args   = func_node.args

        all_args = args.posonlyargs + args.args + args.kwonlyargs
        if is_method and all_args and all_args[0].arg == "self":
            all_args = all_args[1:]   # always skip self

        for arg in all_args:
            params.append(arg.arg)
            if arg.annotation:
                hints[arg.arg] = _hint(arg.annotation)

        sigs.append(FunctionSignature(
            name        = func_node.name,
            params      = params,
            type_hints  = hints,
            return_hint = _hint(func_node.returns),
            is_method   = is_method,
            class_name  = class_name,
        ))

    # Class methods first (prioritise Solution class)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if not item.name.startswith("__"):
                        _extract(item, is_method=True, class_name=node.name)

    # Top-level functions
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("__"):
                _extract(node, is_method=False, class_name="")

    # Sort: Solution class methods with params come first
    sigs.sort(key=lambda s: (
        0 if (s.is_method and s.class_name.lower() == "solution" and s.params) else 1
    ))
    return sigs


def is_leetcode_style(source: str) -> bool:
    """
    Returns True if code looks like a LeetCode submission:
    - Has a class named Solution / solution, OR
    - Has functions but no top-level executable calls / main guard
    """
    if not source.strip():
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    # Explicit Solution class → always LeetCode style
    has_solution_class = any(
        isinstance(n, ast.ClassDef) and n.name.lower() == "solution"
        for n in ast.walk(tree)
    )
    if has_solution_class:
        return True

    # Otherwise: has functions but no runnable top-level expressions
    has_functions = any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree))
    has_main_guard = any(
        isinstance(n, ast.If)
        and isinstance(getattr(n, "test", None), ast.Compare)
        for n in ast.walk(tree)
    )
    has_top_calls = any(
        isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
        for n in tree.body
    )
    return has_functions and not has_main_guard and not has_top_calls


# ── Input Parsing ─────────────────────────────────────────────

_EVAL_GLOBALS = {
    "__builtins__": {},
    "true": True, "false": False, "null": None,   # JSON aliases
    "True": True, "False": False, "None": None,
}


def parse_param_value(raw: str, hint: str = "") -> tuple[Any, str | None]:
    """
    Safely evaluate a user-supplied string into a Python value.
    Returns (value, error_string_or_None).

    Supports: int, float, bool, str, list, dict, tuple, nested structures.
    """
    raw = raw.strip()
    if not raw:
        return None, "Empty input"

    # Try safe ast.literal_eval first
    try:
        return ast.literal_eval(raw), None
    except (ValueError, SyntaxError):
        pass

    # Allow bare words → treat as string
    if re.fullmatch(r"[A-Za-z_]\w*", raw):
        return raw, None

    # JSON-style booleans / null
    low = raw.lower()
    if low == "true":  return True, None
    if low == "false": return False, None
    if low == "null":  return None, None

    return None, f"Cannot parse: {raw!r}"


# ── Code Injection ────────────────────────────────────────────

def inject_test_call(
    source: str,
    sig: FunctionSignature,
    param_values: dict[str, Any],
) -> str:
    """
    Append a test call at the bottom of `source`.

    For a class method:
        sol = Solution()
        result = sol.twoSum(nums=[...], target=...)
        print("Result:", result)

    For a plain function:
        result = twoSum(nums=[...], target=...)
        print("Result:", result)
    """
    lines = ["\n\n# ── TraceX injected test ────────────────────"]

    call_args = ", ".join(
        f"{p}={repr(param_values[p])}" for p in sig.params if p in param_values
    )

    if sig.is_method:
        lines.append(f"_sol = {sig.class_name}()")
        lines.append(f"_result = _sol.{sig.name}({call_args})")
    else:
        lines.append(f"_result = {sig.name}({call_args})")

    lines.append('print("\\n📦 Input:", ' + repr(param_values) + ")")
    lines.append('print("✅ Result:", _result)')

    return source + "\n".join(lines)


def build_injected_source(
    source: str,
    sig: FunctionSignature,
    raw_inputs: dict[str, str],   # param_name → user-typed string
) -> tuple[str, dict[str, Any], list[str]]:
    """
    Parse all raw inputs and build the injected source.

    Returns:
        injected_source : str   — source + test call
        parsed_values   : dict  — {param: parsed_value}
        errors          : list  — validation error messages
    """
    parsed, errors = {}, []
    for param in sig.params:
        raw = raw_inputs.get(param, "").strip()
        hint = sig.type_hints.get(param, "")
        val, err = parse_param_value(raw, hint)
        if err:
            errors.append(f"  • `{param}`: {err}")
        else:
            parsed[param] = val

    if errors:
        return source, parsed, errors

    injected = inject_test_call(source, sig, parsed)
    return injected, parsed, []
