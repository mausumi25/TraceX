"""
TraceX GDB Tracer — uses GDB --batch -ex commands (GDB 7.x compatible)

Generates a line-by-line execution timeline for C++ code.
"""

import subprocess
import os
import re
import time


_MAX_STEPS = 300


def _build_gdb_script(max_steps: int, tmp_script_path: str) -> None:
    """Write a GDB command script to a file (avoids -ex argument length limits)."""
    lines = [
        "set pagination off",
        "set print pretty off",
        "set print elements 8",
        "set width 0",
        "set confirm off",
        "break main",
        "run",
    ]
    for i in range(min(max_steps, 250)):
        lines += [
            f"echo STEP_BEGIN_{i}\\n",
            "info line",
            "info locals",
            "backtrace 4",
            f"echo STEP_END_{i}\\n",
            "next",
        ]
    lines += ["echo TRACEX_DONE\\n", "quit"]

    with open(tmp_script_path, "w") as f:
        f.write("\n".join(lines))


def _clean_var_value(raw: str) -> str:
    """Simplify GDB variable output to a human-readable form."""
    # vector<int>: extract the actual elements from _M_start / raw memory
    # For simple scalars just return the value
    raw = raw.strip()

    # vector pattern: try to extract {1, 2, 3} style
    if "std::" in raw or "_M_impl" in raw:
        # Try to find {number, number, ...} pattern
        nums = re.findall(r'\b-?\d+\b', raw)
        # Filter out large memory addresses (>9999) and GDB internals
        nums = [n for n in nums if abs(int(n)) <= 99999]
        if nums:
            return "{" + ", ".join(nums[:8]) + "}"
        return "<vector>"

    # string pattern
    if raw.startswith('"') or 'static const char' in raw:
        m = re.search(r'"([^"]*)"', raw)
        return f'"{m.group(1)}"' if m else raw

    # Boolean
    if raw in ("true", "false"):
        return raw

    # Simple int/float
    if re.match(r'^-?\d+(\.\d+)?$', raw):
        return raw

    # Truncate long complex values
    if len(raw) > 30:
        return raw[:30] + "..."

    return raw


def _parse_gdb_output(raw: str, source_lines: list[str]) -> list[dict]:
    """Parse raw GDB batch output into a list of execution step dicts."""
    steps  = []
    step_n = 0

    # Split on STEP_BEGIN markers
    # Each chunk: STEP_BEGIN_N\n<info line output>\n<info locals output>\n<backtrace output>\nSTEP_END_N
    chunks = re.split(r"STEP_BEGIN_\d+\n?", raw)

    for chunk in chunks[1:]:  # skip everything before first STEP_BEGIN
        if "TRACEX_DONE" in chunk:
            break
        if re.search(r"(exited|terminated|Program received signal SIGSEGV)", chunk):
            break

        # ── Line number ──────────────────────────────────────
        line_no = -1
        line_m = re.search(r"Line (\d+) of", chunk)
        if line_m:
            line_no = int(line_m.group(1))

        if line_no < 1:
            continue

        # ── Local variables (everything between info line and backtrace) ──
        variables = {}
        # The locals block is between end of "Line X of..." and "#0  func"
        # Find the start of backtrace output
        bt_start = chunk.find("#0 ")
        if bt_start == -1:
            bt_start = chunk.find("STEP_END")

        # Find end of "info line" output (first blank-ish line after "Line X of...")
        line_info_end = chunk.find("\n", chunk.find("Line ") + 5) if "Line " in chunk else 0
        locals_text = chunk[line_info_end:bt_start] if bt_start > line_info_end else ""

        for vline in locals_text.strip().splitlines():
            vline = vline.strip()
            if not vline or vline.startswith("#") or vline.startswith("(gdb)"):
                continue
            # Match:  varname = value
            m = re.match(r"^(\w+)\s*=\s*(.+)$", vline)
            if m:
                name = m.group(1)
                val  = _clean_var_value(m.group(2))
                variables[name] = val

        # Remove uninitialized / garbage values for common junk patterns
        variables = {k: v for k, v in variables.items()
                     if v not in ("<No data fields>", "", "<vector>")
                     and not k.startswith("__")
                     and not k.startswith("_M_")}

        # ── Call stack ───────────────────────────────────────
        call_stack = []
        for frame_m in re.finditer(r"#(\d+)\s+(?:0x\w+\s+in\s+)?(\w+)\s*\(", chunk):
            call_stack.append({
                "name": frame_m.group(2),
                "line": line_no,
                "args": {}
            })
        if not call_stack:
            call_stack = [{"name": "main", "line": line_no, "args": {}}]

        # ── Source line text ─────────────────────────────────
        line_text = ""
        if 0 < line_no <= len(source_lines):
            line_text = source_lines[line_no - 1].strip()

        # ── Loop detection ───────────────────────────────────
        loops = []
        for lv in ["i", "j", "k", "n", "idx"]:
            if lv in variables:
                try:
                    loops.append({
                        "var":       lv,
                        "value":     variables[lv],
                        "iteration": step_n,
                        "line":      line_no,
                    })
                except Exception:
                    pass

        step_n += 1
        steps.append({
            "step":       step_n,
            "line":       line_no,
            "line_no":    line_no,
            "line_text":  line_text,
            "event":      "line",
            "variables":  variables,
            "loops":      loops,
            "call_stack": call_stack,
            "stdout":     "",
            "func_call":  None,
            "return_val": None,
            "error":      None,
            "note":       f"Line {line_no}" + (f"  {line_text[:45]}" if line_text else ""),
            "phase":      "run",
        })

    return steps


def trace_cpp_with_gdb(
    source: str,
    exe_path: str,
    stdin: str = "",
    max_steps: int = _MAX_STEPS,
) -> list[dict]:
    """
    Run exe_path under GDB using a batch script.
    Returns timeline list, or [] on failure.
    """
    import tempfile
    source_lines = source.splitlines()

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "trace.gdb")
        _build_gdb_script(max_steps, script_path)

        try:
            proc = subprocess.run(
                ["gdb", "--batch", "-x", script_path, exe_path],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=60,
            )
            raw = proc.stdout + proc.stderr
            steps = _parse_gdb_output(raw, source_lines)
            return [s for s in steps if s["line"] > 0]

        except subprocess.TimeoutExpired:
            return []
        except FileNotFoundError:
            return []
        except Exception:
            return []
