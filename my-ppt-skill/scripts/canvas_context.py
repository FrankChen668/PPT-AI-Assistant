#!/usr/bin/env python3
"""Canvas context helpers shared by lint/QA/export gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from config_registry import get_canvas_spec

_BASE_W = 1280.0
_BASE_H = 720.0
_BASE_SAFE_X = 60.0
_BASE_SAFE_Y = 60.0
_BASE_SAFE_W = 1160.0
_BASE_SAFE_H = 600.0
_BASE_HEADER_END = 40.0
_BASE_FOOTER_START = 652.0


@dataclass(frozen=True)
class CanvasContext:
    key: str
    width: float
    height: float
    viewbox: str
    safe_x: float
    safe_y: float
    safe_w: float
    safe_h: float
    header_start: float
    header_end: float
    footer_start: float
    footer_end: float

    def safe_edge_ranges(self) -> dict[str, tuple[float, float]]:
        return {
            "header": (self.header_start, self.header_end),
            "footer": (self.footer_start, self.footer_end),
        }


def _parse_canvas_key(design_spec: Path) -> str | None:
    if not design_spec.exists():
        return None
    try:
        text = design_spec.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    match = re.search(r"^\s*-\s*canvas\s*:\s*([^\s#]+)", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def load_canvas_context(project_dir: Path) -> CanvasContext:
    key = _parse_canvas_key(project_dir / "design_spec.md")
    spec = get_canvas_spec(key)
    width = float(spec.width)
    height = float(spec.height)

    safe_x = round(width * (_BASE_SAFE_X / _BASE_W), 2)
    safe_y = round(height * (_BASE_SAFE_Y / _BASE_H), 2)
    safe_w = round(width * (_BASE_SAFE_W / _BASE_W), 2)
    safe_h = round(height * (_BASE_SAFE_H / _BASE_H), 2)

    header_end = round(height * (_BASE_HEADER_END / _BASE_H), 2)
    footer_start = round(height * (_BASE_FOOTER_START / _BASE_H), 2)
    return CanvasContext(
        key=spec.key,
        width=width,
        height=height,
        viewbox=spec.viewbox,
        safe_x=safe_x,
        safe_y=safe_y,
        safe_w=safe_w,
        safe_h=safe_h,
        header_start=0.0,
        header_end=header_end,
        footer_start=footer_start,
        footer_end=height,
    )
