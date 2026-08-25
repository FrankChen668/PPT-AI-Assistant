"""Bar chart SVG fragment."""

from __future__ import annotations

from .svg_fragments import esc, pick_color


def render_bar_chart_fragment(
    *,
    values: list[float] | tuple[float, ...],
    labels: list[str] | tuple[str, ...],
    width: int = 420,
    height: int = 220,
    data_palette: tuple[str, ...] | list[str] = (),
    title: str | None = None,
) -> str:
    bars = [float(v) for v in values]
    names = [str(item) for item in labels]
    count = max(1, min(len(bars), len(names)))
    bars = bars[:count]
    names = names[:count]

    w = max(200, int(width))
    h = max(140, int(height))
    chart_top = 30 if title else 12
    chart_bottom = h - 26
    chart_h = max(20.0, float(chart_bottom - chart_top))
    max_val = max(max(bars), 1.0)
    gap = 14.0
    avail = w - 24.0
    bar_w = max(8.0, (avail - gap * (count - 1)) / count)

    parts: list[str] = ['<g data-chart-fragment="bar">']
    if title:
        parts.append(f'<text x="8" y="16" font-size="13" fill="#475467">{esc(title)}</text>')
    parts.append(
        f'<line x1="8" y1="{chart_bottom}" x2="{w - 8}" y2="{chart_bottom}" stroke="#d0d5dd" stroke-width="1"/>'
    )
    for idx in range(count):
        value = bars[idx]
        x = 12.0 + idx * (bar_w + gap)
        bar_h = 0.0 if max_val <= 0 else chart_h * (value / max_val)
        y = chart_bottom - bar_h
        color = pick_color(data_palette, idx, fallback="#8b1a35")
        parts.append(
            f'<rect data-role="bar" x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" '
            f'rx="3" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x + (bar_w / 2):.2f}" y="{chart_bottom + 14:.2f}" '
            f'font-size="11" text-anchor="middle" fill="#475467">{esc(names[idx])}</text>'
        )
    parts.append("</g>")
    return "".join(parts)
