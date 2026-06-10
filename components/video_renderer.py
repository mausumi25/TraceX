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
CHANGED     = "#F97316"   # orange highlight for mutated variables

FPS         = 2           # 2 fps → each step = 1 second on screen
HOLD_FRAMES = 2           # frames per step


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


def _render_frame(
    step: dict,
    source_lines: list[str],
    total_steps: int,
    prev_vars: dict | None = None,
) -> np.ndarray:
    """
    Render one dry-run step frame.

    prev_vars  — variable dict from the PREVIOUS step (for change detection).
                 Any variable whose value differs from prev_vars is highlighted
                 in orange so the viewer can immediately see what mutated.
    """
    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    gs  = GridSpec(
        4, 2,
        figure=fig,
        left=0.03, right=0.97,
        top=0.92,  bottom=0.05,
        hspace=0.40, wspace=0.06,
        height_ratios=[2.5, 1.5, 1.8, 0.85],
    )
    _ensure_912(fig)

    ax_code   = fig.add_subplot(gs[:, 0])
    ax_vars   = fig.add_subplot(gs[0, 1])
    ax_struct = fig.add_subplot(gs[1:3, 1])
    ax_stack  = fig.add_subplot(gs[3, 1])

    for ax in (ax_code, ax_vars, ax_struct, ax_stack):
        ax.set_facecolor(BG3)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER); spine.set_linewidth(1.4)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    # ── Event colour + progress ───────────────────────────────
    progress  = step["step"] / max(total_steps, 1)
    ev_map    = {"call": VIOLET, "return": CYAN, "exception": ROSE, "line": GREEN}
    ev_color  = ev_map.get(step.get("event", "line"), GREEN)
    ev_label  = {"call": "CALL", "return": "RETURN",
                 "exception": "ERROR", "line": "LINE"}.get(step.get("event", "line"), "LINE")

    # ── Title bar ─────────────────────────────────────────────
    fig.text(0.03, 0.968, "TraceX", fontsize=15, fontweight="bold",
             color=VIOLET, va="center", fontfamily="DejaVu Sans")

    # Event pill
    fig.text(0.14, 0.968, f"  {ev_label}  ", fontsize=8, fontweight="bold",
             color=BG, va="center", ha="left",
             bbox=dict(boxstyle="round,pad=0.3", facecolor=ev_color, edgecolor="none"))

    # Current line note (centre)
    note = step.get("note", "")
    fig.text(0.5, 0.968, note[:70], fontsize=9.5, color=TEXT2,
             ha="center", va="center", style="italic")

    # Step counter (right)
    fig.text(0.97, 0.968, f"Step  {step['step']} / {total_steps}",
             fontsize=9, color=TEXT3, ha="right", va="center", fontweight="bold")

    # Progress bar
    bar_ax = fig.add_axes([0.03, 0.948, 0.94, 0.009])
    bar_ax.set_facecolor(BG2); bar_ax.set_xlim(0, 1); bar_ax.set_ylim(0, 1)
    bar_ax.axvspan(0, progress, ymin=0, ymax=1, color=ev_color, alpha=0.9)
    bar_ax.axis("off")

    # ── Code panel ────────────────────────────────────────────
    ax_code.set_title("  Source Code", loc="left", fontsize=9,
                      color=TEXT3, pad=5, fontweight="bold")
    ax_code.set_xlim(0, 1)

    cur_line      = step.get("line_no", 1) or 1
    visible_start = max(0, cur_line - 9)
    visible_lines = source_lines[visible_start: visible_start + 22]
    n             = len(visible_lines)
    ax_code.set_ylim(-0.5, max(n - 0.5, 0.5))

    for i, text in enumerate(visible_lines):
        abs_ln     = visible_start + i + 1
        is_current = (abs_ln == cur_line)
        row_y      = n - 1 - i

        if is_current:
            # Bright highlight band
            ax_code.axhspan(row_y - 0.48, row_y + 0.48,
                            color=ev_color, alpha=0.20, zorder=0)
            # Thick left-edge bar
            ax_code.plot([0, 0.008], [row_y, row_y],
                         color=ev_color, lw=5, solid_capstyle="butt", zorder=3)
            # Animated arrow ▶
            ax_code.text(0.010, row_y, "▶", fontsize=9, color=ev_color,
                         va="center", zorder=4)

        # Line number
        ax_code.text(0.022, row_y, f"{abs_ln:>3}",
                     fontsize=7.5, va="center", fontfamily="monospace",
                     color=ev_color if is_current else TEXT3,
                     fontweight="bold" if is_current else "normal")

        # Code text
        ax_code.text(0.068, row_y,
                     text[:71] if len(text) > 71 else text,
                     fontsize=8.2,
                     color=TEXT if is_current else TEXT2,
                     va="center", fontfamily="monospace",
                     fontweight="bold" if is_current else "normal")

    # ── Variables panel (with change highlighting) ────────────
    ax_vars.set_title("  Variables", loc="left", fontsize=9,
                      color=TEXT3, pad=4, fontweight="bold")
    ax_vars.set_xlim(0, 1)

    variables  = step.get("variables", {})
    prev       = prev_vars or {}

    # Filter noise: skip _ (comprehension), skip callables represented as <...>
    display_vars = {
        k: v for k, v in variables.items()
        if k not in ("_",) and not k.startswith("__")
    }

    items  = list(display_vars.items())
    n_vars = len(items)
    ax_vars.set_ylim(-0.5, max(n_vars - 0.5, 0.5))

    if not items:
        ax_vars.text(0.5, 0.5, "No variables yet",
                     ha="center", va="center", color=TEXT3,
                     fontsize=9, transform=ax_vars.transAxes)
    else:
        for i, (k, v) in enumerate(items[:9]):
            row      = n_vars - 1 - i
            changed  = prev.get(k) != v    # True if new or mutated this step
            k_color  = CHANGED if changed else VIOLET
            v_color  = CHANGED if changed else CYAN
            k_border = CHANGED if changed else PURPLE
            v_bg     = "#1A0A00" if changed else "#0A1628"

            # Key box
            rect = mpatches.FancyBboxPatch(
                (0.01, row - 0.38), 0.26, 0.76,
                boxstyle="round,pad=0.02",
                facecolor=BG2, edgecolor=k_border, linewidth=1.2 if changed else 0.8)
            ax_vars.add_patch(rect)
            ax_vars.text(0.14, row, k,
                         ha="center", va="center", color=k_color,
                         fontsize=8, fontfamily="monospace", fontweight="bold")

            # Value box
            rect2 = mpatches.FancyBboxPatch(
                (0.29, row - 0.38), 0.69, 0.76,
                boxstyle="round,pad=0.02",
                facecolor=v_bg, edgecolor=k_border, linewidth=1.2 if changed else 0.8)
            ax_vars.add_patch(rect2)
            ax_vars.text(0.635, row,
                         v[:36] if len(v) > 36 else v,
                         ha="center", va="center", color=v_color,
                         fontsize=7.5, fontfamily="monospace",
                         fontweight="bold" if changed else "normal")

            # ★ badge for newly changed vars
            if changed:
                ax_vars.text(0.955, row, "★",
                             ha="center", va="center",
                             color=CHANGED, fontsize=9)

    # Stdout strip
    stdout_text = step.get("stdout", "").strip()
    if stdout_text:
        out_lines = stdout_text.split("\n")
        # Show last 3 lines of output
        preview = "  ▸  ".join(out_lines[-3:])
        ax_vars.text(0.5, -0.60,
                     f"stdout: {preview[:72]}",
                     ha="center", va="center", color=GREEN,
                     fontsize=7.5, fontfamily="monospace",
                     fontweight="bold",
                     transform=ax_vars.transAxes, clip_on=False)

    # ── Data Structures panel ─────────────────────────────────
    ax_struct.set_title("  Data Structures", loc="left", fontsize=9,
                        color=TEXT3, pad=4, fontweight="bold")
    ax_struct.set_xlim(0, 1); ax_struct.set_ylim(0, 1)
    ax_struct.axis("off")

    structures  = step.get("structures", [])
    interesting = [s for s in structures
                   if s["kind"] not in ("Primitive", "Unknown", "String")]

    if not interesting:
        ax_struct.text(0.5, 0.5, "No complex structures yet",
                       ha="center", va="center", color=TEXT3,
                       fontsize=9, transform=ax_struct.transAxes)
    else:
        _draw_structures(ax_struct, interesting[:3])

    # ── Call Stack panel ──────────────────────────────────────
    ax_stack.set_title("  Call Stack", loc="left", fontsize=9,
                       color=TEXT3, pad=4, fontweight="bold")
    ax_stack.set_xlim(0, 1)

    stack = step.get("call_stack", []) or [{"name": "<module>", "line": cur_line}]
    ax_stack.set_ylim(-0.5, max(len(stack) - 0.5, 0.5))

    for i, fr in enumerate(stack):
        is_top = (i == len(stack) - 1)
        col    = ev_color if is_top else TEXT2
        prefix = "▶  " if is_top else "   "
        label  = f"{prefix}{fr['name']}()  — line {fr['line']}"
        ax_stack.text(0.03, i, label[:65], va="center", color=col,
                      fontsize=8.5, fontfamily="monospace",
                      fontweight="bold" if is_top else "normal")

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

    # Step frames — pass prev_vars for change-highlighting
    prev_vars = {}
    for step in enriched_steps:
        frame = _norm(_render_frame(step, source_lines, total_steps, prev_vars))
        all_frames.extend([frame] * HOLD_FRAMES)
        # Update prev_vars (filter noise same as renderer)
        prev_vars = {
            k: v for k, v in step.get('variables', {}).items()
            if k not in ('_',) and not k.startswith('__')
        }

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


