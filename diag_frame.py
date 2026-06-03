"""Test cumulative snapshot rendering."""
import sys, os
sys.path.insert(0, r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")
os.chdir(r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")

from components.tracer import trace_python_code
from components.video_renderer import _render_frame, generate_video
import matplotlib; matplotlib.use("Agg")
from PIL import Image

code = """
nums = [2, 7, 11, 15]
target = 9
stack = []
seen = {}
dp = [[0]*3 for _ in range(3)]
for i, num in enumerate(nums):
    stack.append(num)
    complement = target - num
    if complement in seen:
        print([seen[complement], i])
        break
    seen[num] = i
"""

steps, err = trace_python_code(code, max_steps=300)
print(f"Steps: {len(steps)}, Error: {err}")

# Build cumulative like generate_video does
from components.video_renderer import generate_video as gv
cumulative_vars = {}
cumulative_structs = {}
enriched = []
for step in steps:
    cv = step.get("variables", {})
    cs = step.get("structures", [])
    if cv: cumulative_vars.update(cv)
    if cs:
        for s in cs: cumulative_structs[s["name"]] = s
    e = dict(step)
    e["variables"] = dict(cumulative_vars)
    e["structures"] = list(cumulative_structs.values())
    enriched.append(e)

# Render step 15 (in the loop, should have all vars)
idx = min(15, len(enriched)-1)
s = enriched[idx]
print(f"\nStep {s['step']} line={s['line']} note={s['note']}")
print(f"  vars: {list(s['variables'].keys())}")
print(f"  structs: {[(x['name'], x['kind']) for x in s['structures']]}")

frame = _render_frame(s, code.splitlines(), len(steps))
img = Image.fromarray(frame)
out = r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer\assets\test_frame2.png"
img.save(out)
print(f"\nFrame {frame.shape} saved -> {out}")
