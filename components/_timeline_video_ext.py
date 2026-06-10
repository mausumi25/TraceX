"""
TraceX — Timeline-Driven Video Generator
=========================================
Appended to video_renderer.py.
Generates animated frames from the rich timeline events produced by
timeline_generator.py.  Each event type gets a dedicated visual card.

Event → visual treatment
  line_execute       → standard code frame (1 s)
  variable_set       → code frame + green glow on new var (1 s)
  variable_change    → code frame + orange glow on changed var (1 s)
  array_append/update→ array animation card (1.5 s)
  matrix_cell_update → matrix animation card (1.5 s)
  loop_start         → big LOOP START splash (2 s)
  loop_iteration     → iteration counter splash (1.5 s)
  loop_end           → LOOP COMPLETE splash (1 s)
  condition_check    → condition + TRUE/FALSE result (2 s)
  function_call      → CALLING func(args) card (1.5 s)
  function_return    → RETURNED value card (1.5 s)
  output             → stdout output card (1.5 s)
  final_output       → end frame (4 s)
"""

from __future__ import annotations
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import imageio.v3 as iio
import tempfile

# Re-use constants from video_renderer.py (already imported in same namespace)
# BG, BG2, BG3, PURPLE, VIOLET, CYAN, GREEN, AMBER, ROSE, TEXT, TEXT2, TEXT3,
# BORDER, CHANGED, FPS, _fig_to_rgb, _ensure_912, _render_title_frame,
# _render_end_frame, _draw_structures, _norm

# ── Event seconds per type ─────────────────────────────────────────
_EV_SECS = {
    "line_execute"       : 1.0,
    "variable_set"       : 0.5,
    "variable_change"    : 0.5,
    "array_update"       : 1.5,
    "array_append"       : 1.5,
    "array_pop"          : 1.0,
    "matrix_cell_update" : 1.5,
    "loop_start"         : 2.0,
    "loop_iteration"     : 1.5,
    "loop_end"           : 1.0,
    "condition_check"    : 2.0,
    "function_call"      : 1.5,
    "function_return"    : 1.5,
    "output"             : 1.5,
    "final_output"       : 0.0,   # handled separately
}

_EV_COLORS = {
    "line_execute"       : "#06B6D4",   # cyan
    "variable_set"       : "#10B981",   # green
    "variable_change"    : "#F97316",   # orange
    "array_update"       : "#60A5FA",   # blue
    "array_append"       : "#38BDF8",   # sky
    "array_pop"          : "#93C5FD",   # light blue
    "matrix_cell_update" : "#FBBF24",   # amber
    "loop_start"         : "#A78BFA",   # violet
    "loop_iteration"     : "#C4B5FD",   # lavender
    "loop_end"           : "#7C3AED",   # deep violet
    "condition_check"    : "#F59E0B",   # amber
    "function_call"      : "#818CF8",   # indigo
    "function_return"    : "#6EE7B7",   # emerald
    "output"             : "#86EFAC",   # light green
}


def _norm_frame(frame: np.ndarray) -> np.ndarray:
    """Force frame to exactly 1600 W × 912 H × 3 channels."""
    h, w = frame.shape[:2]
    if h < 912:
        frame = np.vstack([frame, np.zeros((912 - h, w, 3), dtype=np.uint8)])
    elif h > 912:
        frame = frame[:912]
    h, w = frame.shape[:2]
    if w < 1600:
        frame = np.hstack([frame, np.zeros((h, 1600 - w, 3), dtype=np.uint8)])
    elif w > 1600:
        frame = frame[:, :1600]
    return frame.astype(np.uint8)


def _base_figure():
    """Create the standard 16×9.12 canvas."""
    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    _ensure_912(fig)
    return fig


def _panel(ax, title="", accent=BORDER):
    ax.set_facecolor(BG3)
    for sp in ax.spines.values():
        sp.set_edgecolor(accent)
        sp.set_linewidth(1.6)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    if title:
        ax.set_title(f"  {title}", loc="left", fontsize=9,
                     color=TEXT3, pad=5, fontweight="bold")


