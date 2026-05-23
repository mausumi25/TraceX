"""
TraceX — Multi-Language Runtime Executor
Runs C, C++, and Java code via subprocess and produces
a structured execution timeline (compile + run steps).

For Python — use tracer.py (sys.settrace gives line-by-line tracing).
For C/C++/Java — we compile then execute, capturing stdout/stderr,
and generate a simplified but informative execution timeline.
"""

import os
import subprocess
import tempfile
import json
import time
from dataclasses import dataclass, field


@dataclass
class ExecutionResult:
    language:    str
    stdout:      str
    stderr:      str
    return_code: int
    compile_ok:  bool
    compile_err: str
    exec_time_ms: float
    timeline:    list[dict] = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10, stdin: str = "") -> tuple[str, str, int, float]:
    """Run a subprocess. Returns (stdout, stderr, returncode, elapsed_ms)."""
    t0 = time.perf_counter()
    try:
        r = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - t0) * 1000
        return r.stdout, r.stderr, r.returncode, elapsed
    except subprocess.TimeoutExpired:
        return "", "Execution timed out (10s limit)", -1, timeout * 1000
    except FileNotFoundError as e:
        return "", f"Compiler/runtime not found: {e}", -1, 0.0


# ── LeetCode normalisers ───────────────────────────────────────

def _has_main(source: str) -> bool:
    """Return True if the source already contains a main() entry point."""
    import re
    return bool(re.search(r'\bmain\s*\(', source))


def _normalize_cpp_leetcode(source: str) -> str:
    """
    If the C++ source is LeetCode-style (class Solution, no main),
    inject the standard headers and a main() that calls twoSum-style method.
    Supports: twoSum, maxProfit, longestCommonPrefix, and generic void/int methods.
    """
    import re
    if _has_main(source):
        return source

    # Detect method signature inside Solution
    # Pattern: returnType methodName(params)
    method_pat = re.search(
        r'(?:public\s+)?'
        r'(vector\s*<[^>]+>|string|int|bool|double|float|long|void)\s+'
        r'(\w+)\s*\(([^)]*)\)',
        source
    )

    headers = """\
#include <bits/stdc++.h>
using namespace std;
"""
    # Build a minimal main based on detected method
    main_block = ""
    if method_pat:
        ret_type  = method_pat.group(1).strip()
        func_name = method_pat.group(2).strip()
        params    = method_pat.group(3).strip()

        # Build argument list with sample values
        args = []
        for param in params.split(','):
            param = param.strip()
            if not param:
                continue
            if 'vector<int>' in param:
                args.append('nums')
            elif 'vector<string>' in param:
                args.append('strs')
            elif 'string' in param:
                args.append('s')
            elif 'int' in param:
                args.append('target')
            elif 'double' in param or 'float' in param:
                args.append('0.0')
            else:
                args.append('0')

        arg_str = ', '.join(args)

        # Declare sample inputs
        decls = []
        for param in params.split(','):
            param = param.strip()
            if not param:
                continue
            if 'vector<int>' in param:
                decls.append('    vector<int> nums = {2, 7, 11, 15};')
            elif 'vector<string>' in param:
                decls.append('    vector<string> strs = {"flower","flow","flight"};')
            elif 'string' in param and '&' in param:
                decls.append('    string s = "anagram";')
            elif 'int' in param:
                decls.append('    int target = 9;')

        decls_str = '\n'.join(decls)

        if ret_type == 'void':
            main_block = f"""
int main() {{
    Solution sol;
{decls_str}
    sol.{func_name}({arg_str});
    return 0;
}}"""
        elif 'vector' in ret_type:
            main_block = f"""
int main() {{
    Solution sol;
{decls_str}
    auto res = sol.{func_name}({arg_str});
    cout << "[";
    for (int i = 0; i < (int)res.size(); i++) {{
        if (i) cout << ", ";
        cout << res[i];
    }}
    cout << "]" << endl;
    return 0;
}}"""
        else:
            main_block = f"""
int main() {{
    Solution sol;
{decls_str}
    auto res = sol.{func_name}({arg_str});
    cout << res << endl;
    return 0;
}}"""
    else:
        main_block = "\nint main() { Solution sol; return 0; }\n"

    # Prepend headers if not already present
    if '#include' not in source:
        return headers + "\n" + source + "\n" + main_block
    return source + "\n" + main_block


