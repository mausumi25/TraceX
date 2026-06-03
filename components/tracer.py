"""
TraceX — Enhanced Python Execution Tracer
Captures every execution step as a structured JSON timeline dict.

Each step records:
  line        : current line number
  line_text   : source text of that line
  event       : line | call | return | exception
  variables   : snapshot of local variables (cleaned)
  loops       : active loop variables + iteration count
  call_stack  : function call hierarchy
  stdout      : cumulative program output so far
  func_call   : { name, args } if event == 'call'
  return_val  : repr of return value if event == 'return'
  error       : error info if event == 'exception'
  note        : human-readable description
  step        : sequential index (1-based)
"""

import sys
import io
import json
import traceback
import ast
from components.data_structure_detector import detect_all, structures_to_json


# ── Skip internal / stdlib names ──────────────────────────────
_SKIP_NAMES = frozenset({
    "__name__", "__doc__", "__package__", "__loader__",
    "__spec__", "__builtins__", "__file__", "__cached__",
})

# ── Loop keyword detection ─────────────────────────────────────
_LOOP_KEYWORDS = ("for ", "while ")


def _is_loop_line(text: str) -> bool:
    stripped = text.strip()
    return any(stripped.startswith(kw) for kw in _LOOP_KEYWORDS)


def _clean_vars(local_vars: dict) -> dict:
    """Filter and repr all user-defined local variables."""
    result = {}
    for k, v in local_vars.items():
        if k.startswith("__") or k in _SKIP_NAMES:
            continue
        if callable(v) and not isinstance(v, (int, float, str, list, dict, tuple, set, bool)):
            continue
        if isinstance(v, type):
            continue
        if isinstance(v, type(sys)):
            continue
        try:
            r = repr(v)
            result[k] = r if len(r) <= 120 else r[:117] + "..."
        except Exception:
            result[k] = "<unprintable>"
    return result


def _detect_loops(frame, source_lines: list[str]) -> list[dict]:
    """
    Detect active loop variables by scanning local scope for
    variables that look like loop iterators (e.g. 'i', 'idx', etc.)
    Also check if the current line is a for/while line.
    """
    loops = []
    ln = frame.f_lineno
    if 0 < ln <= len(source_lines):
        text = source_lines[ln - 1].strip()
        if text.startswith("for "):
            # Extract loop variable name: "for VAR in ..."
            try:
                parts = text[4:].split(" in ")[0].strip()
                var_names = [v.strip() for v in parts.split(",")]
                for vn in var_names:
                    val = frame.f_locals.get(vn)
                    if val is not None:
                        loops.append({
                            "var": vn,
                            "value": repr(val)[:60],
                            "line": ln,
                        })
            except Exception:
                pass
    return loops


def _build_call_stack(frame, source_lines: list[str]) -> list[dict]:
    """Walk frame chain to build the call stack."""
    stack, f = [], frame
    while f:
        fn = f.f_code.co_filename
        name = f.f_code.co_name
        if fn == "<string>" and name not in ("tracer", "<module>"):
            args = {}
            try:
                # Capture function arguments
                code = f.f_code
                for argname in code.co_varnames[:code.co_argcount]:
                    if argname in f.f_locals:
                        args[argname] = repr(f.f_locals[argname])[:40]
            except Exception:
                pass
            stack.append({
                "name": name,
                "line": f.f_lineno,
                "args": args,
            })
        f = f.f_back
    stack.reverse()
    return stack