def _title_bar(fig, ev_type: str, ev_label: str, seq: int, total: int,
               ev_color: str, note: str = ""):
    """Draw the top title / progress bar shared by all frames."""
    fig.text(0.03, 0.968, "TraceX", fontsize=15, fontweight="bold",
             color=VIOLET, va="center", fontfamily="DejaVu Sans")
    fig.text(0.14, 0.968, f"  {ev_label}  ", fontsize=8, fontweight="bold",
             color=BG, va="center", ha="left",
             bbox=dict(boxstyle="round,pad=0.3", facecolor=ev_color, edgecolor="none"))
    if note:
        fig.text(0.5, 0.968, note[:72], fontsize=9, color=TEXT2,
                 ha="center", va="center", style="italic")
    fig.text(0.97, 0.968, f"Event  {seq} / {total}",
             fontsize=9, color=TEXT3, ha="right", va="center", fontweight="bold")
    progress = seq / max(total, 1)
    bar = fig.add_axes([0.03, 0.948, 0.94, 0.009])
    bar.set_facecolor(BG2); bar.set_xlim(0, 1); bar.set_ylim(0, 1)
    bar.axvspan(0, progress, color=ev_color, alpha=0.9)
    bar.axis("off")


def _code_panel(ax, source_lines: list, cur_line: int, ev_color: str):
    """Draw the source code panel with the current line highlighted."""
    ax.set_xlim(0, 1)
    n_src = len(source_lines)
    vis_start = max(0, cur_line - 9)
    vis_lines = source_lines[vis_start: vis_start + 22]
    n = len(vis_lines)
    ax.set_ylim(-0.5, max(n - 0.5, 0.5))
    _panel(ax, "Source Code", ev_color)

    for i, text in enumerate(vis_lines):
        abs_ln     = vis_start + i + 1
        is_cur     = (abs_ln == cur_line)
        row_y      = n - 1 - i

        if is_cur:
            ax.axhspan(row_y - 0.48, row_y + 0.48, color=ev_color, alpha=0.22, zorder=0)
            ax.plot([0, 0.007], [row_y, row_y], color=ev_color, lw=5,
                    solid_capstyle="butt", zorder=3)
            ax.text(0.010, row_y, "▶", fontsize=9, color=ev_color, va="center", zorder=4)

        ax.text(0.022, row_y, f"{abs_ln:>3}",
                fontsize=7.5, va="center", fontfamily="monospace",
                color=ev_color if is_cur else TEXT3,
                fontweight="bold" if is_cur else "normal")
        ax.text(0.068, row_y,
                text[:70] if len(text) > 70 else text,
                fontsize=8.0,
                color=TEXT if is_cur else TEXT2,
                va="center", fontfamily="monospace",
                fontweight="bold" if is_cur else "normal")


def _vars_panel(ax, cum_vars: dict, changed_keys: set, ev_color: str,
                cum_stdout: str = ""):
    """Draw variables panel with change highlights."""
    _panel(ax, "Variables", ev_color)
    ax.set_xlim(0, 1)

    display = {k: v for k, v in cum_vars.items()
               if k not in ("_",) and not k.startswith("__")}
    items  = list(display.items())
    n_vars = len(items)
    ax.set_ylim(-0.5, max(n_vars - 0.5, 0.5))

    if not items:
        ax.text(0.5, 0.5, "No variables yet", ha="center", va="center",
                color=TEXT3, fontsize=9, transform=ax.transAxes)
    else:
        for i, (k, v) in enumerate(items[:10]):
            row     = n_vars - 1 - i
            changed = k in changed_keys
            kc      = CHANGED if changed else VIOLET
            vc      = CHANGED if changed else CYAN
            bord    = CHANGED if changed else PURPLE

            r1 = mpatches.FancyBboxPatch((0.01, row - 0.38), 0.26, 0.76,
                 boxstyle="round,pad=0.02", facecolor=BG2, edgecolor=bord,
                 linewidth=1.4 if changed else 0.8)
            ax.add_patch(r1)
            ax.text(0.14, row, k, ha="center", va="center", color=kc,
                    fontsize=7.5, fontfamily="monospace", fontweight="bold")

            r2 = mpatches.FancyBboxPatch((0.29, row - 0.38), 0.69, 0.76,
                 boxstyle="round,pad=0.02",
                 facecolor="#1A0A00" if changed else "#0A1628",
                 edgecolor=bord, linewidth=1.4 if changed else 0.8)
            ax.add_patch(r2)
            ax.text(0.635, row, v[:34] if len(v) > 34 else v,
                    ha="center", va="center", color=vc,
                    fontsize=7.0, fontfamily="monospace",
                    fontweight="bold" if changed else "normal")

            if changed:
                ax.text(0.965, row, "★", ha="center", va="center",
                        color=CHANGED, fontsize=9)

    if cum_stdout:
        lines  = cum_stdout.strip().split("\n")
        preview = "  ▸  ".join(lines[-3:])
        ax.text(0.5, -0.65, f"stdout: {preview[:70]}",
                ha="center", va="center", color=GREEN,
                fontsize=7.0, fontfamily="monospace", fontweight="bold",
                transform=ax.transAxes, clip_on=False)


