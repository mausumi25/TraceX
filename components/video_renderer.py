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


def _ensure_912(fig):
    """Resize canvas in-place so height is exactly 912px (divisible by 16)."""
    fig.set_size_inches(16, 9.12)
    fig.set_dpi(100)


def _render_frame(step: dict, source_lines: list[str], total_steps: int) -> np.ndarray:
    """Render a single execution step as an RGB frame — 4-panel layout."""
    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    gs  = GridSpec(
        4, 2,
        figure=fig,
        left=0.03, right=0.97,
        top=0.91,  bottom=0.05,
        hspace=0.38, wspace=0.06,
        height_ratios=[2.5, 1.5, 1.8, 0.9],
    )

    _ensure_912(fig)

    ax_code   = fig.add_subplot(gs[:, 0])
    ax_vars   = fig.add_subplot(gs[0, 1])
    ax_struct = fig.add_subplot(gs[1:3, 1])
    ax_stack  = fig.add_subplot(gs[3, 1])

    for ax in (ax_code, ax_vars, ax_struct, ax_stack):
        ax.set_facecolor(BG3)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
            spine.set_linewidth(1.2)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    # ─── Title bar ───────────────────────────────────────────
    progress  = step["step"] / max(total_steps, 1)
    ev_colors = {"call": VIOLET, "return": CYAN, "exception": ROSE, "line": GREEN}
    ev_color  = ev_colors.get(step["event"], GREEN)

    fig.text(0.03, 0.965, "TraceX", fontsize=16, fontweight="bold",
             color=VIOLET, va="center", fontfamily="DejaVu Sans")
    fig.text(0.5, 0.965, step["note"], fontsize=10, color=TEXT2,
             ha="center", va="center")
    fig.text(0.97, 0.965, f"Step {step['step']} / {total_steps}",
             fontsize=9, color=TEXT3, ha="right", va="center")

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
    ax_code.set_ylim(-0.5, max(n - 0.5, 0.5))   # never singular

    for i, text in enumerate(visible_lines):
        abs_ln     = visible_start + i + 1
        is_current = (abs_ln == step["line_no"])

        if is_current:
            ax_code.axhspan(n - 1 - i - 0.45, n - 1 - i + 0.45,
                            color=ev_color, alpha=0.18)
            ax_code.plot([0, 0.012], [n - 1 - i, n - 1 - i],
                         color=ev_color, lw=3, solid_capstyle="round")

        ax_code.text(0.018, n - 1 - i, f"{abs_ln:>3}",
                     fontsize=7.5, color=TEXT3 if not is_current else ev_color,
                     va="center", fontfamily="monospace")
        ax_code.text(0.065, n - 1 - i,
                     text[:72] if len(text) > 72 else text,
                     fontsize=8,
                     color=TEXT if is_current else TEXT2,
                     va="center", fontfamily="monospace",
                     fontweight="bold" if is_current else "normal")

    # ─── Variables panel ─────────────────────────────────────
    ax_vars.set_title("  Variables", loc="left", fontsize=9,
                      color=TEXT3, pad=4, fontweight="bold")
    ax_vars.set_xlim(0, 1)

    variables = step.get("variables", {})
    items     = list(variables.items())
    n_vars    = len(items)
    ax_vars.set_ylim(-0.5, max(n_vars - 0.5, 0.5))   # never singular

    if not items:
        ax_vars.text(0.5, 0.5, "No variables yet",
                     ha="center", va="center", color=TEXT3,
                     fontsize=9, transform=ax_vars.transAxes)
    else:
        for i, (k, v) in enumerate(items[:8]):
            row  = n_vars - 1 - i
            rect = mpatches.FancyBboxPatch(
                (0.01, row - 0.35), 0.28, 0.7,
                boxstyle="round,pad=0.02",
                facecolor=BG2, edgecolor=PURPLE, linewidth=0.8)
            ax_vars.add_patch(rect)
            ax_vars.text(0.15, row, k, ha="center", va="center",
                         color=VIOLET, fontsize=8, fontfamily="monospace",
                         fontweight="bold")
            rect2 = mpatches.FancyBboxPatch(
                (0.31, row - 0.35), 0.67, 0.7,
                boxstyle="round,pad=0.02",
                facecolor="#0A1628", edgecolor=BORDER, linewidth=0.8)
            ax_vars.add_patch(rect2)
            ax_vars.text(0.645, row,
                         v[:38] if len(v) > 38 else v,
                         ha="center", va="center",
                         color=CYAN, fontsize=7.5, fontfamily="monospace")

    stdout_text = step.get("stdout", "").strip()
    if stdout_text:
        last = stdout_text.split("\n")[-2:]
        ax_vars.text(0.5, -0.55,
                     "stdout  " + " | ".join(last)[:70],
                     ha="center", va="center", color=GREEN,
                     fontsize=7, fontfamily="monospace",
                     transform=ax_vars.transAxes, clip_on=False)

    # ─── Data Structures panel ────────────────────────────────
    ax_struct.set_title("  Data Structures", loc="left", fontsize=9,
                         color=TEXT3, pad=4, fontweight="bold")
    ax_struct.set_xlim(0, 1)
    ax_struct.set_ylim(0, 1)
    ax_struct.axis("off")

    structures  = step.get("structures", [])
    interesting = [
        s for s in structures
        if s["kind"] not in ("Primitive", "Unknown", "String")
    ]

    if not interesting:
        ax_struct.text(0.5, 0.5, "No complex structures yet",
                       ha="center", va="center", color=TEXT3,
                       fontsize=9, transform=ax_struct.transAxes)
    else:
        _draw_structures(ax_struct, interesting[:3])

    # ─── Call Stack panel ─────────────────────────────────────
    ax_stack.set_title("  Call Stack", loc="left", fontsize=9,
                       color=TEXT3, pad=4, fontweight="bold")
    ax_stack.set_xlim(0, 1)

    stack = step.get("call_stack", [])
    if not stack:
        stack = [{"name": "<module>", "line": step["line_no"]}]

    ax_stack.set_ylim(-0.5, len(stack) - 0.5)
    for i, frame in enumerate(stack):
        col   = VIOLET if i == len(stack) - 1 else TEXT2
        label = f"{'-> ' if i == len(stack)-1 else '   '}{frame['name']}()  line {frame['line']}"
        ax_stack.text(0.03, i, label, va="center", color=col,
                      fontsize=8.5, fontfamily="monospace",
                      fontweight="bold" if i == len(stack) - 1 else "normal")

    frame_rgb = _fig_to_rgb(fig)
    plt.close(fig)
    return frame_rgb