# ═══════════════════════════════════════════════════════════════════════════
#  TIMELINE-DRIVEN VIDEO GENERATOR
#  Each timeline event → dedicated animated frame with event-specific card.
# ═══════════════════════════════════════════════════════════════════════════

# Seconds to display each event type
_EV_SECS = {
    "line_execute"       : 1.0,
    "variable_set"       : 0.6,
    "variable_change"    : 0.6,
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
    "final_output"       : 0.0,
}

_EV_LABEL = {
    "line_execute"       : "LINE",
    "variable_set"       : "SET",
    "variable_change"    : "CHANGED",
    "array_update"       : "ARRAY UPD",
    "array_append"       : "APPEND",
    "array_pop"          : "POP",
    "matrix_cell_update" : "MATRIX",
    "loop_start"         : "LOOP START",
    "loop_iteration"     : "LOOP ITER",
    "loop_end"           : "LOOP END",
    "condition_check"    : "CONDITION",
    "function_call"      : "CALL",
    "function_return"    : "RETURN",
    "output"             : "OUTPUT",
}

_EV_COLORS_TL = {
    "line_execute"       : "#06B6D4",
    "variable_set"       : "#10B981",
    "variable_change"    : "#F97316",
    "array_update"       : "#60A5FA",
    "array_append"       : "#38BDF8",
    "array_pop"          : "#93C5FD",
    "matrix_cell_update" : "#FBBF24",
    "loop_start"         : "#A78BFA",
    "loop_iteration"     : "#C4B5FD",
    "loop_end"           : "#7C3AED",
    "condition_check"    : "#F59E0B",
    "function_call"      : "#818CF8",
    "function_return"    : "#6EE7B7",
    "output"             : "#86EFAC",
}


