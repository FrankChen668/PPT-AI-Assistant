#!/usr/bin/env python3
"""Shared standards (SSOT) used by QA/finalize/export adapters.

This module is the local single source of truth for:
- Canvas formats (synced with ppt-ai-core config/references)
- SVG banned elements/attributes/patterns used by compatibility checks
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CanvasSpec:
    key: str
    width: int
    height: int
    viewbox: str
    ratio: str


CANVAS_SPECS: dict[str, CanvasSpec] = {
    "ppt169": CanvasSpec("ppt169", 1280, 720, "0 0 1280 720", "16:9"),
    "ppt43": CanvasSpec("ppt43", 1024, 768, "0 0 1024 768", "4:3"),
    "wechat": CanvasSpec("wechat", 900, 383, "0 0 900 383", "2.35:1"),
    "xiaohongshu": CanvasSpec("xiaohongshu", 1242, 1660, "0 0 1242 1660", "3:4"),
    "moments": CanvasSpec("moments", 1080, 1080, "0 0 1080 1080", "1:1"),
    "story": CanvasSpec("story", 1080, 1920, "0 0 1080 1920", "9:16"),
    "banner": CanvasSpec("banner", 1920, 1080, "0 0 1920 1080", "16:9"),
    "a4": CanvasSpec("a4", 1240, 1754, "0 0 1240 1754", "1:sqrt(2)"),
}

CANVAS_ALIASES: dict[str, str] = {
    "xhs": "xiaohongshu",
    "wechat_moment": "moments",
    "wechat-moment": "moments",
    "xiaohongshu": "xiaohongshu",
    "ppt16:9": "ppt169",
    "16:9": "ppt169",
    "4:3": "ppt43",
}

DEFAULT_CANVAS_KEY = "ppt169"

# Based on ppt-ai-core references/shared-standards.md + scripts/config.py
FORBIDDEN_ELEMENTS: set[str] = {
    "clipPath",
    "mask",
    "style",
    "foreignObject",
    "symbol",
    "textPath",
    "animate",
    "animateMotion",
    "animateTransform",
    "animateColor",
    "set",
    "script",
    "marker",
    "iframe",
}

FORBIDDEN_ATTRIBUTES: set[str] = {
    "class",
    "onclick",
    "onload",
    "onmouseover",
    "onmouseout",
    "onfocus",
    "onblur",
    "onchange",
}

FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"@font-face", re.IGNORECASE),
    re.compile(r"rgba\s*\(", re.IGNORECASE),
    re.compile(r"<\?xml-stylesheet\b", re.IGNORECASE),
    re.compile(r"<link[^>]*rel\s*=\s*[\"']stylesheet[\"']", re.IGNORECASE),
    re.compile(r"@import\s+", re.IGNORECASE),
    re.compile(r"<g[^>]*\sopacity\s*=", re.IGNORECASE),
    re.compile(r"<image[^>]*\sopacity\s*=", re.IGNORECASE),
    re.compile(r"\bon\w+\s*=", re.IGNORECASE),
)


def normalize_canvas_key(raw: str | None) -> str:
    if not raw:
        return DEFAULT_CANVAS_KEY
    key = raw.strip().lower()
    return CANVAS_ALIASES.get(key, key)


def get_canvas_spec(canvas_key: str | None = None) -> CanvasSpec:
    key = normalize_canvas_key(canvas_key)
    return CANVAS_SPECS.get(key, CANVAS_SPECS[DEFAULT_CANVAS_KEY])

