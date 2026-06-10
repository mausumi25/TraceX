"""
Test the timeline generator against the spec examples.
"""
import sys, os, json
sys.path.insert(0, r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")
os.chdir(r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")

from components.timeline_generator import generate_timeline, timeline_summary

CODE = """
def twoSum(nums, target):
    seen = {}
    dp = [[0]*3 for _ in range(3)]
    for i, num in enumerate(nums):
        dp[i][0] = num
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []

nums   = [2, 7, 11, 15]
target = 9
result = twoSum(nums, target)
print(result)
"""

result = generate_timeline(CODE)
tl     = result["timeline"]

print(f"Total events: {len(tl)}")
print(f"stdout      : {result['stdout']!r}")
print(f"error       : {result['error']}")
print()

# Print summary counts
summary = timeline_summary(result)
print("Event type counts:")
for k, v in sorted(summary.items(), key=lambda x: -x[1]):
    print(f"  {k:<25} {v}")
print()

# Print first 50 events formatted
print("=" * 70)
print("TIMELINE (first 60 events):")
print("=" * 70)
for ev in tl[:60]:
    seq = ev.get("seq", "?")
    t   = ev.get("event", "?")
    line= ev.get("line", "")
    code= ev.get("code", ev.get("text", ev.get("value", "")))

    if t == "line_execute":
        print(f"[{seq:>4}] LINE {line:>3} | {code}")
    elif t == "variable_set":
        print(f"[{seq:>4}] SET      {ev['name']} = {ev['value'][:40]}  ({ev['type']})")
    elif t == "variable_change":
        print(f"[{seq:>4}] CHANGED  {ev['name']}  {ev['old_value'][:20]} → {ev['new_value'][:20]}")
    elif t == "array_update":
        print(f"[{seq:>4}] ARR_UPD  {ev['var']}[{ev['index']}] {ev['old_value']} → {ev['new_value']}")
    elif t == "array_append":
        print(f"[{seq:>4}] APPEND   {ev['var']}[{ev['index']}] = {ev['value']}")
    elif t == "array_pop":
        print(f"[{seq:>4}] POP      {ev['var']}  len {ev['old_len']}→{ev['new_len']}")
    elif t == "matrix_cell_update":
        print(f"[{seq:>4}] MATRIX   {ev['var']}[{ev['row']}][{ev['col']}] {ev['old_value']}→{ev['new_value']}")
    elif t == "loop_start":
        print(f"[{seq:>4}] LOOP_START line={line}  var={ev.get('loop_var','?')}  iter={ev.get('iterable','?')}")
    elif t == "loop_iteration":
        print(f"[{seq:>4}] LOOP_ITER  #{ev['iteration']}  {ev.get('loop_var','?')}={ev.get('value','?')}")
    elif t == "loop_end":
        print(f"[{seq:>4}] LOOP_END   line={ev['line']}  total={ev['iterations']} iterations")
    elif t == "condition_check":
        r = "✓ True" if ev.get("result") else "✗ False"
        print(f"[{seq:>4}] COND     {ev['expression'][:40]}  → {r}")
    elif t == "function_call":
        args = ", ".join(f"{k}={v}" for k,v in ev.get("arguments",{}).items())
        print(f"[{seq:>4}] CALL     {ev['function']}({args[:50]})")
    elif t == "function_return":
        print(f"[{seq:>4}] RETURN   {ev['function']} → {ev['value'][:40]}")
    elif t == "output":
        print(f"[{seq:>4}] OUTPUT   {ev['text']}")
    elif t == "final_output":
        print(f"[{seq:>4}] FINAL    stdout={ev['stdout']!r}  error={ev['error']}")
    else:
        print(f"[{seq:>4}] {t}  {json.dumps({k:v for k,v in ev.items() if k!='seq'})[:80]}")

# Save full result
out = r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer\assets\timeline_test.json"
with open(out, "w") as f:
    json.dump(result, f, indent=2, default=str)
print(f"\nFull timeline saved: {out}")