def _tl_norm(frame):
    """Force exactly 1600×912."""
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


def _tl_panel(ax, title="", accent=None):
    accent = accent or BORDER
    ax.set_facecolor(BG3)
    for sp in ax.spines.values():
        sp.set_edgecolor(accent)
        sp.set_linewidth(1.8)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    if title:
        ax.set_title(f"  {title}", loc="left", fontsize=9,
                     color=TEXT3, pad=5, fontweight="bold")


def _tl_title_bar(fig, ev_type, ev_label, seq, total, ev_color, note=""):
    fig.text(0.03, 0.968, "TraceX", fontsize=15, fontweight="bold",
             color=VIOLET, va="center", fontfamily="DejaVu Sans")
    fig.text(0.14, 0.968, f"  {ev_label}  ", fontsize=8, fontweight="bold",
             color=BG, va="center", ha="left",
             bbox=dict(boxstyle="round,pad=0.3", facecolor=ev_color, edgecolor="none"))
    if note:
        fig.text(0.5, 0.968, note[:72], fontsize=9, color=TEXT2,
                 ha="center", va="center", style="italic")
    fig.text(0.97, 0.968, f"Event {seq} / {total}",
             fontsize=9, color=TEXT3, ha="right", va="center", fontweight="bold")
    bar = fig.add_axes([0.03, 0.948, 0.94, 0.009])
    bar.set_facecolor(BG2); bar.set_xlim(0, 1); bar.set_ylim(0, 1)
    bar.axvspan(0, seq / max(total, 1), color=ev_color, alpha=0.9)
    bar.axis("off")


