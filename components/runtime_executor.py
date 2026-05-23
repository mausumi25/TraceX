"""
TraceX — Multi-Language Runtime Executor
Runs C, C++, and Java code via subprocess and produces
a structured execution timeline (compile + run steps).

For Python — use tracer.py (sys.settrace gives line-by-line tracing).
For C/C++/Java — we compile then execute, capturing stdout/stderr,
and generate a simplified but informative execution timeline.
"""

import os
import re
import subprocess
import tempfile
import json
import time
from dataclasses import dataclass, field


@dataclass
class CppParam:
    name: str
    cpp_type: str          # raw C++ type string e.g. "vector<int>&"
    py_kind: str           # 'int_list' | 'str_list' | 'int' | 'string' | 'float'


@dataclass
class CppSolution:
    func_name:   str
    return_type: str       # e.g. "vector<int>", "int", "string"
    params:      list[CppParam]


# ── C++ LeetCode signature parser ─────────────────────────────

def is_cpp_leetcode_style(source: str) -> bool:
    """Return True if source looks like a LeetCode C++ class Solution."""
    return bool(re.search(r'\bclass\s+Solution\b', source))


def parse_cpp_solution(source: str) -> CppSolution | None:
    """
    Parse the first public method inside class Solution.
    Returns a CppSolution with param names, types, and py_kind.
    """
    # Find the method signature inside Solution
    m = re.search(
        r'(vector\s*<[^>]+>|string|int|long long|long|bool|double|float|void)\s+'
        r'(\w+)\s*\(([^)]*)\)\s*\{',
        source
    )
    if not m:
        return None

    ret_type  = m.group(1).strip()
    func_name = m.group(2).strip()
    raw_params = m.group(3).strip()

    params: list[CppParam] = []
    for raw in raw_params.split(','):
        raw = raw.strip()
        if not raw:
            continue
        # Last token is the parameter name
        tokens = raw.replace('&', ' ').replace('*', ' ').split()
        if len(tokens) < 2:
            continue
        pname  = tokens[-1]
        ptype  = ' '.join(tokens[:-1])

        # Map C++ type → python kind for UI hint
        if 'vector<int>' in ptype or 'vector<long' in ptype:
            kind = 'int_list'
        elif 'vector<string>' in ptype or 'vector<char>' in ptype:
            kind = 'str_list'
        elif 'string' in ptype:
            kind = 'string'
        elif 'double' in ptype or 'float' in ptype:
            kind = 'float'
        elif 'int' in ptype or 'long' in ptype or 'bool' in ptype:
            kind = 'int'
        else:
            kind = 'string'

        params.append(CppParam(name=pname, cpp_type=ptype, py_kind=kind))

    return CppSolution(func_name=func_name, return_type=ret_type, params=params)


def _cpp_literal(value_str: str, kind: str) -> str:
    """Convert a user input string to a valid C++ literal."""
    v = value_str.strip()
    if kind == 'int_list':
        # Accept: [2,7,11,15] or 2 7 11 15
        nums = re.findall(r'-?\d+', v)
        return '{' + ', '.join(nums) + '}'
    elif kind == 'str_list':
        # Accept: ["a","b"] or a b
        items = re.findall(r'"([^"]*)"', v)
        if not items:
            items = [x.strip() for x in v.strip('[]').split(',') if x.strip()]
        return '{' + ', '.join(f'"{x}"' for x in items) + '}'
    elif kind == 'string':
        v = v.strip('"\'')
        return f'"{v}"'
    elif kind == 'float':
        try:
            return str(float(v))
        except Exception:
            return '0.0'
    else:  # int / long / bool
        try:
            return str(int(v))
        except Exception:
            return '0'


def _cpp_var_decl(param: CppParam, value_str: str) -> str:
    """Generate a C++ variable declaration for a parameter."""
    lit = _cpp_literal(value_str, param.py_kind)
    kind = param.py_kind
    name = param.name

    if kind == 'int_list':
        return f'    vector<int> {name} = {lit};'
    elif kind == 'str_list':
        return f'    vector<string> {name} = {lit};'
    elif kind == 'string':
        return f'    string {name} = {lit};'
    elif kind == 'float':
        return f'    double {name} = {lit};'
    else:
        return f'    int {name} = {lit};'


def build_cpp_main(solution: CppSolution, user_inputs: dict[str, str]) -> str:
    """
    Generate a main() function that instantiates Solution,
    declares user-supplied inputs, calls the method and prints the result.
    """
    decls = []
    call_args = []
    for param in solution.params:
        raw = user_inputs.get(param.name, "")
        decls.append(_cpp_var_decl(param, raw))
        call_args.append(param.name)

    decls_str = '\n'.join(decls)
    args_str  = ', '.join(call_args)
    ret       = solution.return_type

    if ret == 'void':
        print_line = f'    sol.{solution.func_name}({args_str});'
        output_line = '    cout << "Done" << endl;'
    elif 'vector' in ret:
        print_line = f'    auto res = sol.{solution.func_name}({args_str});'
        output_line = (
            '    cout << "[";\n'
            '    for (int i = 0; i < (int)res.size(); i++) {\n'
            '        if (i) cout << ", ";\n'
            '        cout << res[i];\n'
            '    }\n'
            '    cout << "]" << endl;'
        )
    elif ret == 'string':
        print_line  = f'    auto res = sol.{solution.func_name}({args_str});'
        output_line = '    cout << res << endl;'
    else:
        print_line  = f'    auto res = sol.{solution.func_name}({args_str});'
        output_line = '    cout << res << endl;'

    return (
        '\nint main() {\n'
        '    Solution sol;\n'
        f'{decls_str}\n'
        f'{print_line}\n'
        f'{output_line}\n'
        '    return 0;\n'
        '}'
    )





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


def _normalize_cpp_leetcode(source: str, user_inputs: dict | None = None) -> str:
    """
    If the C++ source is LeetCode-style (class Solution, no main),
    inject standard headers + a main() using user_inputs (or sample values).
    """
    if _has_main(source):
        return source

    headers = "#include <bits/stdc++.h>\nusing namespace std;\n"

    # Try to parse the method signature
    solution = parse_cpp_solution(source)

    if solution and user_inputs:
        # Use actual user-supplied values
        main_block = build_cpp_main(solution, user_inputs)
    elif solution:
        # Fall back to sample values per type
        sample = {}
        for p in solution.params:
            if p.py_kind == 'int_list':  sample[p.name] = '[2, 7, 11, 15]'
            elif p.py_kind == 'str_list': sample[p.name] = '["flower", "flow", "flight"]'
            elif p.py_kind == 'string':  sample[p.name] = 'anagram'
            elif p.py_kind == 'float':   sample[p.name] = '0.0'
            else:                         sample[p.name] = '9'
        main_block = build_cpp_main(solution, sample)
    else:
        main_block = "\nint main() { return 0; }\n"

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

def run_cpp(source: str, stdin: str = "", user_inputs: dict | None = None) -> ExecutionResult:
    """Compile and run C++ code with g++."""
    source = _normalize_cpp_leetcode(source, user_inputs)  # inject main() with user inputs
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


def run_code(source: str, language: str, stdin: str = "", user_inputs: dict | None = None) -> ExecutionResult:
    """
    Dispatch to the appropriate language runner.
    user_inputs: optional dict of {param_name: value_str} for C++ LeetCode mode.
    """
    if language == "C++":
        return run_cpp(source, stdin=stdin, user_inputs=user_inputs)
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
