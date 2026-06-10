"""Append missing frame-assembly code to video_renderer.py"""
APPEND = """
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
"""

with open(
    r"c:\\Users\\MAUSAMI\\OneDrive\\Desktop\\Tracex\\TraceX-Code-Execution-Visualizer\\components\\video_renderer.py",
    "a",
    encoding="utf-8",
) as f:
    f.write(APPEND)

print("Done — appended frame assembly code")