def _tl_code_panel(ax, source_lines, cur_line, ev_color):
    ax.set_xlim(0, 1)
    vis_start = max(0, cur_line - 9)
    vis_lines = source_lines[vis_start: vis_start + 22]
    n = len(vis_lines)
    ax.set_ylim(-0.5, max(n - 0.5, 0.5))
    _tl_panel(ax, "Source Code", ev_color)

    for i, text in enumerate(vis_lines):
        abs_ln = vis_start + i + 1
        is_cur = (abs_ln == cur_line)
        row_y  = n - 1 - i

        if is_cur:
            ax.axhspan(row_y - 0.48, row_y + 0.48, color=ev_color, alpha=0.22, zorder=0)
            ax.plot([0, 0.007], [row_y, row_y], color=ev_color, lw=5,
                    solid_capstyle="butt", zorder=3)
            ax.text(0.010, row_y, "▶", fontsize=9, color=ev_color, va="center", zorder=4)

        ax.text(0.022, row_y, f"{abs_ln:>3}",
                fontsize=7.5, va="center", fontfamily="monospace",
                color=ev_color if is_cur else TEXT3,
                fontweight="bold" if is_cur else "normal")
        ax.text(0.068, row_y, text[:70],
                fontsize=8.0, color=TEXT if is_cur else TEXT2,
                va="center", fontfamily="monospace",
                fontweight="bold" if is_cur else "normal")


def _tl_vars_mini(ax, cum_vars, changed_keys, ev_color, cum_stdout=""):
    """Mini vars panel for line_execute frames."""
    _tl_panel(ax, "Variables", ev_color)
    ax.set_xlim(0, 1)
    display = {k: v for k, v in cum_vars.items()
               if k not in ("_",) and not k.startswith("__")}
    items = list(display.items())
    n = len(items)
    ax.set_ylim(-0.5, max(n - 0.5, 0.5))
    if not items:
        ax.text(0.5, 0.5, "No variables yet", ha="center", va="center",
                color=TEXT3, fontsize=9, transform=ax.transAxes)
    else:
        for i, (k, v) in enumerate(items[:10]):
            row = n - 1 - i
            changed = k in changed_keys
            kc  = CHANGED if changed else VIOLET
            vc  = CHANGED if changed else CYAN
            bd  = CHANGED if changed else PURPLE
            ax.add_patch(mpatches.FancyBboxPatch((0.01, row-0.38), 0.26, 0.76,
                         boxstyle="round,pad=0.02", facecolor=BG2,
                         edgecolor=bd, linewidth=1.4 if changed else 0.8))
            ax.text(0.14, row, k, ha="center", va="center", color=kc,
                    fontsize=7.5, fontfamily="monospace", fontweight="bold")
            ax.add_patch(mpatches.FancyBboxPatch((0.29, row-0.38), 0.69, 0.76,
                         boxstyle="round,pad=0.02",
                         facecolor="#1A0A00" if changed else "#0A1628",
                         edgecolor=bd, linewidth=1.4 if changed else 0.8))
            ax.text(0.635, row, v[:34], ha="center", va="center", color=vc,
                    fontsize=7.0, fontfamily="monospace",
                    fontweight="bold" if changed else "normal")
            if changed:
                ax.text(0.965, row, "★", ha="center", va="center",
                        color=CHANGED, fontsize=9)
    if cum_stdout:
        out_lines = cum_stdout.strip().split("\n")
        preview = "  ▸  ".join(out_lines[-2:])
        ax.text(0.5, -0.65, f"stdout: {preview[:70]}", ha="center", va="center",
                color=GREEN, fontsize=7.0, fontfamily="monospace",
                fontweight="bold", transform=ax.transAxes, clip_on=False)


# ── Event Card helpers ──────────────────────────────────────────────────

