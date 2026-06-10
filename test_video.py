"""Full end-to-end video generation test."""
import sys, os
sys.path.insert(0, r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")
os.chdir(r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer")

from components.tracer import trace_python_code
from components.video_renderer import generate_video
import matplotlib; matplotlib.use("Agg")

code = """
nums = [2, 7, 11, 15]
target = 9
stack = []
seen = {}
for i, num in enumerate(nums):
    stack.append(num)
    complement = target - num
    if complement in seen:
        print([seen[complement], i])
        break
    seen[num] = i
"""

steps, err = trace_python_code(code, max_steps=200)
print(f"Steps: {len(steps)}")
out = r"c:\Users\MAUSAMI\OneDrive\Desktop\Tracex\TraceX-Code-Execution-Visualizer\assets\test_video.mp4"
path = generate_video(steps, code, "Python", "Full Program", err, out)
print(f"Video saved: {path}")
import os
print(f"File size: {os.path.getsize(path):,} bytes")