def _normalize_java_leetcode(source: str) -> str:
    """
    If Java source has class Solution but no main(),
    wrap it so javac can compile it.
    """
    import re
    if _has_main(source):
        return source

    # Detect method name
    method_pat = re.search(
        r'public\s+(?:int\[\]|List<Integer>|String|int|boolean|double|void)\s+(\w+)\s*\(',
        source
    )
    func_name = method_pat.group(1) if method_pat else "twoSum"

    # Inject main into Solution class body (before last closing brace)
    main_inject = f"""
    public static void main(String[] args) {{
        Solution sol = new Solution();
        int[] nums = {{2, 7, 11, 15}};
        int[] result = sol.{func_name}(nums, 9);
        System.out.println(java.util.Arrays.toString(result));
    }}
"""
    # Insert before the last closing brace of the class
    last_brace = source.rfind('}')
    if last_brace != -1:
        return source[:last_brace] + main_inject + source[last_brace:]
    return source


def _normalize_c_leetcode(source: str) -> str:
    """C LeetCode style usually already has main in the snippet; add one if missing."""
    if _has_main(source):
        return source

    headers = "#include <stdio.h>\n#include <stdlib.h>\n"
    main_block = """
int main() {
    int nums[] = {2, 7, 11, 15};
    int returnSize;
    int* res = twoSum(nums, 4, 9, &returnSize);
    printf("[%d, %d]\\n", res[0], res[1]);
    free(res);
    return 0;
}
"""
    if '#include' not in source:
        return headers + "\n" + source + main_block
    return source + main_block




def _make_step(
    step_n: int,
    phase: str,
    line_no: int,
    note: str,
    stdout: str = "",
    variables: dict | None = None,
    event: str = "line",
) -> dict:
    """Create a timeline step dict matching the Python tracer schema."""
    return {
        "step":       step_n,
        "line":       line_no,
        "line_no":    line_no,
        "line_text":  "",
        "event":      event,
        "variables":  variables or {},
        "loops":      [],
        "call_stack": [{"name": phase, "line": line_no, "args": {}}],
        "stdout":     stdout,
        "func_call":  None,
        "return_val": None,
        "error":      None,
        "note":       note,
        "phase":      phase,
    }


def _build_output_timeline(
    source: str,
    stdout: str,
    stderr: str,
    return_code: int,
    language: str,
    compile_err: str = "",
) -> list[dict]:
    """
    Build a simplified execution timeline for compiled languages.
    Shows: compile → run → each output line → finish/error.
    """
    steps  = []
    source_lines = source.splitlines()

    # Step 1 — compile success
    steps.append(_make_step(1, "compile", 0,
                             f"Compiled {language} source successfully", event="call"))

    # Step 2+ — show each printed output line as a step
    out_lines = stdout.strip().splitlines() if stdout.strip() else []
    for i, line in enumerate(out_lines, start=2):
        steps.append(_make_step(
            i, "output", i - 1,
            f"Output: {line[:80]}",
            stdout="\n".join(out_lines[:i - 1]),
        ))

    # Final step — success or error
    n = len(steps) + 1
    if return_code == 0:
        steps.append(_make_step(
            n, "finish", len(source_lines),
            "Program finished successfully",
            stdout=stdout,
            event="return",
        ))
    else:
        err_preview = (stderr or "Non-zero exit code").strip().splitlines()[0][:80]
        steps.append(_make_step(
            n, "error", -1,
            f"Runtime Error: {err_preview}",
            stdout=stdout,
            event="exception",
        ))

    return steps


# ── C Executor ────────────────────────────────────────────────

def run_c(source: str, stdin: str = "") -> ExecutionResult:
    """Compile and run C code with gcc."""
    source = _normalize_c_leetcode(source)   # inject main() if LeetCode-style
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "main.c")
        exe_path = os.path.join(tmpdir, "main.exe")

        with open(src_path, "w") as f:
            f.write(source)

        # Compile
        comp_out, comp_err, comp_rc, _ = _run(
            ["gcc", src_path, "-o", exe_path, "-Wall", "-lm"]
        )
        if comp_rc != 0:
            return ExecutionResult(
                language="C", stdout="", stderr=comp_err,
                return_code=comp_rc, compile_ok=False,
                compile_err=comp_err, exec_time_ms=0,
                timeline=[_make_step(1, "compile_error", -1,
                                     f"Compile failed: {comp_err.splitlines()[0][:80]}",
                                     event="exception")],
            )

        # Run
        stdout, stderr, rc, elapsed = _run([exe_path], stdin=stdin)
        timeline = _build_output_timeline(source, stdout, stderr, rc, "C")
        return ExecutionResult(
            language="C", stdout=stdout, stderr=stderr,
            return_code=rc, compile_ok=True, compile_err="",
            exec_time_ms=elapsed, timeline=timeline,
        )


# ── C++ Executor ──────────────────────────────────────────────

