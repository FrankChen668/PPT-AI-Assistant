"""Small SVG chart fragment library for Executor-side embedding."""

from .bar_chart import render_bar_chart_fragment
from .kpi_card import render_kpi_card_fragment
from .line_chart import render_line_chart_fragment
from .sparkline import render_sparkline_fragment

__all__ = [
    "render_kpi_card_fragment",
    "render_bar_chart_fragment",
    "render_line_chart_fragment",
    "render_sparkline_fragment",
]
