"""
TraceX — Video Renderer
Converts tracer steps into a cinematic MP4 using matplotlib + imageio.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import imageio.v3 as iio
import tempfile, os

# ── Palette ──────────────────────────────────────────────────
BG          = "#0D0D1A"
BG2         = "#13132A"
BG3         = "#1A1A35"
PURPLE      = "#7C3AED"
VIOLET      = "#A78BFA"
CYAN        = "#06B6D4"
GREEN       = "#10B981"
AMBER       = "#F59E0B"
ROSE        = "#F43F5E"
TEXT        = "#E2E8F0"
TEXT2       = "#94A3B8"
TEXT3       = "#475569"
BORDER      = "#2D2B55"

FPS         = 4          # frames per second (slow enough to read)
HOLD_FRAMES = 2          # duplicate each step this many times


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))


def _fig_to_rgb(fig):
    """Render a matplotlib figure to an HxWx3 uint8 numpy array."""
    fig.canvas.draw()
    buf = fig.canvas.buffer_rgba()
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(
        fig.canvas.get_width_height()[::-1] + (4,)
    )
    return arr[:, :, :3]


def _render_frame(step: dict, source_lines: list[str], total_steps: int) -> np.ndarray:
    """Render a single execution step as an RGB frame."""
    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    gs  = GridSpec(
        3, 2,
        figure=fig,
        left=0.03, right=0.97,
        top=0.91,  bottom=0.08,
        hspace=0.35, wspace=0.06,
        height_ratios=[3, 2, 1],
    )

    ax_code  = fig.add_subplot(gs[:, 0])      # left – full height – code
    ax_vars  = fig.add_subplot(gs[0:2, 1])    # right top – variables
    ax_stack = fig.add_subplot(gs[2, 1])      # right bottom – call stack

    for ax in (ax_code, ax_vars, ax_stack):
        ax.set_facecolor(BG3)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
            spine.set_linewidth(1.2)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    # ─── Title bar ───────────────────────────────────────────
    progress = step["step"] / max(total_steps, 1)
    event_colors = {"call": VIOLET, "return": CYAN, "exception": ROSE, "line": GREEN}
    ev_color = event_colors.get(step["event"], GREEN)

    fig.text(0.03, 0.965, "🔍 TraceX", fontsize=16, fontweight="bold",
             color=VIOLET, va="center",
             fontfamily="DejaVu Sans")
    fig.text(0.5, 0.965, step["note"], fontsize=10, color=TEXT2,
             ha="center", va="center")
    fig.text(0.97, 0.965,
             f"Step {step['step']} / {total_steps}",
             fontsize=9, color=TEXT3, ha="right", va="center")

    # Progress bar
    bar_ax = fig.add_axes([0.03, 0.945, 0.94, 0.008])
    bar_ax.set_facecolor(BG2)
    bar_ax.set_xlim(0, 1); bar_ax.set_ylim(0, 1)
    bar_ax.axvspan(0, progress, ymin=0, ymax=1, color=PURPLE, alpha=0.85)
    bar_ax.axis("off")

    # ─── Code panel ──────────────────────────────────────────
    ax_code.set_title("  Source Code", loc="left", fontsize=9,
                      color=TEXT3, pad=6, fontweight="bold")
    ax_code.set_xlim(0, 1)

    visible_start = max(0, step["line_no"] - 10)
    visible_lines = source_lines[visible_start: visible_start + 22]
    n = len(visible_lines)
    ax_code.set_ylim(-0.5, n - 0.5)

    for i, text in enumerate(visible_lines):
        abs_ln = visible_start + i + 1
        is_current = (abs_ln == step["line_no"])

        if is_current:
            ax_code.axhspan(n - 1 - i - 0.45, n - 1 - i + 0.45,
                            color=ev_color, alpha=0.18)
            ax_code.plot([0, 0.012], [n - 1 - i, n - 1 - i],
                         color=ev_color, lw=3, solid_capstyle="round")

        # Line number
        ax_code.text(0.018, n - 1 - i, f"{abs_ln:>3}",
                     fontsize=7.5, color=TEXT3 if not is_current else ev_color,
                     va="center", fontfamily="monospace")
        # Code text
        ax_code.text(0.065, n - 1 - i,
                     text[:72] if len(text) > 72 else text,
                     fontsize=8,
                     color=TEXT if is_current else TEXT2,
                     va="center",
                     fontfamily="monospace",
                     fontweight="bold" if is_current else "normal")

    # ─── Variables panel ─────────────────────────────────────
    ax_vars.set_title("  Variables", loc="left", fontsize=9,
                      color=TEXT3, pad=6, fontweight="bold")
    ax_vars.set_xlim(0, 1)

    variables = step.get("variables", {})
    items = list(variables.items())
    n_vars = len(items)
    ax_vars.set_ylim(-0.5, max(n_vars, 1) - 0.5)

    if not items:
        ax_vars.text(0.5, 0.5, "No variables yet",
                     ha="center", va="center", color=TEXT3,
                     fontsize=9, transform=ax_vars.transAxes)
    else:
        for i, (k, v) in enumerate(items[:12]):
            row = n_vars - 1 - i
            # Key box
            rect = mpatches.FancyBboxPatch(
                (0.01, row - 0.35), 0.3, 0.7,
                boxstyle="round,pad=0.02",
                facecolor=BG2, edgecolor=PURPLE, linewidth=0.8
            )
            ax_vars.add_patch(rect)
            ax_vars.text(0.16, row, k, ha="center", va="center",
                         color=VIOLET, fontsize=8.5,
                         fontfamily="monospace", fontweight="bold")
            # Value box
            rect2 = mpatches.FancyBboxPatch(
                (0.33, row - 0.35), 0.65, 0.7,
                boxstyle="round,pad=0.02",
                facecolor="#0A1628", edgecolor=BORDER, linewidth=0.8
            )
            ax_vars.add_patch(rect2)
            ax_vars.text(0.655, row,
                         v[:40] if len(v) > 40 else v,
                         ha="center", va="center",
                         color=CYAN, fontsize=8,
                         fontfamily="monospace")

    # ─── Stdout strip (below variables) ──────────────────────
    stdout_text = step.get("stdout", "").strip()
    if stdout_text:
        last_lines = stdout_text.split("\n")[-3:]
        preview = " │ ".join(last_lines)
        ax_vars.text(0.5, -0.48,
                     f"stdout ▸  {preview[:80]}",
                     ha="center", va="center",
                     color=GREEN, fontsize=7.5,
                     fontfamily="monospace",
                     transform=ax_vars.transAxes,
                     clip_on=False)

    # ─── Call Stack panel ─────────────────────────────────────
    ax_stack.set_title("  Call Stack", loc="left", fontsize=9,
                       color=TEXT3, pad=6, fontweight="bold")
    ax_stack.set_xlim(0, 1)

    stack = step.get("call_stack", [])
    if not stack:
        stack = [{"name": "<module>", "line": step["line_no"], "file": "<module>"}]

    ax_stack.set_ylim(-0.5, len(stack) - 0.5)
    for i, frame in enumerate(stack):
        col = VIOLET if i == len(stack) - 1 else TEXT2
        label = f"{'→ ' if i == len(stack)-1 else '  '}{frame['name']}()  line {frame['line']}"
        ax_stack.text(0.03, i, label,
                      va="center", color=col, fontsize=8.5,
                      fontfamily="monospace",
                      fontweight="bold" if i == len(stack) - 1 else "normal")

    frame_rgb = _fig_to_rgb(fig)
    plt.close(fig)
    return frame_rgb


def _render_title_frame(language: str, mode: str, total_steps: int) -> np.ndarray:
    """Splash / intro frame."""
    fig, ax = plt.subplots(figsize=(16, 9.12), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.62, "TraceX",
            ha="center", va="center", fontsize=52,
            fontweight="bold", color=VIOLET)
    ax.text(0.5, 0.47, "Code Execution Visualizer",
            ha="center", va="center", fontsize=18, color=TEXT2)
    ax.text(0.5, 0.37,
            f"{language}  |  {mode} Mode  |  {total_steps} Steps",
            ha="center", va="center", fontsize=13, color=TEXT3)

    # Decorative line
    ax.plot([0.25, 0.75], [0.42, 0.42], color=PURPLE, lw=1.5, alpha=0.5)

    frame_rgb = _fig_to_rgb(fig)
    plt.close(fig)
    return frame_rgb


def _render_end_frame(stdout_final: str, error: str | None) -> np.ndarray:
    """End / summary frame."""
    fig, ax = plt.subplots(figsize=(16, 9.12), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.axis("off")

    if error:
        ax.text(0.5, 0.65, "Runtime Error", ha="center",
                fontsize=26, color=ROSE, fontweight="bold")
        lines = error.strip().splitlines()[-6:]
        for i, ln in enumerate(lines):
            ax.text(0.5, 0.52 - i * 0.07, ln.strip()[:90],
                    ha="center", fontsize=9, color=TEXT2,
                    fontfamily="monospace")
    else:
        ax.text(0.5, 0.65, "Execution Complete", ha="center",
                fontsize=26, color=GREEN, fontweight="bold")
        if stdout_final.strip():
            ax.text(0.5, 0.55, "Program Output:", ha="center",
                    fontsize=11, color=TEXT3)
            out_lines = stdout_final.strip().splitlines()[-8:]
            for i, ln in enumerate(out_lines):
                ax.text(0.5, 0.48 - i * 0.065, ln[:90],
                        ha="center", fontsize=10, color=CYAN,
                        fontfamily="monospace")
        else:
            ax.text(0.5, 0.50, "(No stdout output)", ha="center",
                    fontsize=11, color=TEXT3)

    ax.text(0.5, 0.12, "TraceX  |  Code Execution Visualizer",
            ha="center", fontsize=9, color=TEXT3)

    frame_rgb = _fig_to_rgb(fig)
    plt.close(fig)
    return frame_rgb


def _render_syntax_error_frame(
    source_lines: list[str],
    error_line: int,
    error_msg: str,
    language: str,
    frame_idx: int,
    total_frames: int,
) -> np.ndarray:
    """One frame of the syntax-error video — pulsing red highlight on bad line."""
    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    gs  = GridSpec(2, 2, figure=fig,
                   left=0.03, right=0.97, top=0.91, bottom=0.08,
                   hspace=0.25, wspace=0.06, height_ratios=[2.5, 1])
    ax_code = fig.add_subplot(gs[:, 0])
    ax_err  = fig.add_subplot(gs[0, 1])
    ax_hint = fig.add_subplot(gs[1, 1])

    for ax in (ax_code, ax_err, ax_hint):
        ax.set_facecolor(BG3)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER); sp.set_linewidth(1.2)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    # Title bar
    fig.text(0.03, 0.965, "TraceX", fontsize=16, fontweight="bold", color=VIOLET, va="center")
    fig.text(0.5,  0.965, f"Syntax Error  |  {language}",
             fontsize=10, color=ROSE, ha="center", va="center", fontweight="bold")
    fig.text(0.97, 0.965, f"Frame {frame_idx}/{total_frames}",
             fontsize=9, color=TEXT3, ha="right", va="center")

    # Animated red progress bar
    bar_ax = fig.add_axes([0.03, 0.945, 0.94, 0.008])
    bar_ax.set_facecolor(BG2); bar_ax.set_xlim(0, 1); bar_ax.set_ylim(0, 1)
    bar_ax.axvspan(0, frame_idx / max(total_frames, 1), ymin=0, ymax=1, color=ROSE, alpha=0.85)
    bar_ax.axis("off")

    # Code panel
    ax_code.set_title("  Source Code", loc="left", fontsize=9,
                      color=TEXT3, pad=6, fontweight="bold")
    ax_code.set_xlim(0, 1)
    err_ln = max(error_line, 1)
    visible_start = max(0, err_ln - 10)
    visible_lines = source_lines[visible_start: visible_start + 22]
    n = len(visible_lines)
    ax_code.set_ylim(-0.5, max(n - 0.5, 0.5))

    for i, text in enumerate(visible_lines):
        abs_ln = visible_start + i + 1
        is_err = (abs_ln == err_ln)
        if is_err:
            # Pulsing alpha
            alpha = 0.18 + 0.12 * abs((frame_idx % 8) - 4) / 4
            ax_code.axhspan(n-1-i - 0.48, n-1-i + 0.48, color=ROSE, alpha=alpha)
            ax_code.plot([0, 0.015], [n-1-i, n-1-i], color=ROSE, lw=4, solid_capstyle="round")

        ax_code.text(0.018, n-1-i, f"{abs_ln:>3}", fontsize=7.5,
                     color=ROSE if is_err else TEXT3, va="center",
                     fontfamily="monospace", fontweight="bold" if is_err else "normal")
        ax_code.text(0.065, n-1-i, text[:72], fontsize=8,
                     color=ROSE if is_err else TEXT2, va="center",
                     fontfamily="monospace", fontweight="bold" if is_err else "normal")

    # Error message panel
    ax_err.set_title("  Syntax Error", loc="left", fontsize=9, color=ROSE, pad=6, fontweight="bold")
    ax_err.axis("off")
    ax_err.axhspan(0.35, 0.90, xmin=0.03, xmax=0.97, color=ROSE, alpha=0.08)
    ax_err.plot([0.03, 0.97], [0.90, 0.90], color=ROSE, lw=1.2, transform=ax_err.transAxes)
    ax_err.plot([0.03, 0.97], [0.35, 0.35], color=ROSE, lw=1.2, transform=ax_err.transAxes)
    ax_err.text(0.5, 0.80,
                f"Line {err_ln}" if err_ln > 0 else "Unknown line",
                ha="center", va="center", fontsize=22, color=ROSE,
                fontweight="bold", transform=ax_err.transAxes)
    ax_err.text(0.5, 0.60,
                error_msg[:65] if len(error_msg) > 65 else error_msg,
                ha="center", va="center", fontsize=10, color=TEXT,
                fontfamily="monospace", transform=ax_err.transAxes)
    if len(error_msg) > 65:
        ax_err.text(0.5, 0.46, error_msg[65:130],
                    ha="center", va="center", fontsize=9, color=TEXT2,
                    fontfamily="monospace", transform=ax_err.transAxes)
    ax_err.text(0.5, 0.18, "Execution stopped  |  Fix the error and try again",
                ha="center", va="center", fontsize=8.5, color=AMBER,
                transform=ax_err.transAxes)

    # Common fixes hint panel
    ax_hint.set_title("  Quick Fixes", loc="left", fontsize=9, color=TEXT3, pad=6, fontweight="bold")
    ax_hint.axis("off")
    for i, hint in enumerate([
        "Check for missing colons  ( if x:  /  for i in ...: )",
        "Check matching brackets  [ ] { } ( )",
        "Check indentation — Python is whitespace-sensitive",
        "Check for missing quotes around strings",
    ]):
        ax_hint.text(0.04, 0.78 - i * 0.22, f"• {hint}",
                     fontsize=8, color=TEXT2, fontfamily="monospace",
                     transform=ax_hint.transAxes, va="center")

    frame_rgb = _fig_to_rgb(fig)
    plt.close(fig)
    return frame_rgb


def generate_syntax_error_video(
    source: str,
    language: str,
    error_line: int,
    error_msg: str,
    output_path: str | None = None,
) -> str:
    """
    Generate a 6-second MP4 showing the syntax error with animated
    pulsing red highlight on the offending line.
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = tmp.name
        tmp.close()

    source_lines   = source.splitlines()
    total_frames   = FPS * 6    # 6 seconds

    all_frames = [
        _render_syntax_error_frame(
            source_lines, error_line, error_msg, language, idx, total_frames
        )
        for idx in range(1, total_frames + 1)
    ]

    iio.imwrite(output_path, all_frames, fps=FPS,
                codec="libx264", quality=8, macro_block_size=16)
    return output_path


