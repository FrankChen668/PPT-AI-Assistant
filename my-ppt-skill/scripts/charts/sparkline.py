"""Sparkline SVG fragment."""

from __future__ import annotations

from .svg_fragments import pick_color


def render_sparkline_fragment(
    *,
    values: list[float] | tuple[float, ...],
    width: int = 180,
    height: int = 54,
    data_palette: tuple[str, ...] | list[str] = (),
) -> str:
    vals = [float(v) for v in values]
    if not vals:
        vals = [0.0]
    w = max(60, int(width))
    h = max(24, int(height))
    left, right = 4.0, float(w - 4)
    top, bottom = 4.0, float(h - 6)
    max_v = max(vals)
    min_v = min(vals)
    span = max(1e-6, max_v - min_v)
    step = (right - left) / max(1, len(vals) - 1)
    points = []
    for idx, value in enumerate(vals):
        x = left + step * idx
        y = bottom - ((value - min_v) / span) * (bottom - top)
        points.append((x, y))
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    color = pick_color(data_palette, 0, fallback="#2e8b57")
    return (
        f'<g data-chart-fragment="sparkline">'
        f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>'
        f'<circle cx="{points[-1][0]:.2f}" cy="{points[-1][1]:.2f}" r="2.5" fill="{color}"/>'
        f"</g>"
    )
