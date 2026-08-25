# Chart Fragments (SVG)

This folder provides small deterministic chart fragments for Executor embedding.

- `kpi_card.py`
- `bar_chart.py`
- `line_chart.py`
- `sparkline.py`

Usage pattern:

```python
from charts.bar_chart import render_bar_chart_fragment

fragment = render_bar_chart_fragment(
    values=[12, 34, 20],
    labels=["A", "B", "C"],
    width=420,
    height=220,
    data_palette=("#8b1a35", "#1e3a5f", "#2e8b57"),
    title="Monthly trend",
)
```

Then place the returned `<g data-chart-fragment="...">...</g>` inside slide SVG authored by Executor.

Notes:

- These helpers are optional sidecars; they do **not** replace full-slide Executor composition.
- Keep `foreignObject` disabled and use native SVG text/primitives only.