def run_cpp(source: str, stdin: str = "") -> ExecutionResult:
    """Compile and run C++ code with g++."""
    source = _normalize_cpp_leetcode(source)  # inject headers + main() if LeetCode-style
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "main.cpp")
        exe_path = os.path.join(tmpdir, "main.exe")

        with open(src_path, "w") as f:
            f.write(source)

        comp_out, comp_err, comp_rc, _ = _run(
            ["g++", src_path, "-o", exe_path, "-std=c++17", "-Wall"]
        )
        if comp_rc != 0:
            return ExecutionResult(
                language="C++", stdout="", stderr=comp_err,
                return_code=comp_rc, compile_ok=False,
                compile_err=comp_err, exec_time_ms=0,
                timeline=[_make_step(1, "compile_error", -1,
                                     f"Compile failed: {comp_err.splitlines()[0][:80]}",
                                     event="exception")],
            )

        stdout, stderr, rc, elapsed = _run([exe_path], stdin=stdin)
        timeline = _build_output_timeline(source, stdout, stderr, rc, "C++")
        return ExecutionResult(
            language="C++", stdout=stdout, stderr=stderr,
            return_code=rc, compile_ok=True, compile_err="",
            exec_time_ms=elapsed, timeline=timeline,
        )


# ── Java Executor ─────────────────────────────────────────────

def _detect_java_class(source: str) -> str:
    """Extract the public class name from Java source."""
    import re
    m = re.search(r"public\s+class\s+(\w+)", source)
    return m.group(1) if m else "Main"


def run_java(source: str, stdin: str = "") -> ExecutionResult:
    """Compile and run Java code with javac + java."""
    source = _normalize_java_leetcode(source)  # inject main() if LeetCode-style
    class_name = _detect_java_class(source)

    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, f"{class_name}.java")

        with open(src_path, "w") as f:
            f.write(source)

        # Compile
        comp_out, comp_err, comp_rc, _ = _run(["javac", src_path])
        if comp_rc != 0:
            return ExecutionResult(
                language="Java", stdout="", stderr=comp_err,
                return_code=comp_rc, compile_ok=False,
                compile_err=comp_err, exec_time_ms=0,
                timeline=[_make_step(1, "compile_error", -1,
                                     f"Compile failed: {comp_err.splitlines()[0][:80]}",
                                     event="exception")],
            )

        # Run
        stdout, stderr, rc, elapsed = _run(
            ["java", "-cp", tmpdir, class_name], stdin=stdin
        )
        timeline = _build_output_timeline(source, stdout, stderr, rc, "Java")
        return ExecutionResult(
            language="Java", stdout=stdout, stderr=stderr,
            return_code=rc, compile_ok=True, compile_err="",
            exec_time_ms=elapsed, timeline=timeline,
        )


# ── JavaScript Executor (Node.js) ─────────────────────────────

def run_javascript(source: str, stdin: str = "") -> ExecutionResult:
    """Run JavaScript with Node.js."""
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = os.path.join(tmpdir, "main.js")
        with open(src_path, "w") as f:
            f.write(source)

        stdout, stderr, rc, elapsed = _run(["node", src_path], stdin=stdin)
        timeline = _build_output_timeline(source, stdout, stderr, rc, "JavaScript")
        return ExecutionResult(
            language="JavaScript", stdout=stdout, stderr=stderr,
            return_code=rc, compile_ok=True, compile_err="",
            exec_time_ms=elapsed, timeline=timeline,
        )


# ── Main dispatch ─────────────────────────────────────────────

_RUNNERS = {
    "C":          run_c,
    "C++":        run_cpp,
    "Java":       run_java,
    "JavaScript": run_javascript,
}

SUPPORTED_LANGUAGES = set(_RUNNERS.keys())


def run_code(source: str, language: str, stdin: str = "") -> ExecutionResult:
    """
    Dispatch to the appropriate language runner.
    Returns an ExecutionResult with a full timeline.
    """
    runner = _RUNNERS.get(language)
    if runner is None:
        return ExecutionResult(
            language=language, stdout="", stderr=f"No executor for {language}",
            return_code=-1, compile_ok=False, compile_err="",
            exec_time_ms=0, timeline=[],
        )
    return runner(source, stdin=stdin)


def result_to_json(result: ExecutionResult, indent: int = 2) -> str:
    """Serialize an ExecutionResult to JSON."""
    return json.dumps({
        "language":     result.language,
        "compile_ok":   result.compile_ok,
        "compile_err":  result.compile_err,
        "return_code":  result.return_code,
        "exec_time_ms": round(result.exec_time_ms, 2),
        "stdout":       result.stdout,
        "stderr":       result.stderr,
        "timeline":     result.timeline,
    }, indent=indent, default=str)