# ─── Structure Visualizer helpers ────────────────────────────

_KIND_COLORS = {
    "Array":       "#06B6D4",   # cyan
    "Stack":       "#A78BFA",   # violet
    "Queue":       "#34D399",   # green
    "Matrix":      "#F59E0B",   # amber
    "DP Table":    "#F97316",   # orange
    "Linked List": "#EC4899",   # pink
    "Tree":        "#10B981",   # emerald
    "Graph":       "#6366F1",   # indigo
    "Dict":        "#94A3B8",   # slate
    "Set":         "#F43F5E",   # rose
}


def _draw_structures(ax, structures: list[dict]) -> None:
    """Render up to 3 data structures inside ax (already normalised to [0,1]x[0,1])."""
    n    = len(structures)
    slot_h = 1.0 / n           # vertical slice per structure

    for idx, s in enumerate(structures):
        y_top = 1.0 - idx * slot_h
        y_bot = y_top - slot_h
        y_mid = (y_top + y_bot) / 2
        color = _KIND_COLORS.get(s["kind"], TEXT3)

        # Label badge
        ax.text(0.01, y_top - 0.04,
                f"{s['kind']}  {s['name']}",
                va="top", ha="left",
                fontsize=7.5, color=color,
                fontweight="bold", fontfamily="monospace")

        kind = s["kind"]
        meta = s.get("meta", {})

        if kind in ("Array", "Stack", "Queue"):
            _draw_array_strip(ax, meta.get("elements", []), y_mid, color, kind)

        elif kind in ("Matrix", "DP Table"):
            _draw_matrix_grid(ax, meta.get("cells", []),
                              meta.get("rows", 0), meta.get("cols", 0),
                              y_bot + 0.02, y_top - 0.12, color)

        elif kind == "Linked List":
            _draw_linked_list(ax, meta.get("nodes", []), y_mid, color)

        elif kind == "Tree":
            _draw_tree(ax, meta.get("nodes", []), y_bot + 0.02, y_top - 0.12, color)

        elif kind == "Graph":
            _draw_graph_summary(ax, meta.get("nodes", []),
                                meta.get("edges", []), y_mid, color)

        elif kind in ("Dict", "Set"):
            elems = meta.get("elements", meta.get("keys", []))
            _draw_set_strip(ax, elems, y_mid, color)

        # Divider
        if idx < n - 1:
            ax.axhline(y_bot, color=BORDER, lw=0.7, alpha=0.5)


