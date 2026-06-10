"""
TraceX — Code Execution Visualizer
Main Streamlit Application
"""

import os
import streamlit as st
from components.styles import GLOBAL_CSS
from components.code_snippets import (
    FULL_PROGRAM_SNIPPETS,
    LEETCODE_SNIPPETS,
    LANGUAGE_META,
)
from components.input_parser import (
    detect_functions,
    is_leetcode_style,
    build_injected_source,
    FunctionSignature,
)
from components.syntax_checker import check_syntax
from components.video_renderer import generate_syntax_error_video
from components.tracer import trace_python_code, steps_to_json
from components.timeline_generator import (
    generate_timeline, timeline_to_json, timeline_summary,
    EV_LINE, EV_VAR_SET, EV_VAR_CHANGE,
    EV_ARR_UPDATE, EV_ARR_APPEND, EV_ARR_POP,
    EV_MATRIX_UPDATE, EV_LOOP_START, EV_LOOP_ITER, EV_LOOP_END,
    EV_COND, EV_FUNC_CALL, EV_FUNC_RETURN, EV_OUTPUT, EV_FINAL,
)
from components.runtime_executor import (
    run_code, SUPPORTED_LANGUAGES,
    is_cpp_leetcode_style, parse_cpp_solution,
)

# ── Page Config ───────────────────────────────────────────────
st.set_page_config(
    page_title="TraceX — Code Execution Visualizer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────
LANGUAGES = list(LANGUAGE_META.keys())

def _default_code(lang, mode):
    src = FULL_PROGRAM_SNIPPETS if mode == "Full Program" else LEETCODE_SNIPPETS
    return src.get(lang, "")


def _placeholder_for(param: str, hint: str) -> str:
    """Generate a helpful placeholder for each input field."""
    hints_map = {
        "List[int]": "e.g. [2, 7, 11, 15]",
        "List[str]": "e.g. ['a', 'b', 'c']",
        "int":       "e.g. 9",
        "str":       '"hello"',
        "float":     "e.g. 3.14",
        "bool":      "True or False",
    }
    if hint in hints_map:
        return hints_map[hint]
    name_map = {
        "nums":   "e.g. [2, 7, 11, 15]",
        "target": "e.g. 9",
        "s":      '"anagram"',
        "n":      "e.g. 5",
        "k":      "e.g. 3",
        "root":   "e.g. [1, 2, 3]",
    }
    return name_map.get(param, f"value for {param}")

for k, v in [
    ("language",        "Python"),
    ("exec_mode",       "Full Program"),
    ("video_path",      None),
    ("trace_error",     None),
    ("leet_inputs",     {}),
    ("leet_sig",        None),
    ("run_trigger",     False),
    ("timeline_result", None),   # rich typed timeline from TimelineGenerator
]:
    if k not in st.session_state:
        st.session_state[k] = v

if "code" not in st.session_state:
    st.session_state.code = _default_code("Python", "Full Program")


# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-logo">🔍 TraceX</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:0.75rem;color:#475569;">Code Execution Visualizer</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-label">⚡ Quick Actions</div>', unsafe_allow_html=True)

    if st.button("🗑️  Clear Editor", key="sidebar_clear"):
        st.session_state.code = ""
        st.session_state.code_textarea = ""   # sync widget key
        st.session_state.video_path = None
        st.session_state.leet_inputs = {}
        st.rerun()

    if st.button("🔄  Load Example", key="sidebar_example"):
        new_code = _default_code(st.session_state.language, st.session_state.exec_mode)
        st.session_state.code = new_code
        st.session_state.code_textarea = new_code  # sync widget key
        st.session_state.video_path = None
        st.session_state.leet_inputs = {}
        st.rerun()

    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">📊 Session Stats</div>', unsafe_allow_html=True)

    code_now = st.session_state.code or ""
    lines = len(code_now.splitlines())
    chars = len(code_now)
    st.markdown(
        f"""<div class="stat-grid">
            <div class="stat-card"><div class="stat-value">{lines}</div><div class="stat-label">Lines</div></div>
            <div class="stat-card"><div class="stat-value">{chars}</div><div class="stat-label">Chars</div></div>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-label">ℹ️ About</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.76rem;color:#475569;line-height:1.7;">TraceX visualizes code execution step-by-step — variables, call stacks, and control flow — making programs easy to understand.</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────
st.markdown(
    """<div class="tracex-hero">
        <h1>TraceX</h1>
        <div class="subtitle">Step-by-step code execution visualizer for every programmer</div>
        <div class="badge-row">
            <span class="badge">🐍 Python</span>
            <span class="badge">🌐 JavaScript</span>
            <span class="badge">⚙️ C</span>
            <span class="badge">⚡ C++</span>
            <span class="badge">☕ Java</span>
            <span class="badge">🎬 Video Output</span>
        </div>
    </div>""",
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────────────────────
# Main Layout
# ─────────────────────────────────────────────────────────────
left_col, right_col = st.columns([1, 2], gap="large")


# ═══ LEFT PANEL — Config ════════════════════════════════════
with left_col:

    # Language selector
    st.markdown('<div class="section-label">🌍 Select Language</div>', unsafe_allow_html=True)
    lang_cols = st.columns(len(LANGUAGES))
    for idx, lang in enumerate(LANGUAGES):
        meta = LANGUAGE_META[lang]
        with lang_cols[idx]:
            if st.button(f"{meta['icon']}\n{lang}", key=f"lang_{lang}", use_container_width=True):
                new_code = _default_code(lang, st.session_state.exec_mode)
                st.session_state.language = lang
                st.session_state.code = new_code
                st.session_state.code_textarea = new_code
                st.session_state.video_path = None
                st.session_state.leet_inputs = {}
                st.rerun()

    st.markdown(
        f"""<div style="margin-top:-0.3rem;margin-bottom:0.25rem;font-size:0.7rem;color:#475569;text-align:center">
            Active: <strong style="color:#A78BFA">{st.session_state.language}</strong>
            &nbsp;•&nbsp;
            <code style="color:#06B6D4;background:rgba(6,182,212,0.1);padding:1px 6px;border-radius:4px;">
                {LANGUAGE_META[st.session_state.language]['extension']}
            </code>
        </div>""",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Execution mode
    st.markdown('<div class="section-label">⚙️ Execution Mode</div>', unsafe_allow_html=True)
    ma, mb = st.columns(2)
    with ma:
        if st.button("🖥️ Full Program", key="mode_full", use_container_width=True,
                     type="primary" if st.session_state.exec_mode == "Full Program" else "secondary"):
            new_code = _default_code(st.session_state.language, "Full Program")
            st.session_state.exec_mode = "Full Program"
            st.session_state.code = new_code
            st.session_state.code_textarea = new_code
            st.session_state.video_path = None
            st.session_state.leet_inputs = {}
            st.rerun()
    with mb:
        if st.button("🏆 LeetCode", key="mode_leet", use_container_width=True,
                     type="primary" if st.session_state.exec_mode == "LeetCode" else "secondary"):
            new_code = _default_code(st.session_state.language, "LeetCode")
            st.session_state.exec_mode = "LeetCode"
            st.session_state.code = new_code
            st.session_state.code_textarea = new_code
            st.session_state.video_path = None
            st.session_state.leet_inputs = {}
            st.rerun()

    mode = st.session_state.exec_mode
    if mode == "Full Program":
        st.markdown(
            """<div class="mode-card active-full" style="margin-top:0.6rem">
                <div class="mode-icon">🖥️</div>
                <div class="mode-title">Full Program Mode</div>
                <div class="mode-desc">Execute a complete program with a <code>main()</code> entry point.
                TraceX traces every line, variable, and function call.</div>
            </div>""",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """<div class="mode-card active-leet" style="margin-top:0.6rem">
                <div class="mode-icon">🏆</div>
                <div class="mode-title">LeetCode Mode</div>
                <div class="mode-desc">Paste a LeetCode-style solution. TraceX auto-wraps it with
                a test harness and steps through the algorithm visually.</div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    lang = st.session_state.language
    can_trace = True     # all languages now supported
    run_clicked = st.button(
        "Run & Generate Video",
        key="run_btn",
        use_container_width=True,
    )
    if run_clicked:
        st.session_state.run_trigger = True
        st.session_state.video_path  = None

    st.markdown(
        f"""<div class="info-bar" style="justify-content:center;margin-top:0.5rem">
            <div class="info-pill">
                <span class="dot-indicator" style="background:{'#10B981' if mode=='Full Program' else '#F59E0B'};
                    box-shadow:0 0 6px {'rgba(16,185,129,0.6)' if mode=='Full Program' else 'rgba(245,158,11,0.6)'};"></span>
                {mode}
            </div>
            <div class="info-pill">{LANGUAGE_META[lang]['icon']} {lang}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# ═══ RIGHT PANEL — Editor ═══════════════════════════════════
with right_col:
    lang = st.session_state.language
    meta = LANGUAGE_META[lang]
    filename = f"solution{meta['extension']}"

    st.markdown(
        f"""<div class="editor-topbar">
            <div class="editor-dots">
                <div class="dot dot-red"></div>
                <div class="dot dot-amber"></div>
                <div class="dot dot-green"></div>
            </div>
            <div class="editor-filename">{filename}</div>
            <div class="editor-lang-badge">{lang}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    with st.container():
        st.markdown('<div class="editor-wrapper">', unsafe_allow_html=True)
        # NOTE: Do NOT pass value= when using key= — Streamlit manages
        # the widget value via st.session_state.code_textarea directly.
        if "code_textarea" not in st.session_state:
            st.session_state.code_textarea = st.session_state.code
        updated_code = st.text_area(
            label="code_editor",
            height=420,
            key="code_textarea",
            label_visibility="collapsed",
            placeholder=f"// Write or paste your {lang} code here...",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.session_state.code = updated_code
    lines = len(updated_code.splitlines()) if updated_code else 0
    chars = len(updated_code) if updated_code else 0

    st.markdown(
        f"""<div class="info-bar">
            <div class="info-pill"><span class="dot-indicator"></span> Ready</div>
            <div class="info-pill">📄 {lines} Lines</div>
            <div class="info-pill">🔤 {chars} Chars</div>
            <div class="info-pill">🗂️ {filename}</div>
        </div>""",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# LeetCode Input Panel (shown BELOW editor when LeetCode mode)
# ─────────────────────────────────────────────────────────────
code_snapshot = st.session_state.code or ""
lang          = st.session_state.language
mode          = st.session_state.exec_mode

need_inputs = (
    lang == "Python"
    and mode == "LeetCode"
    and is_leetcode_style(code_snapshot)
)

if need_inputs:
    sigs = detect_functions(code_snapshot)
    sig = next((s for s in sigs if s.params), None)
    st.session_state.leet_sig = sig

    if sig:
        st.markdown("---")
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.75rem">
                <span style="font-size:1.1rem">&#129513;</span>
                <span style="font-size:0.8rem;font-weight:700;letter-spacing:1.5px;
                             text-transform:uppercase;color:#94A3B8">
                    Test Input &nbsp;&mdash;&nbsp;
                    <code style="color:#A78BFA;font-size:0.85rem">{sig.name}()</code>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container():
            st.markdown(
                '<div style="background:#1A1A35;border:1px solid rgba(124,58,237,0.3);'
                'border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:0.5rem">',
                unsafe_allow_html=True,
            )
            cols = st.columns(max(1, min(len(sig.params), 3)))
            for idx, param in enumerate(sig.params):
                hint = sig.type_hints.get(param, "")
                label = f"`{param}`" + (f" `{hint}`" if hint else "")
                placeholder = _placeholder_for(param, hint)
                with cols[idx % len(cols)]:
                    val = st.text_input(
                        label,
                        value=st.session_state.leet_inputs.get(param, ""),
                        placeholder=placeholder,
                        key=f"leet_input_{param}",
                    )
                    st.session_state.leet_inputs[param] = val
            st.markdown("</div>", unsafe_allow_html=True)

        args_preview = ", ".join(
            f"{p}={st.session_state.leet_inputs.get(p, '...')}"
            for p in sig.params
        )
        call_preview = (
            f"Solution().{sig.name}({args_preview})"
            if sig.is_method else f"{sig.name}({args_preview})"
        )
        st.markdown(
            f'<div class="tooltip-card" style="margin-top:0">'
            f'<strong>Injected call:</strong><br/>'
            f'<code style="color:#06B6D4">{call_preview}</code>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No parameterised functions detected — running as-is.")
        st.session_state.leet_sig = None

# ── C++ LeetCode Input Panel ──────────────────────────────────
cpp_need_inputs = (
    lang == "C++"
    and mode == "LeetCode"
    and is_cpp_leetcode_style(code_snapshot)
)

if "cpp_leet_inputs" not in st.session_state:
    st.session_state.cpp_leet_inputs = {}
if "cpp_leet_sig" not in st.session_state:
    st.session_state.cpp_leet_sig = None

if cpp_need_inputs:
    cpp_sol = parse_cpp_solution(code_snapshot)
    st.session_state.cpp_leet_sig = cpp_sol

    if cpp_sol and cpp_sol.params:
        st.markdown("---")
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.75rem">
                <span style="font-size:1.1rem">&#129513;</span>
                <span style="font-size:0.8rem;font-weight:700;letter-spacing:1.5px;
                             text-transform:uppercase;color:#94A3B8">
                    C++ Test Input &nbsp;&mdash;&nbsp;
                    <code style="color:#A78BFA;font-size:0.85rem">{cpp_sol.func_name}()</code>
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _KIND_PLACEHOLDER = {
            'int_list':  'e.g. [2, 7, 11, 15]',
            'str_list':  'e.g. ["flower", "flow", "flight"]',
            'int':       'e.g. 9',
            'string':    'e.g. anagram',
            'float':     'e.g. 3.14',
        }
        _KIND_LABEL = {
            'int_list':  'vector&lt;int&gt;',
            'str_list':  'vector&lt;string&gt;',
            'int':       'int',
            'string':    'string',
            'float':     'double',
        }

        with st.container():
            st.markdown(
                '<div style="background:#1A1A35;border:1px solid rgba(124,58,237,0.3);'
                'border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:0.5rem">',
                unsafe_allow_html=True,
            )
            cols = st.columns(max(1, min(len(cpp_sol.params), 3)))
            for idx, param in enumerate(cpp_sol.params):
                type_label = _KIND_LABEL.get(param.py_kind, param.cpp_type)
                ph = _KIND_PLACEHOLDER.get(param.py_kind, 'value')
                with cols[idx % len(cols)]:
                    val = st.text_input(
                        f"`{param.name}` — `{type_label}`",
                        value=st.session_state.cpp_leet_inputs.get(param.name, ""),
                        placeholder=ph,
                        key=f"cpp_leet_{param.name}",
                    )
                    st.session_state.cpp_leet_inputs[param.name] = val
            st.markdown("</div>", unsafe_allow_html=True)

        # Preview injected call
        args_preview = ", ".join(
            f"{p.name}={st.session_state.cpp_leet_inputs.get(p.name, '...')}"
            for p in cpp_sol.params
        )
        st.markdown(
            f'<div class="tooltip-card" style="margin-top:0">'
            f'<strong>Will call:</strong><br/>'
            f'<code style="color:#06B6D4">sol.{cpp_sol.func_name}({args_preview})</code>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No method detected in class Solution — will run with sample inputs.")


# (_placeholder_for is defined at top of file)


# ─────────────────────────────────────────────────────────────
# Run → Trace → Video
# ─────────────────────────────────────────────────────────────
if st.session_state.run_trigger:
    st.session_state.run_trigger = False   # reset
    code = st.session_state.code.strip()
    if not code:
        st.warning("⚠️ Editor is empty. Write some Python code first.")
    else:
        st.markdown("---")

        # ── Step 0: Syntax Check ─────────────────────────────
        syn_err = check_syntax(code, st.session_state.language)
        if syn_err:
            st.error(
                f"🚫 **Syntax Error** on **line {syn_err.line}**: `{syn_err.message}`\n\n"
                f"Fix the error in the editor, then click Trace again."
            )
            with st.status("🎬 Generating syntax-error video…", expanded=True) as se_status:
                st.write(f"❌ Syntax error at line {syn_err.line}: {syn_err.message}")
                try:
                    out_dir = os.path.join(os.path.dirname(__file__), "assets")
                    os.makedirs(out_dir, exist_ok=True)
                    out_path = os.path.join(out_dir, "tracex_output.mp4")
                    generate_syntax_error_video(
                        source=code,
                        language=st.session_state.language,
                        error_line=syn_err.line,
                        error_msg=syn_err.message,
                        output_path=out_path,
                    )
                    st.session_state.video_path = out_path
                    st.session_state.trace_error = f"SyntaxError at line {syn_err.line}: {syn_err.message}"
                    st.write("✅ Error video ready.")
                    se_status.update(label="🚫 Syntax Error — video generated.", state="error")
                except Exception as ve:
                    st.error(f"Video render failed: {ve}")
                    se_status.update(label="Video generation failed.", state="error")
            st.stop()

        # ── Inject test call for LeetCode mode ───────────────
        run_source = code
        if (
            st.session_state.exec_mode == "LeetCode"
            and is_leetcode_style(code)
            and st.session_state.leet_sig
            and st.session_state.leet_sig.params
        ):
            sig = st.session_state.leet_sig
            raw_inputs = {
                p: st.session_state.leet_inputs.get(p, "")
                for p in sig.params
            }

            # Check all inputs filled
            missing = [p for p in sig.params if not raw_inputs.get(p, "").strip()]
            if missing:
                st.error(
                    f"⚠️ Please fill in inputs for: **{', '.join(missing)}** before tracing."
                )
                st.stop()

            run_source, parsed_vals, errs = build_injected_source(
                code, sig, raw_inputs
            )
            if errs:
                st.error("⚠️ Input validation errors:\n" + "\n".join(errs))
                st.stop()

            with st.expander("🔍 Injected Source Preview", expanded=False):
                st.code(run_source, language="python")

        # ── Step 1: Execute / Trace ───────────────────────────
        lang = st.session_state.language
        with st.status(f"Running {lang}...", expanded=True) as status:
            steps      = []
            error      = None
            stdout_out = ""

            if lang == "Python":
                st.write("🔵 Running Python tracer (sys.settrace)...")
                try:
                    steps, error = trace_python_code(run_source, max_steps=500)
                    stdout_out = steps[-1]["stdout"] if steps else ""
                    st.write(f"✅ Captured **{len(steps)} execution steps**")
                except Exception as exc:
                    st.error(f"Tracer failed: {exc}")
                    st.stop()

                # ── Generate rich typed timeline (new) ────────
                st.write("🟣 Building Execution Timeline...")
                try:
                    tl_result = generate_timeline(run_source, max_events=3000)
                    st.session_state.timeline_result = tl_result
                    ev_counts  = timeline_summary(tl_result)
                    total_evs  = len(tl_result["timeline"])
                    st.write(
                        f"✅ Timeline: **{total_evs} events** — "
                        + "  ".join(
                            f"`{k}×{v}`"
                            for k, v in sorted(ev_counts.items(), key=lambda x: -x[1])
                            if k not in (EV_FINAL,)
                        )
                    )
                except Exception as exc:
                    import traceback as _tb
                    st.warning(f"Timeline generation warning: {exc}")
                    st.session_state.timeline_result = None

            else:
                # C / C++ / Java / JavaScript via subprocess
                st.write(f"Compiling and running {lang}...")
                try:
                    cpp_inputs = None
                    if lang == "C++" and st.session_state.exec_mode == "LeetCode":
                        cpp_inputs = st.session_state.get("cpp_leet_inputs") or None
                    result = run_code(code, lang, user_inputs=cpp_inputs)
                    steps      = result.timeline
                    stdout_out = result.stdout
                    if not result.compile_ok:
                        error = result.compile_err
                        st.error(f"Compile error:\n```\n{error}\n```")
                    elif result.return_code != 0:
                        error = result.stderr
                    st.write(
                        f"Captured **{len(steps)} timeline steps** | "
                        f"exit {result.return_code} | "
                        f"{result.exec_time_ms:.1f} ms"
                    )
                    if stdout_out:
                        with st.expander("Program Output", expanded=True):
                            st.code(stdout_out, language="text")
                except Exception as exc:
                    import traceback as _tb
                    st.error(f"Execution failed: {exc}")
                    st.code(_tb.format_exc())
                    st.stop()

            # ── Save rich timeline JSON ────────────────────────
            out_dir = os.path.join(os.path.dirname(__file__), "assets")
            os.makedirs(out_dir, exist_ok=True)
            timeline_path = os.path.join(out_dir, "timeline.json")
            tl_result = st.session_state.get("timeline_result")
            if tl_result:
                with open(timeline_path, "w", encoding="utf-8") as jf:
                    jf.write(timeline_to_json(tl_result))
                total_evs = len(tl_result["timeline"])
            else:
                # Fallback: save old-style steps
                with open(timeline_path, "w", encoding="utf-8") as jf:
                    jf.write(steps_to_json(steps))
                total_evs = len(steps)
            st.session_state.timeline_path = timeline_path
            st.write(f"💾 Timeline saved — **{total_evs} events** → `assets/timeline.json`")

            # ── Step 2: Render Video ──────────────────────────
            st.write("Rendering video frames...")
            try:
                from components.video_renderer import generate_video
                out_path = os.path.join(out_dir, "tracex_output.mp4")
                generate_video(
                    steps=steps,
                    source=run_source if lang == "Python" else code,
                    language=lang,
                    mode=st.session_state.exec_mode,
                    error=error,
                    output_path=out_path,
                )
                st.session_state.video_path  = out_path
                st.session_state.trace_error = error
                st.write("Video rendered  tracex_output.mp4")
            except Exception as exc:
                import traceback
                st.error(f"Video render failed: {exc}")
                st.code(traceback.format_exc())
                st.stop()

            status.update(label="Done! Video ready.", state="complete")


# ─────────────────────────────────────────────────────────────
# Video Player
# ─────────────────────────────────────────────────────────────
if st.session_state.get("video_path") and os.path.exists(st.session_state.video_path):
    st.markdown("---")
    st.markdown(
        """<div class="section-label" style="font-size:0.85rem;letter-spacing:1.5px;">
            🎬 EXECUTION VISUALIZATION
        </div>""",
        unsafe_allow_html=True,
    )

    vc1, vc2 = st.columns([3, 1])
    with vc1:
        with open(st.session_state.video_path, "rb") as f:
            st.video(f.read(), format="video/mp4")

    with vc2:
        st.markdown(
            f"""<div class="tooltip-card" style="margin-top:0">
                <strong>📊 Trace Summary</strong><br/><br/>
                🌐 <strong>Language:</strong> {st.session_state.language}<br/>
                ⚙️ <strong>Mode:</strong> {st.session_state.exec_mode}<br/>
                {'🎬 <strong>Status:</strong> <span style="color:#10B981">Success</span>' 
                  if not st.session_state.trace_error 
                  else '💥 <strong>Status:</strong> <span style="color:#F43F5E">Error</span>'}
            </div>""",
            unsafe_allow_html=True,
        )

        # Download MP4
        with open(st.session_state.video_path, "rb") as f:
            st.download_button(
                label="Download MP4",
                data=f,
                file_name="tracex_visualization.mp4",
                mime="video/mp4",
                use_container_width=True,
            )

        # Download JSON timeline
        tpath = st.session_state.get("timeline_path", "")
        if tpath and os.path.exists(tpath):
            with open(tpath, "r", encoding="utf-8") as jf:
                st.download_button(
                    label="Download Timeline JSON",
                    data=jf.read(),
                    file_name="tracex_timeline.json",
                    mime="application/json",
                    use_container_width=True,
                )

        if st.session_state.trace_error:
            with st.expander("Error Details"):
                st.code(st.session_state.trace_error, language="python")

    # ── Execution Timeline Viewer ─────────────────────────────
    _tl_result = st.session_state.get("timeline_result")
    if _tl_result and _tl_result.get("timeline"):
        _tl = _tl_result["timeline"]
        _summary = timeline_summary(_tl_result)
        _total   = len(_tl)

        # ── Event-type color map ──────────────────────────────
        _EV_STYLE = {
            EV_LINE         : ("📍", "#1e293b",  "#64748b"),   # icon, bg, text
            EV_VAR_SET      : ("🟢", "#052e16",  "#4ade80"),
            EV_VAR_CHANGE   : ("🟠", "#431407",  "#fb923c"),
            EV_ARR_UPDATE   : ("🔵", "#0c1a4a",  "#60a5fa"),
            EV_ARR_APPEND   : ("🔵", "#082f49",  "#38bdf8"),
            EV_ARR_POP      : ("🔵", "#0c1a4a",  "#93c5fd"),
            EV_MATRIX_UPDATE: ("🟡", "#422006",  "#fbbf24"),
            EV_LOOP_START   : ("🔄", "#1a0a4a",  "#a78bfa"),
            EV_LOOP_ITER    : ("🔄", "#130533",  "#c4b5fd"),
            EV_LOOP_END     : ("🔄", "#1a0a4a",  "#7c3aed"),
            EV_COND         : ("❓", "#1c1917",  "#d97706"),
            EV_FUNC_CALL    : ("📞", "#0f172a",  "#818cf8"),
            EV_FUNC_RETURN  : ("↩️", "#0f172a",  "#6ee7b7"),
            EV_OUTPUT       : ("🖨️", "#052e16",  "#86efac"),
            EV_FINAL        : ("🏁", "#0f172a",  "#f8fafc"),
        }

        with st.expander(
            f"📊 Execution Timeline — {_total} events",
            expanded=True,
        ):
            # ── Summary badges ────────────────────────────────
            badge_html = ""
            _BADGE_ORDER = [
                EV_FUNC_CALL, EV_FUNC_RETURN,
                EV_LOOP_START, EV_LOOP_ITER, EV_LOOP_END,
                EV_COND,
                EV_VAR_SET, EV_VAR_CHANGE,
                EV_ARR_UPDATE, EV_ARR_APPEND, EV_ARR_POP,
                EV_MATRIX_UPDATE,
                EV_OUTPUT, EV_LINE,
            ]
            for ev_type in _BADGE_ORDER:
                cnt = _summary.get(ev_type, 0)
                if cnt == 0:
                    continue
                icon, bg, fg = _EV_STYLE.get(ev_type, ("•", "#1e293b", "#94a3b8"))
                label = ev_type.replace("_", " ").title()
                badge_html += (
                    f'<span style="display:inline-block;margin:3px;padding:3px 10px;'
                    f'border-radius:12px;background:{bg};color:{fg};'
                    f'font-size:0.75rem;font-family:monospace;font-weight:600;">'
                    f'{icon} {label}: {cnt}</span>'
                )
            st.markdown(
                f'<div style="margin-bottom:12px">{badge_html}</div>',
                unsafe_allow_html=True,
            )

            # ── Filter controls ───────────────────────────────
            _fc1, _fc2 = st.columns([2, 1])
            with _fc1:
                _filter_types = st.multiselect(
                    "Filter by event type",
                    options=sorted(_summary.keys()),
                    default=[t for t in _summary if t != EV_LINE],
                    key="tl_filter",
                )
            with _fc2:
                _max_rows = st.slider(
                    "Max rows", 20, min(_total, 500), 100, key="tl_max"
                )

            # ── Build display rows ────────────────────────────
            import json as _json
            _rows = []
            for ev in _tl:
                ev_t = ev.get("event", "?")
                if _filter_types and ev_t not in _filter_types:
                    continue
                icon, _bg, _fg = _EV_STYLE.get(ev_t, ("•", "", ""))

                # Build a human description per event type
                if ev_t == EV_LINE:
                    desc = f"Line {ev.get('line','')}  `{ev.get('code','')[:60]}`"
                elif ev_t == EV_VAR_SET:
                    desc = f"`{ev['name']}` = `{ev['value'][:50]}`  ({ev['type']})"
                elif ev_t == EV_VAR_CHANGE:
                    desc = f"`{ev['name']}`:  `{ev.get('old_value','?')[:30]}` → `{ev.get('new_value','?')[:30]}`"
                elif ev_t == EV_ARR_UPDATE:
                    desc = f"`{ev['var']}[{ev['index']}]`:  `{ev['old_value']}` → `{ev['new_value']}`"
                elif ev_t == EV_ARR_APPEND:
                    desc = f"`{ev['var']}`.append(`{ev['value']}`)  → len={ev['new_len']}"
                elif ev_t == EV_ARR_POP:
                    desc = f"`{ev['var']}`.pop()  len {ev['old_len']} → {ev['new_len']}"
                elif ev_t == EV_MATRIX_UPDATE:
                    desc = f"`{ev['var']}[{ev['row']}][{ev['col']}]`:  `{ev['old_value']}` → `{ev['new_value']}`"
                elif ev_t == EV_LOOP_START:
                    desc = f"Loop `{ev.get('loop_var','?')}` in `{ev.get('iterable', ev.get('condition','?'))}` — line {ev.get('line','')}"
                elif ev_t == EV_LOOP_ITER:
                    desc = f"Iteration #{ev.get('iteration','?')} — `{ev.get('loop_var','?')}` = `{ev.get('value', ev.get('result','?'))}`"
                elif ev_t == EV_LOOP_END:
                    desc = f"Loop ended — {ev.get('iterations','?')} iterations"
                elif ev_t == EV_COND:
                    r = "✓ True" if ev.get("result") else "✗ False"
                    desc = f"`{ev.get('expression','?')[:60]}` → **{r}**"
                elif ev_t == EV_FUNC_CALL:
                    args = ", ".join(f"{k}={v}" for k, v in ev.get("arguments", {}).items())
                    desc = f"`{ev['function']}({args[:60]})`"
                elif ev_t == EV_FUNC_RETURN:
                    desc = f"`{ev['function']}` returned `{ev.get('value','?')[:50]}`"
                elif ev_t == EV_OUTPUT:
                    desc = f"stdout: `{ev.get('text','')[:80]}`"
                elif ev_t == EV_FINAL:
                    desc = f"stdout={ev.get('stdout','')!r}  error={ev.get('error','None')}"
                else:
                    desc = _json.dumps(
                        {k: v for k, v in ev.items() if k not in ("seq", "event")},
                        default=str
                    )[:100]

                _rows.append({
                    "#"    : ev.get("seq", ""),
                    "Type" : f"{icon} {ev_t}",
                    "Detail": desc,
                })
                if len(_rows) >= _max_rows:
                    break

            # ── Render table ──────────────────────────────────
            import pandas as _pd
            try:
                _df = _pd.DataFrame(_rows)
                st.dataframe(
                    _df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "#"    : st.column_config.NumberColumn("#", width="small"),
                        "Type" : st.column_config.TextColumn("Event Type", width="medium"),
                        "Detail": st.column_config.TextColumn("Detail", width="large"),
                    },
                )
            except Exception:
                for r in _rows[:50]:
                    st.text(str(r))

            # ── Download rich timeline JSON ────────────────────
            _tpath = st.session_state.get("timeline_path", "")
            if _tpath and os.path.exists(_tpath):
                with open(_tpath, "r", encoding="utf-8") as _jf:
                    st.download_button(
                        label="⬇ Download timeline.json",
                        data=_jf.read(),
                        file_name="tracex_timeline.json",
                        mime="application/json",
                        use_container_width=True,
                        key="dl_timeline_rich",
                    )




# ─────────────────────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────────────────────
st.markdown(
    """<div style="text-align:center;margin-top:3rem;padding:1.5rem;
                  border-top:1px solid rgba(124,58,237,0.15);">
        <span style="font-size:0.72rem;color:#334155;">
            🔍 <strong style="color:#7C3AED">TraceX</strong>
            &nbsp;•&nbsp; Web-based Code Execution Visualizer
            &nbsp;•&nbsp; Built with Streamlit + Matplotlib
        </span>
    </div>""",
    unsafe_allow_html=True,
)
