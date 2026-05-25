"""
GDB trace script — executed inside `gdb --batch -x gdb_trace.py ./program`

Produces a JSON array on stdout where each element is one execution step:
  { step, line, event, variables, call_stack, loops, stdout, note, ... }

This file is NOT imported by Python directly — it is passed as -x script to GDB.
"""
import gdb
import json
import io
import sys

MAX_STEPS = 500

# ---------- stdout capture via inferior I/O ----------
_captured_stdout = []

class OutputCapture(gdb.InferiorOutputFilter):
    def filter(self, string):
        _captured_stdout.append(string)
        return string           # still echo to GDB console

try:
    _cap = OutputCapture()
except Exception:
    _cap = None


def _get_vars(frame):
    """Collect local variables and arguments from the current frame."""
    result = {}
    try:
        block = frame.block()
        while block:
            for sym in block:
                if sym.is_variable or sym.is_argument:
                    if sym.name in result:
                        continue
                    try:
                        val = frame.read_var(sym, block)
                        result[sym.name] = val.format_string(
                            raw=False, max_elements=8
                        )
                    except Exception:
                        pass
            if block.is_static or block.is_global:
                break
            block = block.superblock
    except Exception:
        pass
    return result


def _get_callstack(frame):
    stack = []
    f = frame
    depth = 0
    while f and depth < 8:
        try:
            sal  = f.find_sal()
            name = str(f.name() or "??")
            line = sal.line if sal and sal.symtab else -1
            stack.append({"name": name, "line": line, "args": {}})
        except Exception:
            break
        try:
            f = f.older()
        except Exception:
            break
        depth += 1
    return stack


def _make_step(n, line, event, variables, call_stack, stdout_so_far, note):
    return {
        "step":       n,
        "line":       line,
        "line_no":    line,
        "line_text":  "",
        "event":      event,
        "variables":  variables,
        "loops":      [],
        "call_stack": call_stack,
        "stdout":     stdout_so_far,
        "func_call":  None,
        "return_val": None,
        "error":      None,
        "note":       note,
        "phase":      "run",
    }


# ---------- Main trace loop ----------
gdb.execute("set pagination off")
gdb.execute("set print pretty off")
gdb.execute("set print elements 8")
gdb.execute("set width 0")
gdb.execute("set confirm off")

# Break at the start of main and run
gdb.execute("break main", to_string=True)
gdb.execute("run", to_string=True)

steps = []
stdout_so_far = ""

for i in range(MAX_STEPS):
    try:
        frame = gdb.selected_frame()
    except gdb.error:
        break

    sal = frame.find_sal()
    if not sal or not sal.symtab:
        try:
            gdb.execute("next", to_string=True)
        except gdb.error:
            break
        continue

    line = sal.line
    variables  = _get_vars(frame)
    call_stack = _get_callstack(frame)

    # Accumulate captured stdout
    if _cap is not None:
        stdout_so_far = "".join(_captured_stdout)

    steps.append(_make_step(
        n=i + 1,
        line=line,
        event="line",
        variables=variables,
        call_stack=call_stack,
        stdout_so_far=stdout_so_far,
        note=f"Line {line}",
    ))

    # Step to the next source line
    try:
        out = gdb.execute("next", to_string=True)
        if "exited" in out or "terminated" in out or "Program received signal" in out:
            break
    except gdb.error as e:
        err_msg = str(e)
        if steps:
            steps[-1]["error"] = err_msg
        break

# Final accumulated stdout
if _cap is not None:
    stdout_so_far = "".join(_captured_stdout)
if steps:
    steps[-1]["stdout"] = stdout_so_far

# Print JSON to stdout (GDB will include it in subprocess stdout capture)
gdb.write("TRACEX_JSON_BEGIN\n")
gdb.write(json.dumps(steps))
gdb.write("\nTRACEX_JSON_END\n")
gdb.execute("quit")