# ── Event Card Renderers ───────────────────────────────────────────────────

def _card_condition(ax, ev: dict, ev_color: str):
    """Render a big condition-check card."""
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    result  = ev.get("result")
    expr    = ev.get("expression", "?")
    res_txt = "✅  TRUE" if result else "❌  FALSE"
    res_col = GREEN if result else ROSE

    # Header
    ax.text(0.5, 0.92, "CONDITION CHECK", ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold",
            fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    # Expression box
    ax.fill_between([0.05, 0.95], [0.6], [0.78], color=BG3, zorder=0)
    ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.58), 0.90, 0.22,
                 boxstyle="round,pad=0.02", facecolor=BG3,
                 edgecolor=ev_color, linewidth=1.2))
    ax.text(0.5, 0.69, f"if  {expr[:50]}", ha="center", va="center",
            fontsize=12, color=TEXT, fontfamily="monospace", fontweight="bold")

    # Result
    ax.add_patch(mpatches.FancyBboxPatch((0.15, 0.28), 0.70, 0.22,
                 boxstyle="round,pad=0.02",
                 facecolor="#052e16" if result else "#450a0a",
                 edgecolor=res_col, linewidth=2.0))
    ax.text(0.5, 0.39, res_txt, ha="center", va="center",
            fontsize=18, color=res_col, fontweight="bold", fontfamily="monospace")

    # Line number
    ax.text(0.5, 0.10, f"line {ev.get('line','')}", ha="center", va="center",
            fontsize=8, color=TEXT3, fontfamily="monospace")


def _card_loop(ax, ev: dict, ev_color: str):
    """Render a loop event card (start / iteration / end)."""
    ev_type = ev.get("event")
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    if ev_type == "loop_start":
        header = "🔄  LOOP START"
        body1  = f"for  {ev.get('loop_var','?')}"
        body2  = f"in  {ev.get('iterable', ev.get('condition','?'))[:40]}"
        body3  = ""
    elif ev_type == "loop_iteration":
        n      = ev.get("iteration", "?")
        header = f"🔄  ITERATION  #{n}"
        body1  = f"{ev.get('loop_var','?')}"
        body2  = "="
        body3  = str(ev.get("value", ev.get("result", "?")))[:30]
    else:  # loop_end
        header = "🔄  LOOP COMPLETE"
        body1  = f"{ev.get('iterations', '?')} iterations"
        body2  = ""
        body3  = ""

    ax.text(0.5, 0.88, header, ha="center", va="center",
            fontsize=12, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    if body1:
        ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.52), 0.90, 0.26,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.65, body1, ha="center", va="center",
                fontsize=13, color=TEXT, fontfamily="monospace", fontweight="bold")

    if body2 and ev_type == "loop_iteration":
        ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.22), 0.90, 0.26,
                     boxstyle="round,pad=0.02",
                     facecolor="#130533", edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.35, f"{body1}  =  {body3}", ha="center", va="center",
                fontsize=14, color="#C4B5FD", fontfamily="monospace", fontweight="bold")
    elif body2:
        ax.text(0.5, 0.35, body2, ha="center", va="center",
                fontsize=11, color=TEXT2, fontfamily="monospace")

    ax.text(0.5, 0.08, f"line {ev.get('line','')}", ha="center", va="center",
            fontsize=8, color=TEXT3, fontfamily="monospace")


