"""Primitives for deterministic SVG fragment generation."""

from __future__ import annotations

from html import escape

DEFAULT_PALETTE = ("#8b1a35", "#1e3a5f", "#2e8b57", "#d4ac0d")


def pick_color(data_palette: tuple[str, ...] | list[str], index: int, *, fallback: str) -> str:
    colors = tuple(item.strip().lower() for item in data_palette if isinstance(item, str) and item.strip())
    if not colors:
        colors = DEFAULT_PALETTE
    if not colors:
        return fallback
    return colors[index % len(colors)]


def esc(value: str) -> str:
    return escape(value, quote=True)