def generate_video(
    steps: list[dict],
    source: str,
    language: str,
    mode: str,
    error: str | None = None,
    output_path: str | None = None,
) -> str:
    """
    Compile all steps into an MP4 video.

    Parameters
    ----------
    steps        : list of step dicts from tracer
    source       : original source code string
    language     : e.g. "Python"
    mode         : "Full Program" | "LeetCode"
    error        : error string if execution failed
    output_path  : where to save the MP4 (auto-generates temp file if None)

    Returns
    -------
    str : absolute path to the generated MP4 file
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = tmp.name
        tmp.close()

    source_lines = source.splitlines()
    total_steps  = len(steps)
    final_stdout = steps[-1]["stdout"] if steps else ""

    all_frames: list[np.ndarray] = []

    # Intro (hold 3 seconds = 3 × FPS frames)
    title = _render_title_frame(language, mode, total_steps)
    all_frames.extend([title] * (FPS * 3))

    # Step frames
    for step in steps:
        frame = _render_frame(step, source_lines, total_steps)
        all_frames.extend([frame] * HOLD_FRAMES)

    # End frame (hold 4 seconds)
    end_frame = _render_end_frame(final_stdout, error)
    all_frames.extend([end_frame] * (FPS * 4))

    # Write MP4
    iio.imwrite(
        output_path,
        all_frames,
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=16,
    )

    return output_path