def _card_big(ax, header, body1, body2="", body3="",
              ev_color=CYAN, body1_color=None, body2_color=None):
    """Generic big-card layout used by most event types."""
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    bc1 = body1_color or TEXT
    bc2 = body2_color or TEXT2

    ax.text(0.5, 0.90, header, ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3,
                      edgecolor=ev_color, lw=1.2))
    if body1:
        ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.55), 0.92, 0.26,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.68, body1[:55], ha="center", va="center",
                fontsize=12, color=bc1, fontfamily="monospace", fontweight="bold")
    if body2:
        ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.22), 0.92, 0.26,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.35, body2[:55], ha="center", va="center",
                fontsize=11, color=bc2, fontfamily="monospace",
                fontweight="bold" if body2_color else "normal")
    if body3:
        ax.text(0.5, 0.10, body3, ha="center", va="center",
                fontsize=8, color=TEXT3, fontfamily="monospace")


def _tl_render_event_card(ax, ev, ev_color, cum_vars):
    """Dispatch to the right card for this event type."""
    ev_t = ev.get("event")

    # ── CONDITION ──────────────────────────────────────────────
    if ev_t == "condition_check":
        result  = ev.get("result")
        expr    = ev.get("expression", "?")
        res_txt = "✅  TRUE" if result else "❌  FALSE"
        res_col = GREEN if result else ROSE
        _card_big(ax, "CONDITION CHECK",
                  f"if  {expr[:48]}",
                  res_txt,
                  f"line {ev.get('line','')}",
                  ev_color=ev_color,
                  body1_color=TEXT,
                  body2_color=res_col)

    # ── LOOP ───────────────────────────────────────────────────
    elif ev_t == "loop_start":
        lv = ev.get("loop_var", "?")
        it = ev.get("iterable", ev.get("condition", "?"))
        _card_big(ax, "🔄  LOOP START",
                  f"for  {lv}",
                  f"in  {it[:45]}",
                  f"line {ev.get('line','')}",
                  ev_color=ev_color,
                  body1_color=TEXT, body2_color=VIOLET)

    elif ev_t == "loop_iteration":
        n  = ev.get("iteration", "?")
        lv = ev.get("loop_var", "?")
        vl = str(ev.get("value", ev.get("result", "?")))
        _card_big(ax, f"🔄  ITERATION  #{n}",
                  f"{lv}  =  {vl[:35]}",
                  body_color=None,
                  ev_color=ev_color,
                  body1_color="#C4B5FD")

    elif ev_t == "loop_end":
        _card_big(ax, "🔄  LOOP COMPLETE",
                  f"{ev.get('iterations','?')} iterations done",
                  ev_color=ev_color, body1_color="#7C3AED")

    # ── FUNCTION ───────────────────────────────────────────────
    elif ev_t == "function_call":
        args = ", ".join(f"{k}={v}" for k, v in ev.get("arguments",{}).items())
        _card_big(ax, "📞  FUNCTION CALL",
                  f"{ev.get('function','?')}()",
                  args[:55] or "(no args)",
                  f"line {ev.get('line','')}",
                  ev_color=ev_color,
                  body1_color="#818CF8", body2_color=TEXT2)

    elif ev_t == "function_return":
        _card_big(ax, "↩️  RETURN",
                  f"{ev.get('function','?')}()",
                  f"→  {ev.get('value','?')[:45]}",
                  f"line {ev.get('line','')}",
                  ev_color=ev_color,
                  body1_color="#6EE7B7", body2_color=GREEN)

    # ── ARRAY ──────────────────────────────────────────────────
    elif ev_t in ("array_update", "array_append", "array_pop"):
        var = ev.get("var", "?")
        if ev_t == "array_update":
            hdr  = f"🔵  ARRAY UPDATE  ·  {var}"
            desc = f"[{ev.get('index')}]  {ev.get('old_value')} → {ev.get('new_value')}"
        elif ev_t == "array_append":
            hdr  = f"🔵  APPEND  ·  {var}"
            desc = f"append({ev.get('value')})  → len={ev.get('new_len')}"
        else:
            hdr  = f"🔵  POP  ·  {var}"
            desc = f"len {ev.get('old_len')} → {ev.get('new_len')}"

        ax.set_facecolor(BG2)
        for sp in ax.spines.values():
            sp.set_edgecolor(ev_color); sp.set_linewidth(2)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        ax.text(0.5, 0.90, hdr, ha="center", va="center",
                fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3,
                          edgecolor=ev_color, lw=1.2))

        # Draw array boxes
        raw = cum_vars.get(var, "")
        try:
            import ast as _ast
            arr = _ast.literal_eval(raw)
            if not isinstance(arr, list): raise ValueError
        except Exception:
            arr = []
        n_el = len(arr)
        if 0 < n_el <= 20:
            bw     = min(0.88 / n_el, 0.10)
            ox     = (1 - n_el * bw) / 2
            hi_idx = ev.get("index", -1)
            for idx, val in enumerate(arr):
                x    = ox + idx * bw
                is_h = (idx == hi_idx)
                ax.add_patch(mpatches.FancyBboxPatch(
                    (x + 0.005, 0.48), bw - 0.012, 0.22,
                    boxstyle="round,pad=0.01",
                    facecolor="#1c3d5a" if is_h else BG3,
                    edgecolor=ev_color if is_h else BORDER,
                    linewidth=2.0 if is_h else 0.8))
                ax.text(x + bw/2, 0.59, str(val)[:5],
                        ha="center", va="center", fontsize=9,
                        color=ev_color if is_h else CYAN,
                        fontfamily="monospace",
                        fontweight="bold" if is_h else "normal")
                ax.text(x + bw/2, 0.46, str(idx),
                        ha="center", va="center", fontsize=7, color=TEXT3)

        ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.16), 0.90, 0.20,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.26, desc, ha="center", va="center",
                fontsize=11, color=ev_color, fontfamily="monospace", fontweight="bold")

    # ── MATRIX ─────────────────────────────────────────────────
    elif ev_t == "matrix_cell_update":
        var   = ev.get("var", "?")
        row_i = ev.get("row", 0)
        col_i = ev.get("col", 0)
        desc  = f"[{row_i}][{col_i}]  {ev.get('old_value')} → {ev.get('new_value')}"

        ax.set_facecolor(BG2)
        for sp in ax.spines.values():
            sp.set_edgecolor(ev_color); sp.set_linewidth(2)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        ax.text(0.5, 0.90, f"🟡  MATRIX UPDATE  ·  {var}",
                ha="center", va="center",
                fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3,
                          edgecolor=ev_color, lw=1.2))

        raw = cum_vars.get(var, "")
        try:
            import ast as _ast
            mat = _ast.literal_eval(raw)
            if isinstance(mat, list) and mat and isinstance(mat[0], list):
                rows_n = len(mat); cols_n = len(mat[0])
                cell_h = min(0.48 / rows_n, 0.14)
                cell_w = min(0.82 / cols_n, 0.14)
                ox     = (1 - cols_n * cell_w) / 2
                oy     = 0.28
                for r in range(rows_n):
                    for c in range(cols_n):
                        x    = ox + c * cell_w
                        y    = oy + (rows_n - 1 - r) * cell_h
                        is_h = (r == row_i and c == col_i)
                        ax.add_patch(mpatches.FancyBboxPatch(
                            (x+0.005, y+0.005), cell_w-0.010, cell_h-0.010,
                            boxstyle="round,pad=0.01",
                            facecolor="#1c3d5a" if is_h else BG3,
                            edgecolor=ev_color if is_h else BORDER,
                            linewidth=2.0 if is_h else 0.6))
                        ax.text(x + cell_w/2, y + cell_h/2, str(mat[r][c])[:4],
                                ha="center", va="center", fontsize=8,
                                color=ev_color if is_h else TEXT2,
                                fontfamily="monospace",
                                fontweight="bold" if is_h else "normal")
        except Exception:
            pass

        ax.add_patch(mpatches.FancyBboxPatch((0.05, 0.08), 0.90, 0.16,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.16, desc, ha="center", va="center",
                fontsize=11, color=ev_color, fontfamily="monospace", fontweight="bold")

    # ── OUTPUT ─────────────────────────────────────────────────
    elif ev_t == "output":
        ax.set_facecolor(BG2)
        for sp in ax.spines.values():
            sp.set_edgecolor(ev_color); sp.set_linewidth(2)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

        ax.text(0.5, 0.88, "🖨️  PROGRAM OUTPUT", ha="center", va="center",
                fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3,
                          edgecolor=ev_color, lw=1.2))
        ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.52), 0.92, 0.26,
                     boxstyle="round,pad=0.02", facecolor="#052e16",
                     edgecolor=ev_color, linewidth=1.5))
        ax.text(0.5, 0.65, f">>> {ev.get('text','')[:52]}",
                ha="center", va="center",
                fontsize=13, color=GREEN, fontfamily="monospace", fontweight="bold")

    # ── VARIABLE SET / CHANGE ───────────────────────────────────
    elif ev_t in ("variable_set", "variable_change"):
        name = ev.get("name", "?")
        val  = ev.get("value", ev.get("new_value", "?"))
        old  = ev.get("old_value", "")
        if ev_t == "variable_set":
            hdr  = "🟢  VARIABLE SET"
            body = f"{name}  =  {val[:40]}"
            col  = GREEN
        else:
            hdr  = "🟠  VARIABLE CHANGED"
            body = f"{name}:  {old[:25]} → {val[:25]}"
            col  = CHANGED
        _card_big(ax, hdr, body,
                  f"type: {ev.get('type','?')}",
                  ev_color=ev_color,
                  body1_color=col, body2_color=TEXT3)

    # ── FALLBACK ────────────────────────────────────────────────
    else:
        ax.set_facecolor(BG2)
        for sp in ax.spines.values():
            sp.set_edgecolor(ev_color); sp.set_linewidth(2)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        ax.text(0.5, 0.5, ev_t.replace("_", "\n").upper(),
                ha="center", va="center", fontsize=14,
                color=ev_color, fontfamily="monospace", fontweight="bold")


