"""
TraceX — Execution Timeline Generator
======================================
Central data model for the entire animation pipeline.

Produces a chronological list of typed events from Python code execution.
Every executed line, variable mutation, loop iteration, condition check,
function call/return, array/matrix operation, and output becomes an event.

Event types
-----------
line_execute       Every source line that runs
variable_set       First assignment of a variable
variable_change    Variable value mutated (primitive / dict / set)
array_update       arr[i] element changed
array_append       arr.append() / arr grew
array_pop          arr.pop() / arr shrank
matrix_cell_update dp[r][c] changed
loop_start         Entering a for/while loop
loop_iteration     Subsequent pass of a loop
loop_end           Loop finished (StopIteration / condition False)
condition_check    if / while condition evaluated → True/False
function_call      Function entered
function_return    Function returned
output             print() / stdout line emitted
final_output       Last event — program result

Timeline format
---------------
{
  "timeline": [ {event}, ... ],
  "stdout": "...",
  "error": null | "..."
}
"""

from __future__ import annotations

import ast
import copy
import io
import json
import sys
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import Any

# ── Event type constants ──────────────────────────────────────
EV_LINE          = "line_execute"
EV_VAR_SET       = "variable_set"
EV_VAR_CHANGE    = "variable_change"
EV_ARR_UPDATE    = "array_update"
EV_ARR_APPEND    = "array_append"
EV_ARR_POP       = "array_pop"
EV_MATRIX_UPDATE = "matrix_cell_update"
EV_LOOP_START    = "loop_start"
EV_LOOP_ITER     = "loop_iteration"
EV_LOOP_END      = "loop_end"
EV_COND          = "condition_check"
EV_FUNC_CALL     = "function_call"
EV_FUNC_RETURN   = "function_return"
EV_OUTPUT        = "output"
EV_FINAL         = "final_output"

MAX_EVENTS       = 3000
_SENTINEL        = object()

# Variables to always skip
_SKIP = frozenset({
    "_", "__builtins__", "__name__", "__doc__", "__package__",
    "__loader__", "__spec__", "__file__", "__cached__",
    "tracex_input",
})


