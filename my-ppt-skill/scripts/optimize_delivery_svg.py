#!/usr/bin/env python3
"""Delivery-oriented SVG cleanup for external-facing decks.

Goals:
- remove internal/technical footer text (canvas size, font notes, etc.)
- normalize adjacent multi-line body text font sizes
- increase vertical divider contrast against row backgrounds
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

TECH_FOOTER_PATTERNS = [
    re.compile(r"16:9", re.IGNORECASE),
    re.compile(r"\bcm\b", re.IGNORECASE),
    re.compile(r"字体"),
    re.compile(r"咨询风能力蓝图页"),
]

DELIVERY_PROFILES: dict[str, dict[str, float | int | bool]] = {
    "preserve-design": {
        "normalize_fonts": False,
        "line_gap_threshold": 32.0,
        "font_delta_threshold": 1.8,
        "divider_darken_factor": 0.18,
        "divider_stroke_width": 1.0,
    },
    "balanced": {
        "normalize_fonts": True,
        "line_gap_threshold": 40.0,
        "font_delta_threshold": 1.5,
        "divider_darken_factor": 0.28,
        "divider_stroke_width": 1.2,
    },
    "strict": {
        "normalize_fonts": True,
        "line_gap_threshold": 56.0,
        "font_delta_threshold": 0.8,
        "divider_darken_factor": 0.38,
        "divider_stroke_width": 1.4,
    },
}


@dataclass
class DeliveryOptimizeStats:
    scanned_files: int
    changed_files: int
    removed_footer_nodes: int
    normalized_font_nodes: int
    divider_adjusted: int
    report_path: Path


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def _num(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    text = value.strip().replace("px", "")
    try:
        return float(text)
    except ValueError:
        return default


def _parse_hex(color: str) -> tuple[int, int, int] | None:
    value = color.strip()
    if not value.startswith("#"):
        return None
    raw = value[1:]
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return None
    try:
        return (int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError:
        return None


def _to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(color: str, factor: float = 0.22) -> str:
    parsed = _parse_hex(color)
    if parsed is None:
        return color
    r, g, b = parsed
    r = max(0, min(255, int(r * (1.0 - factor))))
    g = max(0, min(255, int(g * (1.0 - factor))))
    b = max(0, min(255, int(b * (1.0 - factor))))
    return _to_hex((r, g, b))


def _get_font_size(elem: ET.Element, default: float = 18.0) -> float:
    value = elem.get("font-size")
    if value:
        return _num(value, default)
    return default


def _text_content(elem: ET.Element) -> str:
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        if _local_name(child.tag) == "tspan" and child.text:
            parts.append(child.text)
    return "".join(parts).strip()


def _is_tech_footer_text(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in TECH_FOOTER_PATTERNS)


def _remove_tech_footers(root: ET.Element) -> int:
    removed = 0
    for parent in root.iter():
        children = list(parent)
        for child in children:
            if _local_name(child.tag) != "text":
                continue
            y = _num(child.get("y"), 0.0)
            if y < 620:
                continue
            text = _text_content(child)
            if _is_tech_footer_text(text):
                parent.remove(child)
                removed += 1
    return removed


def _normalize_adjacent_font_sizes(
    root: ET.Element,
    *,
    line_gap_threshold: float,
    font_delta_threshold: float,
) -> int:
    # Group text nodes by visual style and x position, then normalize adjacent lines.
    groups: dict[tuple[str, str, str, int], list[ET.Element]] = {}
    for elem in root.iter():
        if _local_name(elem.tag) != "text":
            continue
        x = int(round(_num(elem.get("x"), -9999)))
        fill = (elem.get("fill") or "").strip().lower()
        family = (elem.get("font-family") or "").strip().lower()
        weight = (elem.get("font-weight") or "").strip().lower()
        key = (fill, family, weight, x)
        groups.setdefault(key, []).append(elem)

    changed = 0
    for _, items in groups.items():
        items.sort(key=lambda e: _num(e.get("y"), 0.0))
        for i in range(len(items) - 1):
            a = items[i]
            b = items[i + 1]
            ya = _num(a.get("y"), 0.0)
            yb = _num(b.get("y"), 0.0)
            if yb - ya > line_gap_threshold:
                continue
            sa = _get_font_size(a)
            sb = _get_font_size(b)
            if abs(sa - sb) < font_delta_threshold:
                continue
            # Normalize to the first line size to keep paragraph consistency.
            b.set("font-size", f"{sa:g}")
            changed += 1
    return changed


def _boost_vertical_dividers(
    root: ET.Element,
    *,
    darken_factor: float,
    stroke_width: float,
) -> int:
    # Build a simple lookup of major layer rectangles.
    rects: list[tuple[float, float, float, float, str]] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "rect":
            continue
        x = _num(elem.get("x"), 0.0)
        y = _num(elem.get("y"), 0.0)
        w = _num(elem.get("width"), 0.0)
        h = _num(elem.get("height"), 0.0)
        if w < 600 or h < 90:
            continue
        fill = (elem.get("fill") or "").strip()
        rects.append((x, y, x + w, y + h, fill))

    adjusted = 0
    for elem in root.iter():
        if _local_name(elem.tag) != "line":
            continue
        x1 = _num(elem.get("x1"))
        x2 = _num(elem.get("x2"))
        y1 = _num(elem.get("y1"))
        y2 = _num(elem.get("y2"))
        if abs(x1 - x2) > 0.5:
            continue
        if abs(y2 - y1) < 60:
            continue
        midx = x1
        midy = (y1 + y2) / 2.0
        base_fill = None
        for lx, ty, rx, by, fill in rects:
            if lx <= midx <= rx and ty <= midy <= by:
                base_fill = fill
                break
        if not base_fill:
            continue
        stroke = _darken(base_fill, factor=darken_factor)
        elem.set("stroke", stroke)
        elem.set("stroke-opacity", "0.9")
        elem.set("stroke-width", f"{stroke_width:g}")
        adjusted += 1
    return adjusted


def optimize_svg_file(svg_file: Path, *, profile: str = "balanced") -> tuple[bool, int, int, int]:
    tree = ET.parse(svg_file)
    root = tree.getroot()
    cfg = DELIVERY_PROFILES.get(profile, DELIVERY_PROFILES["balanced"])
    line_gap_threshold = float(cfg["line_gap_threshold"])
    font_delta_threshold = float(cfg["font_delta_threshold"])
    darken_factor = float(cfg["divider_darken_factor"])
    stroke_width = float(cfg["divider_stroke_width"])

    removed = _remove_tech_footers(root)
    normalized = (
        _normalize_adjacent_font_sizes(
            root,
            line_gap_threshold=line_gap_threshold,
            font_delta_threshold=font_delta_threshold,
        )
        if bool(cfg["normalize_fonts"])
        else 0
    )
    dividers = _boost_vertical_dividers(root, darken_factor=darken_factor, stroke_width=stroke_width)
    changed = (removed + normalized + dividers) > 0
    if changed:
        tree.write(svg_file, encoding="utf-8", xml_declaration=True)
    return changed, removed, normalized, dividers


def run_delivery_optimize(
    project_dir: Path,
    svg_dir_name: str = "svg_output",
    profile: str = "balanced",
) -> DeliveryOptimizeStats:
    project_dir = project_dir.resolve()
    svg_dir = project_dir / svg_dir_name
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_path = qa_dir / "delivery-optimize-report.md"

    files = sorted(svg_dir.glob("slide_*.svg"))
    changed_files = 0
    removed_sum = 0
    normalized_sum = 0
    divider_sum = 0

    for path in files:
        changed, removed, normalized, dividers = optimize_svg_file(path, profile=profile)
        if changed:
            changed_files += 1
        removed_sum += removed
        normalized_sum += normalized
        divider_sum += dividers

    lines = [
        "# Delivery Optimize Report",
        "",
        f"- project: `{project_dir}`",
        f"- svg_dir: `{svg_dir}`",
        f"- scanned_files: `{len(files)}`",
        f"- profile: `{profile}`",
        f"- changed_files: `{changed_files}`",
        f"- removed_footer_nodes: `{removed_sum}`",
        f"- normalized_font_nodes: `{normalized_sum}`",
        f"- divider_adjusted: `{divider_sum}`",
        "",
        (
            "This pass removes technical footers, harmonizes adjacent body font "
            "sizes, and boosts vertical divider contrast."
        ),
    ]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return DeliveryOptimizeStats(
        scanned_files=len(files),
        changed_files=changed_files,
        removed_footer_nodes=removed_sum,
        normalized_font_nodes=normalized_sum,
        divider_adjusted=divider_sum,
        report_path=report_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optimize SVG slides for external delivery quality.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--svg-dir", default="svg_output", help="Relative SVG directory (default: svg_output).")
    parser.add_argument(
        "--profile",
        choices=("preserve-design", "balanced", "strict"),
        default="balanced",
        help="Delivery optimization profile.",
    )
    args = parser.parse_args(argv)

    stats = run_delivery_optimize(args.project_dir, svg_dir_name=args.svg_dir, profile=args.profile)
    print(
        "Delivery optimize complete: "
        f"changed_files={stats.changed_files}, removed_footer_nodes={stats.removed_footer_nodes}, "
        f"normalized_font_nodes={stats.normalized_font_nodes}, divider_adjusted={stats.divider_adjusted}"
    )
    print(stats.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