def _card_big(ax, header, body1="", body2="", body3="",
              ev_color=CYAN, body1_color=None, body2_color=None,
              body_color=None):
    """Generic two-body card."""
    if body_color and not body1_color:
        body1_color = body_color
    body1_color = body1_color or TEXT
    body2_color = body2_color or TEXT2
    ax.set_facecolor(BG2)
    for sp in ax.spines.values():
        sp.set_edgecolor(ev_color); sp.set_linewidth(2)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    ax.text(0.5, 0.90, header, ha="center", va="center",
            fontsize=10, color=ev_color, fontweight="bold", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=BG3, edgecolor=ev_color, lw=1.2))
    if body1:
        ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.55), 0.92, 0.26,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.68, body1[:55], ha="center", va="center",
                fontsize=12, color=body1_color, fontfamily="monospace", fontweight="bold")
    if body2:
        ax.add_patch(mpatches.FancyBboxPatch((0.04, 0.22), 0.92, 0.26,
                     boxstyle="round,pad=0.02", facecolor=BG3,
                     edgecolor=ev_color, linewidth=1))
        ax.text(0.5, 0.35, body2[:55], ha="center", va="center",
                fontsize=11, color=body2_color, fontfamily="monospace",
                fontweight="bold" if body2_color else "normal")
    if body3:
        ax.text(0.5, 0.10, body3, ha="center", va="center",
                fontsize=8, color=TEXT3, fontfamily="monospace")


