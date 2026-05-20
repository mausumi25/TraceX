"""
TraceX — Python Execution Tracer
Captures every execution step using sys.settrace.
"""

import sys
import io
import traceback


_SKIP_NAMES = frozenset({
    "__name__", "__doc__", "__package__", "__loader__",
    "__spec__", "__builtins__", "__file__", "__cached__"
})


def _clean_vars(local_vars: dict) -> dict:
    result = {}
    for k, v in local_vars.items():
        if k.startswith("__") or k in _SKIP_NAMES:
            continue
        if isinstance(v, (type, type(sys), type(lambda: None))):
            continue
        try:
            r = repr(v)
            result[k] = r if len(r) <= 80 else r[:77] + "..."
        except Exception:
            result[k] = "<unprintable>"
    return result


def trace_python_code(source: str, max_steps: int = 300):
    """
    Execute source code and record every line-level step.

    Returns (steps, error_string_or_None)
    Each step dict has: step, line_no, line_text, variables,
                        call_stack, stdout, event, note
    """
    source_lines = source.splitlines()
    steps = []
    stdout_buf = io.StringIO()
    error_msg = None
    count = [0]

    def tracer(frame, event, arg):
        if count[0] >= max_steps:
            return None
        if event not in ("line", "call", "return", "exception"):
            return tracer

        fname = frame.f_code.co_filename
        # Skip stdlib / internal frames
        if fname not in ("<string>",) and not fname.endswith("tracer.py"):
            return tracer if event == "call" else None

        ln = frame.f_lineno
        line_text = (
            source_lines[ln - 1].rstrip()
            if 0 < ln <= len(source_lines) else ""
        )

        # Build call stack
        call_stack, f = [], frame
        while f:
            fn = f.f_code.co_filename
            name = f.f_code.co_name
            if fn == "<string>" and name not in ("tracer", "<module>"):
                call_stack.append({"name": name, "line": f.f_lineno})
            f = f.f_back
        call_stack.reverse()

        # Note
        if event == "call":
            note = f"↪ Calling  {frame.f_code.co_name}()"
        elif event == "return":
            note = f"↩ Returning from {frame.f_code.co_name}()  →  {repr(arg)[:50]}"
        elif event == "exception":
            et, ev, _ = arg
            note = f"💥 {et.__name__}: {ev}"
        else:
            note = f"▶ Line {ln}"

        count[0] += 1
        steps.append({
            "step":       count[0],
            "line_no":    ln,
            "line_text":  line_text,
            "variables":  _clean_vars(dict(frame.f_locals)),
            "call_stack": call_stack,
            "stdout":     stdout_buf.getvalue(),
            "event":      event,
            "note":       note,
        })
        return tracer

    old_stdout = sys.stdout
    sys.stdout = stdout_buf
    try:
        sys.settrace(tracer)
        exec(compile(source, "<string>", "exec"), {})  # noqa: S102
    except SystemExit:
        pass
    except Exception:
        error_msg = traceback.format_exc()
        steps.append({
            "step":       count[0] + 1,
            "line_no":    -1,
            "line_text":  "",
            "variables":  {},
            "call_stack": [],
            "stdout":     stdout_buf.getvalue(),
            "event":      "exception",
            "note":       "💥 Runtime Error",
        })
    finally:
        sys.settrace(None)
        sys.stdout = old_stdout

    # Patch final stdout into each step
    final = stdout_buf.getvalue()
    for i, s in enumerate(steps):
        if not s["stdout"] and i == len(steps) - 1:
            s["stdout"] = final

    return steps, error_msg