def _card_function(ax, ev: dict, ev_color: str):
    """Render a function call or return card."""
    ev_type = ev.get("event")
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    func = ev.get("function", "?")

    if ev_type == "function_call":
        header = "📞  FUNCTION CALL"
        args   = ev.get("arguments", {})
        args_s = ", ".join(f"{k}={v}" for k, v in args.items())[:60]
        body   = f"{func}({args_s})"
        col    = "#818CF8"
    else:
        header = "↩️  RETURN"
        body   = f"{func}()  →  {ev.get('value','?')[:50]}"
        col    = "#6EE7B7"

    ax.text(0.5, 0.88, header, ha="center", va="center",
            fontsize=11, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.42), 0.92, 0.32,
                 boxstyle="round,pad=0.02", facecolor=BG3,
                 edgecolor=ev_color, linewidth=1.2))
    ax.text(0.5, 0.58, body[:55], ha="center", va="center",
            fontsize=11, color=col, fontfamily="monospace", fontweight="bold",
            wrap=True)

    ax.text(0.5, 0.22, f"line {ev.get('line','')}", ha="center", va="center",
            fontsize=8, color=TEXT3, fontfamily="monospace")


def _card_array(ax, ev: dict, ev_color: str, cum_vars: dict):
    """Render an array mutation card."""
    ev_type = ev.get("event")
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    var  = ev.get("var", "?")
    headers = {
        "array_update": f"🔵  ARRAY UPDATE  ·  {var}",
        "array_append": f"🔵  ARRAY APPEND  ·  {var}",
        "array_pop"   : f"🔵  ARRAY POP     ·  {var}",
    }
    ax.text(0.5, 0.88, headers.get(ev_type, "ARRAY OP"),
            ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    # Show the current array from cum_vars
    raw_val = cum_vars.get(var, "")
    try:
        import ast as _ast
        arr = _ast.literal_eval(raw_val)
        if not isinstance(arr, list):
            arr = []
    except Exception:
        arr = []

    # Draw boxes for each element
    n    = len(arr)
    if 0 < n <= 20:
        box_w  = min(0.88 / n, 0.1)
        start_x = (1 - n * box_w) / 2
        hi_idx  = ev.get("index", -1)

        for idx, val in enumerate(arr):
            x     = start_x + idx * box_w
            is_hi = (idx == hi_idx)
            color = ev_color if is_hi else CYAN
            bg_c  = "#082f49" if not is_hi else "#1c3d5a"

            ax.add_patch(mpatches.FancyBboxPatch(
                (x + 0.005, 0.47), box_w - 0.012, 0.22,
                boxstyle="round,pad=0.01",
                facecolor=bg_c, edgecolor=color, linewidth=2.0 if is_hi else 0.8))
            ax.text(x + box_w / 2, 0.58, str(val)[:6],
                    ha="center", va="center", fontsize=9,
                    color=color, fontfamily="monospace",
                    fontweight="bold" if is_hi else "normal")
            ax.text(x + box_w / 2, 0.45, str(idx),
                    ha="center", va="center", fontsize=7, color=TEXT3)

    # Change description
    if ev_type == "array_update":
        desc = f"[{ev.get('index')}]  {ev.get('old_value')}  →  {ev.get('new_value')}"
    elif ev_type == "array_append":
        desc = f"append({ev.get('value')})  →  len={ev.get('new_len')}"
    else:
        desc = f"pop()  len {ev.get('old_len')} → {ev.get('new_len')}"

    ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.16), 0.90, 0.20,
                 boxstyle="round,pad=0.02", facecolor=BG3,
                 edgecolor=ev_color, linewidth=1))
    ax.text(0.5, 0.26, desc, ha="center", va="center",
            fontsize=11, color=ev_color, fontfamily="monospace", fontweight="bold")