# ── Frame builder ───────────────────────────────────────────────────────────

def _tl_build_frame(ev, source_lines, total_evs,
                    cum_vars, cum_structs, cum_stdout, cur_line, changed_keys):
    ev_t     = ev.get("event", "line_execute")
    ev_color = _EV_COLORS_TL.get(ev_t, CYAN)
    ev_label = _EV_LABEL.get(ev_t, ev_t.upper())
    seq      = ev.get("seq", 0)
    note     = ev.get("code", ev.get("expression", ev.get("text", "")))

    fig = plt.figure(figsize=(16, 9.12), dpi=100, facecolor=BG)
    _ensure_912(fig)

    is_line = (ev_t == "line_execute")

    if is_line:
        gs = GridSpec(4, 2, figure=fig,
                      left=0.03, right=0.97, top=0.92, bottom=0.05,
                      hspace=0.42, wspace=0.06,
                      height_ratios=[2.5, 1.6, 1.6, 0.8])
        ax_code   = fig.add_subplot(gs[:, 0])
        ax_vars   = fig.add_subplot(gs[0, 1])
        ax_struct = fig.add_subplot(gs[1:3, 1])
        ax_stack  = fig.add_subplot(gs[3, 1])

        _tl_code_panel(ax_code, source_lines, cur_line, ev_color)
        _tl_vars_mini(ax_vars, cum_vars, changed_keys, ev_color, cum_stdout)

        # Structures (empty for timeline mode — no detector hooked in)
        _tl_panel(ax_struct, "Data Structures", BORDER)
        ax_struct.set_xlim(0, 1); ax_struct.set_ylim(0, 1); ax_struct.axis("off")
        if cum_structs:
            _draw_structures(ax_struct, cum_structs[:3])
        else:
            ax_struct.text(0.5, 0.5, "Structures appear as code runs",
                           ha="center", va="center", color=TEXT3,
                           fontsize=9, transform=ax_struct.transAxes)

        # Call stack
        _tl_panel(ax_stack, "Call Stack", BORDER)
        ax_stack.set_xlim(0, 1); ax_stack.set_ylim(-0.5, 0.5)
        ax_stack.text(0.03, 0,
                      f"▶  <module>()  — line {cur_line}",
                      va="center", color=ev_color,
                      fontsize=8.5, fontfamily="monospace", fontweight="bold")

    else:
        gs = GridSpec(1, 2, figure=fig,
                      left=0.03, right=0.97, top=0.92, bottom=0.05,
                      wspace=0.05, width_ratios=[1.1, 0.9])
        ax_code  = fig.add_subplot(gs[0])
        ax_event = fig.add_subplot(gs[1])

        _tl_code_panel(ax_code, source_lines, cur_line, ev_color)
        _tl_render_event_card(ax_event, ev, ev_color, cum_vars)

    _tl_title_bar(fig, ev_t, ev_label, seq, total_evs, ev_color, note)

    frame = _fig_to_rgb(fig)
    plt.close(fig)
    return _tl_norm(frame)


