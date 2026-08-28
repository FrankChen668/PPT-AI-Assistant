"""KPI card SVG fragment."""

from __future__ import annotations

from .svg_fragments import esc, pick_color


def render_kpi_card_fragment(
    *,
    value: str,
    label: str,
    width: int = 280,
    height: int = 140,
    data_palette: tuple[str, ...] | list[str] = (),
    title: str | None = None,
) -> str:
    w = max(120, int(width))
    h = max(80, int(height))
    primary = pick_color(data_palette, 0, fallback="#8b1a35")
    muted = pick_color(data_palette, 1, fallback="#667085")
    title_block = f'<text x="16" y="24" font-size="13" fill="{muted}">{esc(title)}</text>' if title else ""
    value_y = 66 if title else 56
    label_y = min(h - 18, value_y + 34)
    return (
        f'<g data-chart-fragment="kpi-card">'
        f'<rect x="0" y="0" width="{w}" height="{h}" rx="8" fill="#ffffff" stroke="#e3e7ed" stroke-width="1"/>'
        f"{title_block}"
        f'<text x="16" y="{value_y}" font-size="36" font-weight="700" fill="{primary}">{esc(str(value))}</text>'
        f'<text x="16" y="{label_y}" font-size="14" fill="{muted}">{esc(label)}</text>'
        f"</g>"
    )