def _card_matrix(ax, ev: dict, ev_color: str, cum_vars: dict):
    """Render a matrix cell update card."""
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    var   = ev.get("var", "?")
    row_i = ev.get("row", 0)
    col_i = ev.get("col", 0)

    ax.text(0.5, 0.88, f"🟡  MATRIX UPDATE  ·  {var}",
            ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    # Try to draw the matrix
    raw_val = cum_vars.get(var, "")
    try:
        import ast as _ast
        mat = _ast.literal_eval(raw_val)
        if isinstance(mat, list) and mat and isinstance(mat[0], list):
            rows = len(mat); cols = len(mat[0])
            cell_h = min(0.48 / rows, 0.14)
            cell_w = min(0.80 / cols, 0.14)
            ox = (1 - cols * cell_w) / 2
            oy = 0.27

            for r in range(rows):
                for c in range(cols):
                    x    = ox + c * cell_w
                    y    = oy + (rows - 1 - r) * cell_h
                    is_h = (r == row_i and c == col_i)
                    ax.add_patch(mpatches.FancyBboxPatch(
                        (x + 0.005, y + 0.005), cell_w - 0.010, cell_h - 0.010,
                        boxstyle="round,pad=0.01",
                        facecolor="#1c3d5a" if is_h else BG3,
                        edgecolor=ev_color if is_h else BORDER,
                        linewidth=2.0 if is_h else 0.6))
                    ax.text(x + cell_w / 2, y + cell_h / 2, str(mat[r][c])[:4],
                            ha="center", va="center",
                            fontsize=8, color=ev_color if is_h else TEXT2,
                            fontfamily="monospace",
                            fontweight="bold" if is_h else "normal")
    except Exception:
        pass

    # Change description
    desc = f"[{row_i}][{col_i}]  {ev.get('old_value')}  →  {ev.get('new_value')}"
    ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.08), 0.90, 0.16,
                 boxstyle="round,pad=0.02", facecolor=BG3,
                 edgecolor=ev_color, linewidth=1))
    ax.text(0.5, 0.16, desc, ha="center", va="center",
            fontsize=11, color=ev_color, fontfamily="monospace", fontweight="bold")


def _card_output(ax, ev: dict, ev_color: str, cum_stdout: str):
    """Render an output / print card."""
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    ax.text(0.5, 0.88, "🖨️  PROGRAM OUTPUT",
            ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    # Show the new line
    new_line = ev.get("text", "")
    ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.50), 0.92, 0.26,
                 boxstyle="round,pad=0.02", facecolor="#052e16",
                 edgecolor=ev_color, linewidth=1.5))
    ax.text(0.5, 0.63, f">>> {new_line[:55]}", ha="center", va="center",
            fontsize=13, color=GREEN, fontfamily="monospace", fontweight="bold")

    # Show full stdout so far
    lines = cum_stdout.strip().split("\n") if cum_stdout else []
    if lines:
        all_out = "  ·  ".join(lines[-4:])
        ax.text(0.5, 0.30, f"stdout: {all_out[:65]}", ha="center", va="center",
                fontsize=9, color=TEXT2, fontfamily="monospace",
                transform=ax.transAxes, clip_on=False)


def _card_var_change(ax, ev: dict, ev_color: str):
    """Render a variable set / change card."""
    ev_type = ev.get("event")
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    name = ev.get("name", "?")
    val  = ev.get("value", ev.get("new_value", "?"))
    old  = ev.get("old_value", "")

    if ev_type == "variable_set":
        header = "🟢  VARIABLE SET"
        body   = f"{name}  =  {val[:40]}"
        col    = GREEN
    else:
        header = "🟠  VARIABLE CHANGED"
        body   = f"{name}:  {old[:25]}  →  {val[:25]}"
        col    = CHANGED

    ax.text(0.5, 0.85, header, ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))

    ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.42), 0.90, 0.28,
                 boxstyle="round,pad=0.02", facecolor=BG3,
                 edgecolor=ev_color, linewidth=1.5))
    ax.text(0.5, 0.56, body, ha="center", va="center",
            fontsize=13, color=col, fontfamily="monospace", fontweight="bold")

    ax.text(0.5, 0.22, f"type: {ev.get('type','?')}",
            ha="center", va="center", fontsize=9, color=TEXT3, fontfamily="monospace")


# ── Main frame builder ─────────────────────────────────────────────────────