# ── Public API ──────────────────────────────────────────────────────────────

def generate_video_from_timeline(
    timeline_result: dict,
    source: str,
    language: str,
    mode: str,
    output_path: str | None = None,
) -> str:
    """
    Build an MP4 from a rich timeline (output of TimelineGenerator).
    Each event type gets its own dedicated animated frame.

    Returns the path to the written .mp4 file.
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        output_path = tmp.name
        tmp.close()

    source_lines = source.splitlines()
    tl           = timeline_result.get("timeline", [])
    final_stdout = timeline_result.get("stdout", "")
    error        = timeline_result.get("error")

    # Drop final_output — handled by end frame
    events = [e for e in tl if e.get("event") != "final_output"]
    total_evs = len(events)

    # Cumulative state
    cum_vars     : dict = {}
    cum_structs  : list = []
    cum_stdout   : str  = ""
    cur_line     : int  = 1
    changed_keys : set  = set()

    def _update(ev):
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
                base = name.split("[")[0]
                cum_vars[base] = ev.get("new_value", cum_vars.get(base, ""))
                changed_keys.add(base)
        elif ev_t in ("array_update", "array_append", "array_pop", "matrix_cell_update"):
            changed_keys.add(ev.get("var", ""))
        elif ev_t == "output":
            text = ev.get("text", "")
            cum_stdout = (cum_stdout + "\n" + text).strip()

    all_frames: list[np.ndarray] = []

    # Intro (3 s)
    all_frames.extend([_tl_norm(_render_title_frame(language, mode, total_evs))] * (FPS * 3))

    for ev in events:
        _update(ev)

        ev_t   = ev.get("event", "line_execute")
        secs   = _EV_SECS.get(ev_t, 1.0)
        n_frms = max(1, round(secs * FPS))

        frame = _tl_build_frame(
            ev, source_lines, total_evs,
            cum_vars, cum_structs, cum_stdout,
            cur_line, changed_keys,
        )
        all_frames.extend([frame] * n_frms)

    # End frame (4 s)
    all_frames.extend([_tl_norm(_render_end_frame(final_stdout, error))] * (FPS * 4))

    iio.imwrite(output_path, all_frames,
                fps=FPS, codec="libx264", quality=8, macro_block_size=16)
    return output_path
