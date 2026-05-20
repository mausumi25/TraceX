# 🔍 TraceX — Code Execution Visualizer

A **web-based, step-by-step code execution visualizer** that traces Python programs and generates a cinematic MP4 video showing every variable change, function call, and line of execution.

## ✨ Features

- 🐍 **Python Tracer** — `sys.settrace` hooks into execution, capturing every step
- 🎬 **Video Output** — Generates MP4 with highlighted code, live variable panel, call stack
- 🏆 **LeetCode Mode** — Auto-detects `class Solution` style code, shows dynamic input fields, injects test call
- 🖥️ **Full Program Mode** — Traces complete programs end-to-end
- ⬇️ **Download MP4** — Save the visualization locally

## 🛠️ Tech Stack

| Purpose | Technology |
|---|---|
| UI | Streamlit |
| Code Editor | Streamlit text_area |
| Tracing | Python `sys.settrace` |
| Video Frames | Matplotlib |
| Video Compile | imageio + imageio-ffmpeg |
| Function Parsing | Python AST |
| Input Injection | `exec()` |

## 🚀 Getting Started

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/TraceX-Code-Execution-Visualizer.git
cd TraceX-Code-Execution-Visualizer

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the app
streamlit run app.py
```

Open your browser at **http://localhost:8501**

## 📁 Project Structure

```
TraceX-Code-Execution-Visualizer/
├── app.py                    # Main Streamlit application
├── requirements.txt          # Python dependencies
├── .streamlit/
│   └── config.toml           # Dark theme config
└── components/
    ├── styles.py             # Premium CSS styles
    ├── code_snippets.py      # Default code examples
    ├── tracer.py             # Python sys.settrace tracer
    ├── video_renderer.py     # Matplotlib frame renderer → MP4
    └── input_parser.py       # AST function detector + input injector
```

## 🎬 How It Works

1. **Write or paste** Python code in the editor
2. **Select mode** — Full Program or LeetCode
3. For LeetCode: **fill in test inputs** (auto-detected from function signature)
4. Click **▶ Trace & Generate Video**
5. Watch the **step-by-step video** play in your browser
6. **Download the MP4** for sharing

## 📝 Example — LeetCode Mode

Paste this code:
```python
class Solution(object):
    def twoSum(self, nums, target):
        num_map = {}
        for i, num in enumerate(nums):
            complement = target - num
            if complement in num_map:
                return [num_map[complement], i]
            num_map[num] = i
```

TraceX detects `twoSum(nums, target)`, shows input fields, you enter:
- `nums` = `[2, 7, 11, 15]`
- `target` = `9`

And generates a full execution trace video! ✅