def _draw_array_strip(ax, elements: list, y: float, color: str, kind: str) -> None:
    """Horizontal box strip for Array / Stack / Queue."""
    if not elements:
        ax.text(0.5, y, "[ ]", ha="center", va="center", color=TEXT3, fontsize=8)
        return

    MAX_BOXES = 14
    show = elements[:MAX_BOXES]
    n    = len(show)
    box_w = min(0.06, 0.85 / n)
    x_start = 0.07

    # Arrow indicators for Stack / Queue
    if kind == "Stack":
        ax.annotate("TOP", xy=(x_start + (n - 1) * (box_w + 0.01) + box_w / 2, y + 0.06),
                    fontsize=6.5, color=color, ha="center")
    elif kind == "Queue":
        ax.text(x_start - 0.05, y, "IN", fontsize=6.5, color=color,
                ha="right", va="center")

    for i, val in enumerate(show):
        x = x_start + i * (box_w + 0.01)
        rect = mpatches.FancyBboxPatch(
            (x, y - 0.055), box_w, 0.11,
            boxstyle="round,pad=0.005",
            facecolor=color + "33",
            edgecolor=color, linewidth=1.2,
        )
        ax.add_patch(rect)
        label = str(val)[:5]
        ax.text(x + box_w / 2, y, label,
                ha="center", va="center",
                fontsize=7, color=TEXT,
                fontfamily="monospace")

    if len(elements) > MAX_BOXES:
        ax.text(x_start + MAX_BOXES * (box_w + 0.01) + 0.01, y,
                f"…+{len(elements)-MAX_BOXES}",
                va="center", fontsize=7, color=TEXT3)


def _draw_matrix_grid(ax, cells: list, rows: int, cols: int,
                      y_bot: float, y_top: float, color: str) -> None:
    """Compact grid for Matrix / DP Table."""
    if not cells or rows == 0 or cols == 0:
        ax.text(0.5, (y_bot + y_top) / 2, "[ ]",
                ha="center", va="center", color=TEXT3, fontsize=8)
        return

    MAX_R, MAX_C = 8, 10
    show_rows = min(rows, MAX_R)
    show_cols = min(cols, MAX_C)

    h_total = y_top - y_bot
    w_total = 0.88
    cell_h  = h_total / show_rows
    cell_w  = w_total / show_cols
    x0 = 0.06

    for r in range(show_rows):
        for c in range(show_cols):
            x = x0 + c * cell_w
            y = y_bot + (show_rows - 1 - r) * cell_h
            val = cells[r][c] if r < len(cells) and c < len(cells[r]) else ""

            # Color heat map for DP tables
            try:
                intensity = float(val) / (max(
                    abs(float(cells[rr][cc]))
                    for rr in range(show_rows)
                    for cc in range(show_cols)
                    if rr < len(cells) and cc < len(cells[rr])
                ) + 1e-9)
                alpha = min(0.7, abs(intensity) * 0.6 + 0.1)
            except Exception:
                alpha = 0.15

            rect = mpatches.FancyBboxPatch(
                (x + 0.001, y + 0.001), cell_w - 0.002, cell_h - 0.002,
                boxstyle="square,pad=0",
                facecolor=color + f"{int(alpha*255):02x}",
                edgecolor=color, linewidth=0.5,
            )
            ax.add_patch(rect)
            label = str(val)[:4]
            ax.text(x + cell_w / 2, y + cell_h / 2, label,
                    ha="center", va="center",
                    fontsize=min(7.5, 50 / max(show_cols, 1)),
                    color=TEXT, fontfamily="monospace")

    if rows > MAX_R or cols > MAX_C:
        ax.text(0.97, y_bot, f"+more ({rows}x{cols})",
                ha="right", va="bottom", fontsize=6.5, color=TEXT3)