def _build_timeline_frame(
    ev: dict,
    source_lines: list,
    total_evs: int,
    cum_vars: dict,
    cum_structs: list,
    cum_stdout: str,
    cur_line: int,
    changed_keys: set,
) -> np.ndarray:
    """
    Render one frame for a timeline event.
    Layout: left=code panel, right=event card.
    For line_execute, right shows vars+structs like the classic layout.
    """
    ev_type  = ev.get("event", "line_execute")
    ev_color = _EV_COLORS.get(ev_type, CYAN)
    seq      = ev.get("seq", 0)

    EV_LABELS = {
        "line_execute"      : "LINE",
        "variable_set"      : "SET",
        "variable_change"   : "CHANGED",
        "array_update"      : "ARRAY",
        "array_append"      : "APPEND",
        "array_pop"         : "POP",
        "matrix_cell_update": "MATRIX",
        "loop_start"        : "LOOP START",
        "loop_iteration"    : "LOOP ITER",
        "loop_end"          : "LOOP END",
        "condition_check"   : "CONDITION",
        "function_call"     : "CALL",
        "function_return"   : "RETURN",
        "output"            : "OUTPUT",
    }
    ev_label = EV_LABELS.get(ev_type, ev_type.upper())

    # ── Figure + grid ─────────────────────────────────────────
    fig = _base_figure()

    is_line_ev = ev_type in ("line_execute",)

    if is_line_ev:
        # Classic 4-panel layout for regular line events
        gs = GridSpec(4, 2, figure=fig,
                      left=0.03, right=0.97, top=0.92, bottom=0.05,
                      hspace=0.42, wspace=0.06,
                      height_ratios=[2.5, 1.6, 1.6, 0.8])
        ax_code   = fig.add_subplot(gs[:, 0])
        ax_vars   = fig.add_subplot(gs[0, 1])
        ax_struct = fig.add_subplot(gs[1:3, 1])
        ax_stack  = fig.add_subplot(gs[3, 1])

        _code_panel(ax_code, source_lines, cur_line, ev_color)
        _vars_panel(ax_vars, cum_vars, changed_keys, ev_color, cum_stdout)

        # Structures
        _panel(ax_struct, "Data Structures", BORDER)
        ax_struct.set_xlim(0, 1); ax_struct.set_ylim(0, 1); ax_struct.axis("off")
        interesting = [s for s in cum_structs
                       if s.get("kind") not in ("Primitive", "Unknown", "String")]
        if interesting:
            _draw_structures(ax_struct, interesting[:3])
        else:
            ax_struct.text(0.5, 0.5, "No structures yet",
                           ha="center", va="center", color=TEXT3,
                           fontsize=9, transform=ax_struct.transAxes)

        # Call stack
        _panel(ax_stack, "Call Stack", BORDER)
        ax_stack.set_xlim(0, 1)
        ax_stack.set_ylim(-0.5, 0.5)
        ax_stack.text(0.03, 0, f"▶  <module>()  — line {cur_line}",
                      va="center", color=ev_color,
                      fontsize=8.5, fontfamily="monospace", fontweight="bold")

    else:
        # 2-panel layout: left=code, right=event card
        gs = GridSpec(1, 2, figure=fig,
                      left=0.03, right=0.97, top=0.92, bottom=0.05,
                      wspace=0.05,
                      width_ratios=[1.15, 0.85])
        ax_code  = fig.add_subplot(gs[0])
        ax_event = fig.add_subplot(gs[1])

        _code_panel(ax_code, source_lines, cur_line, ev_color)

        # Draw the right-side event card
        if ev_type == "condition_check":
            _card_condition(ax_event, ev, ev_color)
        elif ev_type in ("loop_start", "loop_iteration", "loop_end"):
            _card_loop(ax_event, ev, ev_color)
        elif ev_type in ("function_call", "function_return"):
            _card_function(ax_event, ev, ev_color)
        elif ev_type in ("array_update", "array_append", "array_pop"):
            _card_array(ax_event, ev, ev_color, cum_vars)
        elif ev_type == "matrix_cell_update":
            _card_matrix(ax_event, ev, ev_color, cum_vars)
        elif ev_type == "output":
            _card_output(ax_event, ev, ev_color, cum_stdout)
        elif ev_type in ("variable_set", "variable_change"):
            _card_var_change(ax_event, ev, ev_color)
        else:
            # Generic card
            ax_event.set_facecolor(BG2)
            ax_event.set_xlim(0, 1); ax_event.set_ylim(0, 1)
            ax_event.tick_params(left=False, bottom=False,
                                 labelleft=False, labelbottom=False)
            ax_event.text(0.5, 0.5, ev_type.replace("_", "\n"),
                          ha="center", va="center", fontsize=14,
                          color=ev_color, fontfamily="monospace", fontweight="bold")

    # Title bar on top
    note = ev.get("code", ev.get("expression", ev.get("text", "")))
    _title_bar(fig, ev_type, ev_label, seq, total_evs, ev_color, note)

    frame = _fig_to_rgb(fig)
    plt.close(fig)
    return _norm_frame(frame)


