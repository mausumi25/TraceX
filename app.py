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
    ("language",   "Python"),
    ("exec_mode",  "Full Program"),
    ("video_path", None),
    ("trace_error", None),
    ("leet_inputs", {}),          # raw user strings per param
    ("leet_sig",    None),         # detected FunctionSignature
    ("run_trigger", False),
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

    # Run button — only for Python
    lang = st.session_state.language
    can_trace = (lang == "Python")
    run_clicked = st.button(
        "▶  Trace & Generate Video",
        key="run_btn",
        use_container_width=True,
        disabled=not can_trace,
    )
    if not can_trace:
        st.markdown(
            f'<div class="tooltip-card">⚠️ Live tracing supports <strong>Python</strong> only. '
            f'{lang} support coming soon.</div>',
            unsafe_allow_html=True,
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
    # Pick the first non-trivial function
    sig = next((s for s in sigs if s.params), None)
    st.session_state.leet_sig = sig

    if sig:
        st.markdown("---")
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.75rem">
                <span style="font-size:1.1rem">🧩</span>
                <span style="font-size:0.8rem;font-weight:700;letter-spacing:1.5px;
                             text-transform:uppercase;color:#94A3B8">
                    Test Input &nbsp;—&nbsp;
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

            # One input field per parameter
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

        # Preview injected call
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
        st.info("ℹ️ No parameterised functions detected — running as-is.")
        st.session_state.leet_sig = None


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

        # ── Step 1: Trace ────────────────────────────────────
        with st.status("⚙️ Tracing code execution…", expanded=True) as status:
            st.write("🔬 Running Python tracer (sys.settrace)…")
            try:
                from components.tracer import trace_python_code
                steps, error = trace_python_code(run_source, max_steps=300)
                st.write(f"✅ Captured **{len(steps)} execution steps**")
            except Exception as e:
                st.error(f"Tracer failed: {e}")
                st.stop()

            # ── Step 2: Render Video ─────────────────────────
            st.write("🎬 Rendering video frames…")
            try:
                from components.video_renderer import generate_video

                # Save to a persistent temp file in the project dir
                out_dir = os.path.join(
                    os.path.dirname(__file__), "assets"
                )
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, "tracex_output.mp4")

                generate_video(
                    steps=steps,
                    source=code,
                    language=st.session_state.language,
                    mode=st.session_state.exec_mode,
                    error=error,
                    output_path=out_path,
                )
                st.session_state.video_path = out_path
                st.session_state.trace_error = error
                st.write(f"✅ Video rendered → `tracex_output.mp4`")
            except Exception as e:
                st.error(f"Video render failed: {e}")
                import traceback; st.code(traceback.format_exc())
                st.stop()

            status.update(label="✅ Done! Video ready.", state="complete")

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

        # Download button
        with open(st.session_state.video_path, "rb") as f:
            st.download_button(
                label="⬇️ Download MP4",
                data=f,
                file_name="tracex_visualization.mp4",
                mime="video/mp4",
                use_container_width=True,
            )

        if st.session_state.trace_error:
            with st.expander("💥 Error Details"):
                st.code(st.session_state.trace_error, language="python")


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