# ─────────────────────────────────────────────────────────────
class TimelineGenerator:
    """
    Execute Python source and produce a structured event timeline.

    Usage
    -----
    gen    = TimelineGenerator(source)
    result = gen.generate(user_input="9")
    # result == {"timeline": [...], "stdout": "...", "error": None}
    """

    def __init__(self, source: str, max_events: int = MAX_EVENTS):
        self.source     = textwrap.dedent(source)
        self.max_events = max_events
        self.timeline   : list[dict] = []
        self._seq       = 0

        # AST map: lineno → node metadata
        self._line_info : dict[int, dict] = {}
        self._func_end  : dict[str, int]  = {}   # func name → end line

        # State for diffing
        self._prev_locals   : dict[str, Any]  = {}
        self._arr_snaps     : dict[str, list]  = {}  # list snapshots
        self._dict_snaps    : dict[str, dict]  = {}  # dict snapshots

        # Loop tracking: for_line → {iteration, var, iter_src, end_ln}
        self._loop_state  : dict[int, dict]  = {}
        self._loop_stack  : list[int]        = []   # for-line numbers

        # Call stack mirror
        self._call_stack  : list[dict]       = []

        # Stdout
        self._stdout_buf  = io.StringIO()
        self._stdout_prev = ""

        self._parse_ast()

    # ── AST Pre-Analysis ─────────────────────────────────────

    def _parse_ast(self):
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            ln = getattr(node, "lineno", None)
            if ln is None:
                continue

            if isinstance(node, ast.For):
                self._line_info[ln] = {
                    "type"     : "for_loop",
                    "var"      : ast.unparse(node.target),
                    "iter_src" : ast.unparse(node.iter),
                    "end_ln"   : getattr(node, "end_lineno", ln),
                }
            elif isinstance(node, ast.While):
                if ln not in self._line_info:
                    self._line_info[ln] = {
                        "type"    : "while_loop",
                        "test_src": ast.unparse(node.test),
                        "end_ln"  : getattr(node, "end_lineno", ln),
                    }
            elif isinstance(node, ast.If):
                if ln not in self._line_info:
                    self._line_info[ln] = {
                        "type"    : "condition",
                        "test_src": ast.unparse(node.test),
                    }
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._line_info[ln] = {
                    "type"   : "function_def",
                    "name"   : node.name,
                    "end_ln" : getattr(node, "end_lineno", ln),
                }
                self._func_end[node.name] = getattr(node, "end_lineno", ln)
            elif isinstance(node, ast.Return):
                if ln not in self._line_info:
                    self._line_info[ln] = {
                        "type"     : "return",
                        "value_src": ast.unparse(node.value) if node.value else "None",
                    }

    # ── Event emission ────────────────────────────────────────

    def _emit(self, ev: dict) -> None:
        if self._seq >= self.max_events:
            return
        ev["seq"] = self._seq
        self.timeline.append(ev)
        self._seq += 1

    # ── Repr helpers ──────────────────────────────────────────

    @staticmethod
    def _repr(val: Any, limit: int = 80) -> str:
        try:
            s = repr(val)
            return s if len(s) <= limit else s[:limit] + "…"
        except Exception:
            return "<unrepresentable>"

    @staticmethod
    def _skip(name: str) -> bool:
        return name in _SKIP or name.startswith("__")

    # ── Snapshot helpers ──────────────────────────────────────

    def _snap_list(self, val: list) -> list:
        """Shallow copy preserving 2D structure."""
        try:
            return [list(r) if isinstance(r, list) else r for r in val]
        except Exception:
            return list(val)

    def _snap_dict(self, val: dict) -> dict:
        try:
            return {k: v for k, v in val.items()}
        except Exception:
            return {}

    # ── Array / Matrix diff ───────────────────────────────────

    def _diff_list(self, name: str, old: list, new: list) -> None:
        """Emit granular events for list mutations."""
        # Detect 2D (matrix / DP table)
        is_2d = bool(old) and isinstance(old[0], list)
        if not is_2d and bool(new) and isinstance(new[0], list):
            is_2d = True

        if is_2d:
            for r in range(min(len(old), len(new))):
                old_r = old[r] if r < len(old) else []
                new_r = new[r] if r < len(new) else []
                if isinstance(old_r, list) and isinstance(new_r, list):
                    for c in range(min(len(old_r), len(new_r))):
                        ov = old_r[c] if c < len(old_r) else None
                        nv = new_r[c] if c < len(new_r) else None
                        if ov != nv:
                            self._emit({
                                "event"    : EV_MATRIX_UPDATE,
                                "var"      : name,
                                "row"      : r,
                                "col"      : c,
                                "old_value": self._repr(ov),
                                "new_value": self._repr(nv),
                            })
            return

        # 1-D array: element changes
        for i in range(min(len(old), len(new))):
            ov, nv = old[i], new[i]
            if ov != nv:
                self._emit({
                    "event"    : EV_ARR_UPDATE,
                    "var"      : name,
                    "index"    : i,
                    "old_value": self._repr(ov),
                    "new_value": self._repr(nv),
                })

        # Appended elements
        if len(new) > len(old):
            for i in range(len(old), len(new)):
                self._emit({
                    "event"  : EV_ARR_APPEND,
                    "var"    : name,
                    "index"  : i,
                    "value"  : self._repr(new[i]),
                    "new_len": len(new),
                })

        # Popped elements
        elif len(new) < len(old):
            self._emit({
                "event"   : EV_ARR_POP,
                "var"     : name,
                "old_len" : len(old),
                "new_len" : len(new),
                "removed" : self._repr(old[len(new):]),
            })

    # ── Variable diff engine ──────────────────────────────────

    def _diff_scope(self, old: dict, new: dict) -> None:
        """Compare two local-scope snapshots and emit typed events."""
        for name, new_val in new.items():
            if self._skip(name):
                continue
            old_val = old.get(name, _SENTINEL)

            # ── Brand new variable ─────────────────────────────
            if old_val is _SENTINEL:
                self._emit({
                    "event": EV_VAR_SET,
                    "name" : name,
                    "value": self._repr(new_val),
                    "type" : type(new_val).__name__,
                })
                # Snapshot mutable structures
                if isinstance(new_val, list):
                    self._arr_snaps[name] = self._snap_list(new_val)
                elif isinstance(new_val, dict):
                    self._dict_snaps[name] = self._snap_dict(new_val)
                continue

            # ── List mutations ─────────────────────────────────
            if isinstance(new_val, list):
                old_snap = self._arr_snaps.get(name)
                if old_snap is None:
                    old_snap = self._snap_list(old_val) if isinstance(old_val, list) else []
                new_snap = self._snap_list(new_val)
                if old_snap != new_snap:
                    self._diff_list(name, old_snap, new_snap)
                    self._arr_snaps[name] = new_snap
                continue

            # ── Dict mutations ─────────────────────────────────
            if isinstance(new_val, dict):
                old_snap = self._dict_snaps.get(name, {})
                new_snap = self._snap_dict(new_val)
                for k, v in new_snap.items():
                    if k not in old_snap:
                        self._emit({
                            "event"    : EV_VAR_CHANGE,
                            "name"     : f"{name}[{self._repr(k)}]",
                            "old_value": "<absent>",
                            "new_value": self._repr(v),
                            "type"     : "dict_insert",
                        })
                    elif old_snap[k] != v:
                        self._emit({
                            "event"    : EV_VAR_CHANGE,
                            "name"     : f"{name}[{self._repr(k)}]",
                            "old_value": self._repr(old_snap[k]),
                            "new_value": self._repr(v),
                            "type"     : "dict_update",
                        })
                self._dict_snaps[name] = new_snap
                continue

            # ── Primitive / other value change ─────────────────
            try:
                changed = (new_val != old_val)
                if isinstance(changed, bool) and changed:
                    self._emit({
                        "event"    : EV_VAR_CHANGE,
                        "name"     : name,
                        "old_value": self._repr(old_val),
                        "new_value": self._repr(new_val),
                        "type"     : type(new_val).__name__,
                    })
            except Exception:
                pass

    # ── stdout monitor ────────────────────────────────────────

    def _flush_stdout(self) -> None:
        current = self._stdout_buf.getvalue()
        if current == self._stdout_prev:
            return
        new_text = current[len(self._stdout_prev):]
        for line in new_text.split("\n"):
            if line:
                self._emit({
                    "event": EV_OUTPUT,
                    "text" : line,
                })
        self._stdout_prev = current

    # ── sys.settrace callback ─────────────────────────────────

    def _trace(self, frame, event_type: str, arg: Any):
        if self._seq >= self.max_events:
            sys.settrace(None)
            return None

        if frame.f_code.co_filename != "<tracex>":
            # Allow tracing into called functions compiled under <tracex>
            return self._trace

        ln        = frame.f_lineno
        func_name = frame.f_code.co_name
        lo        = frame.f_locals
        gl        = frame.f_globals

        src_lines = self.source.splitlines()
        line_text = src_lines[ln - 1].rstrip() if 0 < ln <= len(src_lines) else ""
        info      = self._line_info.get(ln, {})

        # ── CALL ─────────────────────────────────────────────
        if event_type == "call":
            args = {}
            try:
                code = frame.f_code
                for aname in code.co_varnames[:code.co_argcount]:
                    if aname in lo and not self._skip(aname):
                        args[aname] = self._repr(lo[aname])
            except Exception:
                pass

            self._call_stack.append({"name": func_name, "line": ln, "args": args})
            self._emit({
                "event"    : EV_FUNC_CALL,
                "function" : func_name,
                "arguments": args,
                "line"     : ln,
                "code"     : line_text.strip(),
            })
            # Fresh scope — reset diff baseline
            self._prev_locals = {}
            return self._trace

        # ── RETURN ───────────────────────────────────────────
        if event_type == "return":
            self._flush_stdout()

            ret_repr = self._repr(arg)
            if self._call_stack:
                self._call_stack.pop()

            self._emit({
                "event"   : EV_FUNC_RETURN,
                "function": func_name,
                "value"   : ret_repr,
                "line"    : ln,
            })
            self._prev_locals = {}
            return self._trace

        # ── EXCEPTION ────────────────────────────────────────
        if event_type == "exception":
            return self._trace

        # ── LINE ─────────────────────────────────────────────
        if event_type != "line":
            return self._trace

        # 1. Emit line_execute first
        self._emit({
            "event"   : EV_LINE,
            "line"    : ln,
            "code"    : line_text.strip(),
            "function": func_name,
        })

        # 2. Loop detection
        node_type = info.get("type", "")
        if node_type == "for_loop":
            if ln not in self._loop_state:
                # First encounter → loop_start
                self._loop_state[ln] = {
                    "iteration": 0,
                    "var"      : info["var"],
                    "iter_src" : info["iter_src"],
                    "end_ln"   : info.get("end_ln", ln),
                }
                self._loop_stack.append(ln)
                self._emit({
                    "event"    : EV_LOOP_START,
                    "line"     : ln,
                    "loop_type": "for",
                    "loop_var" : info["var"],
                    "iterable" : info["iter_src"],
                })
            else:
                # Subsequent → loop_iteration
                state = self._loop_state[ln]
                state["iteration"] += 1
                loop_var_val = lo.get(info["var"])
                self._emit({
                    "event"    : EV_LOOP_ITER,
                    "line"     : ln,
                    "loop_type": "for",
                    "iteration": state["iteration"],
                    "loop_var" : info["var"],
                    "value"    : self._repr(loop_var_val),
                })

        elif node_type == "while_loop":
            if ln not in self._loop_state:
                self._loop_state[ln] = {
                    "iteration": 0,
                    "test_src" : info["test_src"],
                    "end_ln"   : info.get("end_ln", ln),
                }
                self._loop_stack.append(ln)

            # Always evaluate while condition
            try:
                result = bool(eval(info["test_src"], gl, lo))
            except Exception:
                result = None

            state = self._loop_state[ln]
            if state["iteration"] == 0:
                self._emit({
                    "event"     : EV_LOOP_START,
                    "line"      : ln,
                    "loop_type" : "while",
                    "condition" : info["test_src"],
                    "result"    : result,
                })
            else:
                self._emit({
                    "event"     : EV_LOOP_ITER,
                    "line"      : ln,
                    "loop_type" : "while",
                    "iteration" : state["iteration"],
                    "condition" : info["test_src"],
                    "result"    : result,
                })
            state["iteration"] += 1

        # 3. Condition check (if statement)
        elif node_type == "condition":
            test_src = info.get("test_src", "")
            try:
                result = bool(eval(test_src, gl, lo))
            except Exception:
                result = None
            self._emit({
                "event"     : EV_COND,
                "line"      : ln,
                "expression": test_src,
                "result"    : result,
            })

        # 4. Check if any active loop just ended
        #    (we've jumped past the loop's end_ln)
        ended = []
        for loop_ln in list(self._loop_stack):
            state = self._loop_state.get(loop_ln, {})
            end_ln = state.get("end_ln", loop_ln)
            if ln > end_ln or (ln < loop_ln):
                self._emit({
                    "event"      : EV_LOOP_END,
                    "line"       : loop_ln,
                    "iterations" : state.get("iteration", 0),
                    "loop_var"   : state.get("var", ""),
                })
                ended.append(loop_ln)
        for l in ended:
            self._loop_stack.remove(l)
            del self._loop_state[l]

        # 5. Variable diff — compare with previous scope snapshot
        new_lo = {k: v for k, v in lo.items() if not self._skip(k)}
        self._diff_scope(self._prev_locals, new_lo)
        self._prev_locals = new_lo

        # Refresh list snapshots for newly seen lists
        for name, val in new_lo.items():
            if isinstance(val, list) and name not in self._arr_snaps:
                self._arr_snaps[name] = self._snap_list(val)
            elif isinstance(val, dict) and name not in self._dict_snaps:
                self._dict_snaps[name] = self._snap_dict(val)

        # 6. Flush stdout
        self._flush_stdout()

        return self._trace

    # ── Public API ────────────────────────────────────────────

    def generate(self, user_input: str = "") -> dict:
        """
        Execute source, collect events, return:
        {
            "timeline": [ ...events... ],
            "stdout"  : "...",
            "error"   : null | "traceback string"
        }
        """
        error: str | None = None
        old_stdout = sys.stdout
        sys.stdout = self._stdout_buf

        try:
            code_obj = compile(self.source, "<tracex>", "exec")
            gl: dict = {
                "__name__"    : "__main__",
                "__builtins__": __builtins__,
            }
            if user_input.strip():
                _inp = iter(user_input.splitlines())
                gl["input"] = lambda _="": next(_inp, "")

            sys.settrace(self._trace)
            exec(code_obj, gl)          # noqa: S102

        except SystemExit:
            pass
        except Exception:
            error = traceback.format_exc()
        finally:
            sys.settrace(None)
            sys.stdout = old_stdout

        # Close any loops still on the stack
        for loop_ln in list(self._loop_stack):
            state = self._loop_state.get(loop_ln, {})
            self._emit({
                "event"      : EV_LOOP_END,
                "line"       : loop_ln,
                "iterations" : state.get("iteration", 0),
                "loop_var"   : state.get("var", ""),
            })

        # Flush remaining stdout
        self._flush_stdout()

        # Final output event — ALWAYS last
        final_stdout = self._stdout_buf.getvalue().strip()
        self._emit({
            "event" : EV_FINAL,
            "stdout": final_stdout,
            "error" : error,
        })

        return {
            "timeline": self.timeline,
            "stdout"  : final_stdout,
            "error"   : error,
        }


# ── Convenience functions ─────────────────────────────────────

def generate_timeline(
    source: str,
    user_input: str = "",
    max_events: int = MAX_EVENTS,
) -> dict:
    """
    Top-level function. Returns:
      {"timeline": [...], "stdout": "...", "error": None | str}
    """
    gen = TimelineGenerator(source, max_events=max_events)
    return gen.generate(user_input)


def timeline_to_json(result: dict, indent: int = 2) -> str:
    """Serialize generate_timeline() result to JSON string."""
    return json.dumps(result, indent=indent, default=str)


def save_timeline(result: dict, path: str) -> str:
    """Write timeline JSON to disk. Returns the path."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(timeline_to_json(result))
    return path


def timeline_summary(result: dict) -> dict:
    """
    Return a compact summary of event type counts.
    Useful for sidebar stats.
    """
    counts: dict[str, int] = {}
    for ev in result["timeline"]:
        t = ev.get("event", "?")
        counts[t] = counts.get(t, 0) + 1
    return counts
