from components.gdb_tracer import _build_gdb_commands
import subprocess, tempfile, os

code = '''#include <bits/stdc++.h>
using namespace std;
class Solution {
public:
    int singleNumber(vector<int>& nums) {
        int result = 0;
        for (int n : nums) result ^= n;
        return result;
    }
};
int main() {
    Solution sol;
    vector<int> nums = {2, 2, 1};
    auto res = sol.singleNumber(nums);
    cout << res << endl;
    return 0;
}'''

# Compile
with tempfile.TemporaryDirectory() as tmpdir:
    src = os.path.join(tmpdir, "main.cpp")
    exe = os.path.join(tmpdir, "main.exe")
    with open(src, "w") as f: f.write(code)
    r = subprocess.run(["g++", src, "-o", exe, "-std=c++17", "-g", "-O0"],
                       capture_output=True, text=True)
    print("compile:", r.returncode, r.stderr[:100])

    cmds = _build_gdb_commands(10)
    ex_args = []
    for c in cmds:
        ex_args += ["-ex", c]

    proc = subprocess.run(
        ["gdb", "--batch"] + ex_args + [exe],
        capture_output=True, text=True, timeout=30
    )
    raw = proc.stdout + proc.stderr
    # Print a section around STEP_BEGIN_0
    idx = raw.find("STEP_BEGIN_0")
    if idx >= 0:
        print("=== STEP 0 raw output ===")
        print(raw[idx:idx+800])
    else:
        print("STEP_BEGIN_0 not found, full output:")
        print(raw[:2000])