def _draw_linked_list(ax, nodes: list, y: float, color: str) -> None:
    """Chain of boxes connected with arrows."""
    if not nodes:
        ax.text(0.5, y, "NULL", ha="center", va="center",
                color=TEXT3, fontsize=9)
        return

    MAX_NODES = 10
    show = nodes[:MAX_NODES]
    n    = len(show)
    box_w, box_h = 0.07, 0.1
    gap  = 0.025
    x0   = 0.04

    total_w = n * box_w + (n - 1) * (gap + 0.025)
    x0 = max(0.03, (1 - total_w) / 2)

    for i, val in enumerate(show):
        x = x0 + i * (box_w + gap + 0.025)
        rect = mpatches.FancyBboxPatch(
            (x, y - box_h / 2), box_w, box_h,
            boxstyle="round,pad=0.005",
            facecolor=color + "33", edgecolor=color, linewidth=1.3)
        ax.add_patch(rect)
        ax.text(x + box_w / 2, y, str(val)[:5],
                ha="center", va="center",
                fontsize=7.5, color=TEXT, fontfamily="monospace")
        # Arrow
        if i < n - 1:
            ax.annotate("",
                xy=(x + box_w + gap + 0.025, y),
                xytext=(x + box_w + 0.003, y),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.2))

    # NULL terminus
    ax.text(x0 + n * (box_w + gap + 0.025) - gap, y,
            "NULL", ha="left", va="center",
            fontsize=7, color=TEXT3, fontfamily="monospace")


def _draw_tree(ax, nodes: list[dict], y_bot: float, y_top: float,
               color: str) -> None:
    """BFS-positioned binary tree nodes."""
    if not nodes:
        ax.text(0.5, (y_bot + y_top) / 2, "None",
                ha="center", va="center", color=TEXT3, fontsize=9)
        return

    h_range = y_top - y_bot
    max_depth = max(n["depth"] for n in nodes) if nodes else 0
    max_depth = max(max_depth, 1)

    # Map (depth, index) → x,y position
    def pos(depth, idx):
        width_slots = 2 ** (max_depth + 1)
        x = idx / width_slots
        y = y_top - (depth / max_depth) * h_range * 0.9
        return x, y

    node_pos = {}
    for nd in nodes[:31]:          # cap at 31 nodes
        d, i = nd["depth"], nd["index"]
        x, y = pos(d, i)
        node_pos[(d, i)] = (x, y)

        # Draw edge to parent
        if d > 0:
            parent_i = i // 2
            pk = (d - 1, parent_i)
            if pk in node_pos:
                px, py = node_pos[pk]
                ax.plot([px, x], [py, y], color=color, lw=0.9, alpha=0.6)

        # Node circle
        circle = plt.Circle((x, y), radius=0.025 / max(max_depth, 1) * 2,
                             color=color + "55", ec=color, lw=1.2)
        ax.add_patch(circle)
        ax.text(x, y, str(nd["val"])[:3],
                ha="center", va="center",
                fontsize=max(5, 8 - max_depth),
                color=TEXT, fontfamily="monospace")