def trace_python_code(source: str, max_steps: int = 500):
    """
    Execute source code with sys.settrace and record every step.

    Returns
    -------
    steps : list[dict]
        Sequential timeline — each dict is one execution step.
    error : str | None
        Traceback string if a runtime error occurred.

    Step dict schema
    ----------------
    {
        "step"       : int,           # 1-based index
        "line"       : int,           # source line number
        "line_text"  : str,           # source text of that line
        "event"      : str,           # 'line' | 'call' | 'return' | 'exception'
        "variables"  : dict[str,str], # repr of all local vars
        "loops"      : list[dict],    # active loop variables
        "call_stack" : list[dict],    # function call hierarchy
        "stdout"     : str,           # cumulative program output
        "func_call"  : dict | None,   # {name, args} on 'call' events
        "return_val" : str | None,    # repr of return value
        "error"      : dict | None,   # {type, message} on exceptions
        "note"       : str,           # human-readable label
    }
    """
    source_lines = source.splitlines()
    steps: list[dict] = []
    stdout_buf = io.StringIO()
    error_msg: str | None = None
    count = [0]
    loop_counters: dict[int, int] = {}  # line_no → iteration count

    def tracer(frame, event, arg):
        if count[0] >= max_steps:
            return None
        if event not in ("line", "call", "return", "exception"):
            return tracer

        fname = frame.f_code.co_filename
        # Only trace user code (executed via exec)
        if fname != "<string>":
            return tracer if event == "call" else None

        ln        = frame.f_lineno
        line_text = (
            source_lines[ln - 1].rstrip()
            if 0 < ln <= len(source_lines) else ""
        )
        raw_locals = dict(frame.f_locals)
        variables  = _clean_vars(raw_locals)
        call_stack = _build_call_stack(frame, source_lines)
        loops      = _detect_loops(frame, source_lines)

        # ── Data structure detection on raw objects ───────────
        try:
            struct_infos = detect_all(raw_locals)
            structures   = structures_to_json(struct_infos)
        except Exception:
            structures = []

        # Track loop iteration counts
        if _is_loop_line(line_text):
            loop_counters[ln] = loop_counters.get(ln, 0) + 1
            for lp in loops:
                lp["iteration"] = loop_counters[ln]

        # Event-specific fields
        func_call  = None
        return_val = None
        error_info = None

        if event == "call":
            # Capture function arguments
            try:
                code = frame.f_code
                call_args = {}
                for argname in code.co_varnames[:code.co_argcount]:
                    if argname in frame.f_locals and argname != "self":
                        call_args[argname] = repr(frame.f_locals[argname])[:60]
                func_call = {"name": frame.f_code.co_name, "args": call_args}
            except Exception:
                func_call = {"name": frame.f_code.co_name, "args": {}}
            note = f"Call: {frame.f_code.co_name}({', '.join(f'{k}={v}' for k,v in func_call['args'].items())})"

        elif event == "return":
            return_val = repr(arg)[:80] if arg is not None else "None"
            note = f"Return: {frame.f_code.co_name}() -> {return_val}"

        elif event == "exception":
            et, ev, _ = arg
            error_info = {"type": et.__name__, "message": str(ev)[:120]}
            note = f"Exception: {et.__name__}: {ev}"

        else:  # line
            if loops:
                lp = loops[0]
                note = f"Line {ln} | loop {lp['var']}={lp['value']}"
            else:
                note = f"Line {ln}: {line_text.strip()[:60]}"

        count[0] += 1
        steps.append({
            "step":       count[0],
            "line":       ln,
            "line_no":    ln,
            "line_text":  line_text,
            "event":      event,
            "variables":  variables,
            "structures": structures,
            "loops":      loops,
            "call_stack": call_stack,
            "stdout":     stdout_buf.getvalue(),
            "func_call":  func_call,
            "return_val": return_val,
            "error":      error_info,
            "note":       note,
        })
        return tracer

    # ── Execute ───────────────────────────────────────────────
    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        sys.settrace(tracer)
        exec(compile(source, "<string>", "exec"), {})   # noqa: S102
    except SystemExit:
        pass
    except Exception:
        error_msg = traceback.format_exc()
        steps.append({
            "step":       count[0] + 1,
            "line":       -1,
            "line_no":    -1,
            "line_text":  "",
            "event":      "exception",
            "variables":  {},
            "loops":      [],
            "call_stack": [],
            "stdout":     stdout_buf.getvalue(),
            "func_call":  None,
            "return_val": None,
            "error":      {"type": "RuntimeError", "message": error_msg},
            "note":       "Runtime Error",
        })
    finally:
        sys.settrace(None)
        sys.stdout = old_stdout

    # Patch final stdout into all steps
    final_stdout = stdout_buf.getvalue()
    for s in steps:
        if not s["stdout"]:
            s["stdout"] = final_stdout

    return steps, error_msg


def steps_to_json(steps: list[dict], indent: int = 2) -> str:
    """Serialize the execution timeline to a JSON string."""
    return json.dumps(steps, indent=indent, default=str)


def save_timeline(steps: list[dict], path: str) -> str:
    """Save the execution timeline to a JSON file. Returns the path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(steps_to_json(steps))
    return path
