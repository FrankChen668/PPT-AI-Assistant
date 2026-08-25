"""Line chart SVG fragment."""

from __future__ import annotations

from .svg_fragments import esc, pick_color


def _points(values: list[float], width: int, height: int, *, top: float, bottom: float) -> list[tuple[float, float]]:
    if not values:
        return []
    if len(values) == 1:
        return [(width / 2.0, bottom)]
    max_v = max(values)
    min_v = min(values)
    span = max(1e-6, max_v - min_v)
    left = 12.0
    right = width - 12.0
    step = (right - left) / max(1, len(values) - 1)
    out: list[tuple[float, float]] = []
    for idx, value in enumerate(values):
        x = left + step * idx
        ratio = (value - min_v) / span
        y = bottom - (bottom - top) * ratio
        out.append((x, y))
    return out


def render_line_chart_fragment(
    *,
    values: list[float] | tuple[float, ...],
    labels: list[str] | tuple[str, ...],
    width: int = 420,
    height: int = 220,
    data_palette: tuple[str, ...] | list[str] = (),
    title: str | None = None,
) -> str:
    vals = [float(v) for v in values]
    names = [str(item) for item in labels]
    count = max(1, min(len(vals), len(names)))
    vals = vals[:count]
    names = names[:count]

    w = max(200, int(width))
    h = max(140, int(height))
    top = 30.0 if title else 12.0
    bottom = h - 26.0
    color = pick_color(data_palette, 0, fallback="#8b1a35")
    pts = _points(vals, w, h, top=top, bottom=bottom)
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)

    parts: list[str] = ['<g data-chart-fragment="line">']
    if title:
        parts.append(f'<text x="8" y="16" font-size="13" fill="#475467">{esc(title)}</text>')
    parts.append(f'<polyline points="{polyline}" fill="none" stroke="{color}" stroke-width="2"/>')
    for idx, (x, y) in enumerate(pts):
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="{color}"/>')
        parts.append(
            f'<text x="{x:.2f}" y="{bottom + 14:.2f}" font-size="11" '
            f'text-anchor="middle" fill="#475467">{esc(names[idx])}</text>'
        )
    parts.append("</g>")
    return "".join(parts)