def _draw_graph_summary(ax, nodes: list, edges: list, y: float,
                        color: str) -> None:
    """Simple text summary for graphs (full layout is expensive)."""
    n_nodes = len(nodes)
    n_edges = len(edges)
    ax.text(0.5, y + 0.04,
            f"Nodes: {', '.join(str(n) for n in nodes[:8])}{',...' if n_nodes>8 else ''}",
            ha="center", va="center", fontsize=7.5, color=TEXT,
            fontfamily="monospace")
    ax.text(0.5, y - 0.04,
            f"Edges: {n_edges}  e.g. {' '.join(f'{a}->{b}' for a,b in edges[:3])}",
            ha="center", va="center", fontsize=7.5, color=color,
            fontfamily="monospace")


def _draw_set_strip(ax, elements: list, y: float, color: str) -> None:
    """Pill badges for Set / Dict keys."""
    x = 0.06
    for el in elements[:12]:
        label = str(el)[:8]
        w = len(label) * 0.013 + 0.03
        rect = mpatches.FancyBboxPatch(
            (x, y - 0.045), w, 0.09,
            boxstyle="round,pad=0.008",
            facecolor=color + "44", edgecolor=color, linewidth=1)
        ax.add_patch(rect)
        ax.text(x + w / 2, y, label,
                ha="center", va="center",
                fontsize=7, color=TEXT, fontfamily="monospace")
        x += w + 0.015
        if x > 0.92:
            break




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
    Builds a cumulative variable+structure snapshot so variables never
    disappear when execution enters a sub-scope (e.g. comprehensions).
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = tmp.name
        tmp.close()

    source_lines = source.splitlines()
    total_steps  = len(steps)
    final_stdout = steps[-1]["stdout"] if steps else ""

    # ── Build cumulative snapshots ──────────────────────────────
    # At each step, merge current vars/structs ON TOP OF the running
    # cumulative state so sub-scope steps don't blank the display.
    cumulative_vars    : dict = {}
    cumulative_structs : dict = {}   # keyed by var name → struct dict

    enriched_steps = []
    for step in steps:
        cur_vars = step.get("variables", {})
        cur_structs = step.get("structures", [])

        # Update cumulative only when we HAVE data (non-empty scope)
        if cur_vars:
            cumulative_vars.update(cur_vars)
        if cur_structs:
            for s in cur_structs:
                # skip __builtins__ and other dunder names
                if not s["name"].startswith("__"):
                    cumulative_structs[s["name"]] = s

        # Build enriched step with merged snapshot
        enriched = dict(step)
        enriched["variables"]  = dict(cumulative_vars)
        enriched["structures"] = list(cumulative_structs.values())
        enriched_steps.append(enriched)


    # ── Normalise every frame to exactly 1600x912 (W x H) ────────────────
    def _norm(frame):
        import numpy as _np
        h, w = frame.shape[:2]
        if h < 912:
            frame = _np.vstack([frame, _np.zeros((912 - h, w, 3), dtype='uint8')])
        elif h > 912:
            frame = frame[:912]
        h, w = frame.shape[:2]
        if w < 1600:
            frame = _np.hstack([frame, _np.zeros((h, 1600 - w, 3), dtype='uint8')])
        elif w > 1600:
            frame = frame[:, :1600]
        return frame.astype('uint8')

    all_frames = []

    # Intro 3 seconds
    all_frames.extend([_norm(_render_title_frame(language, mode, total_steps))] * (FPS * 3))

    # Step frames
    for step in enriched_steps:
        all_frames.extend([_norm(_render_frame(step, source_lines, total_steps))] * HOLD_FRAMES)

    # End frame 4 seconds
    all_frames.extend([_norm(_render_end_frame(final_stdout, error))] * (FPS * 4))

    iio.imwrite(
        output_path,
        all_frames,
        fps=FPS,
        codec="libx264",
        quality=8,
        macro_block_size=16,
    )

    return output_path
