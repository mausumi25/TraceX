import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer')
os.chdir(r'c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer')

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
summary = timeline_summary(result)

print(f"Total events : {len(result['timeline'])}")
print(f"stdout       : {result['stdout']!r}")
print(f"error        : {result['error']}")
print()
print("Event type counts:")
for k, v in sorted(summary.items(), key=lambda x: -x[1]):
    print(f"  {k:<25} {v}")

print()
print("=" * 72)
print("FULL TIMELINE:")
print("=" * 72)
SKIP_KEYS = {"seq", "event"}
for ev in result["timeline"]:
    t = ev.get("event")
    s = ev.get("seq", "?")
    meta = {k: v for k, v in ev.items() if k not in SKIP_KEYS}
    line = json.dumps(meta, default=str)[:110]
    print(f"  [{s:>3}] {t:<22} {line}")