# ── Public API ─────────────────────────────────────────────────────────────

def generate_video_from_timeline(
    timeline_result: dict,
    source: str,
    language: str,
    mode: str,
    output_path: str | None = None,
) -> str:
    """
    Build an MP4 from the rich timeline produced by TimelineGenerator.
    Each event gets its own dedicated animated frame so the video
    clearly shows every step of execution.

    Parameters
    ----------
    timeline_result : dict
        Output of generate_timeline() → {"timeline": [...], "stdout": ..., "error": ...}
    source          : str
        Original source code (for the code panel)
    language / mode : str
        Displayed in the title card
    output_path     : str | None
        Where to write the MP4 (temp file if None)

    Returns
    -------
    str  Path to the written MP4 file.
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = tmp.name
        tmp.close()

    source_lines = source.splitlines()
    tl           = timeline_result.get("timeline", [])
    final_stdout = timeline_result.get("stdout", "")
    error        = timeline_result.get("error")

    # Filter out final_output — handled separately
    events = [e for e in tl if e.get("event") != "final_output"]
    total_evs = len(events)

    # ── Cumulative state tracking ──────────────────────────────
    cum_vars    : dict = {}   # name → repr string
    cum_structs : list = []   # from data_structure_detector (not in timeline, kept empty)
    cum_stdout  : str  = ""
    cur_line    : int  = 1
    changed_keys: set  = set()

    def _update_state(ev: dict):
        nonlocal cum_stdout, cur_line, changed_keys
        ev_t = ev.get("event")
        changed_keys = set()

        if ev_t == "line_execute":
            cur_line = ev.get("line", cur_line) or cur_line

        elif ev_t == "variable_set":
            name = ev.get("name", "")
            if name and not name.startswith("__") and name != "_":
                cum_vars[name] = ev.get("value", "")
                changed_keys.add(name)

        elif ev_t == "variable_change":
            name = ev.get("name", "")
            if name and not name.startswith("__"):
                # Handle dict inserts like "seen[2]"
                cum_vars[name] = ev.get("new_value", "")
                changed_keys.add(name.split("[")[0])

        elif ev_t in ("array_update", "array_append", "array_pop",
                      "matrix_cell_update"):
            var = ev.get("var", "")
            changed_keys.add(var)

        elif ev_t == "output":
            text = ev.get("text", "")
            cum_stdout = (cum_stdout + "\n" + text).strip()

    # ── Build frame list ───────────────────────────────────────
    def _norm(f):
        return _norm_frame(f)

    all_frames: list[np.ndarray] = []

    # Intro (3 s)
    title_f = _norm(_render_title_frame(language, mode, total_evs))
    all_frames.extend([title_f] * (FPS * 3))

    for ev in events:
        _update_state(ev)

        ev_t   = ev.get("event", "line_execute")
        secs   = _EV_SECS.get(ev_t, 1.0)
        n_frms = max(1, round(secs * FPS))

        frame = _norm(_build_timeline_frame(
            ev, source_lines, total_evs,
            cum_vars, cum_structs, cum_stdout,
            cur_line, changed_keys,
        ))
        all_frames.extend([frame] * n_frms)

    # End frame (4 s)
    end_f = _norm(_render_end_frame(final_stdout, error))
    all_frames.extend([end_f] * (FPS * 4))

    iio.imwrite(
        output_path, all_frames,
        fps=FPS, codec="libx264", quality=8, macro_block_size=16,
    )
    return output_path
