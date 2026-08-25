#!/usr/bin/env python3
"""Layout lint checks for AI-authored SVG slides.

This script provides a lightweight pre-export gate between State 3 and State 4:
- text box overlap checks (text-vs-text)
- canvas and safe-area boundary checks
- optional copyfit checks driven by slide_plan.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from path_bootstrap import ensure_scripts_path  # noqa: E402

SCRIPT_DIR = ensure_scripts_path(Path(__file__))

from canvas_context import CanvasContext, load_canvas_context  # noqa: E402
from profile_policy import resolve_profile_policy  # noqa: E402
from render_theme import visual_width  # noqa: E402

TEXT_TAGS = {"text", "tspan"}
CONCLUSION_ANCHOR_RE = re.compile(r"(最终价值|最终结论|关键结论|结论：|Conclusion|Final Value)", re.IGNORECASE)
ENGINE_TITLE_RE = re.compile(r"(证明链引擎|追溯引擎|引擎|Engine|Proof Chain)", re.IGNORECASE)
TRANSLATE_RE = re.compile(
    r"translate\(\s*([-+]?(?:\d+(?:\.\d+)?|\.\d+))(?:[\s,]+([-+]?(?:\d+(?:\.\d+)?|\.\d+)))?\s*\)"
)
SAFE_AREA_PROFILES: dict[str, dict[str, float]] = {
    "legacy": {"pad_x": 28.0, "pad_top": 28.0, "pad_bottom": 40.0},
    "presentation": {"pad_x": 24.0, "pad_top": 24.0, "pad_bottom": 20.0},
}
QUALITY_MODES = ("dev-fast", "release-safe", "premium")
@dataclass
class LintFinding:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class LayoutLintReport:
    project: str
    ok: bool
    errors: int
    warnings: int
    findings: list[LintFinding]
    metrics: dict[str, Any]
    advisories: int = 0


@dataclass
class TextBlock:
    svg_file: Path
    x: float
    y: float
    left: float
    top: float
    right: float
    bottom: float
    font_size: float
    lines: list[str]


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    text = value.strip().replace("px", "")
    try:
        return float(text)
    except ValueError:
        return default


def parse_translate(transform: str | None) -> tuple[float, float]:
    if not transform:
        return 0.0, 0.0
    dx = 0.0
    dy = 0.0
    for match in TRANSLATE_RE.finditer(transform):
        dx += float(match.group(1))
        dy += float(match.group(2) or 0.0)
    return dx, dy


def iter_text_elements_with_offsets(
    elem: ET.Element,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
):
    dx, dy = parse_translate(elem.get("transform"))
    next_x = offset_x + dx
    next_y = offset_y + dy
    if local_name(elem.tag) == "text":
        yield elem, next_x, next_y
    for child in elem:
        yield from iter_text_elements_with_offsets(child, next_x, next_y)


def emit(findings: list[LintFinding], severity: str, code: str, path: str, message: str) -> None:
    findings.append(LintFinding(severity, code, path, message))


def _normalize_quality_mode(value: str | None) -> str:
    mode = (value or "dev-fast").strip().lower()
    if mode not in QUALITY_MODES:
        return "dev-fast"
    return mode


def _classify_overflow_risk(ratio: float, profile: str) -> str | None:
    policy = resolve_profile_policy(profile)
    if ratio >= policy.overflow_risk_high_ratio:
        return "high"
    if ratio >= policy.overflow_risk_medium_ratio:
        return "medium"
    if ratio >= policy.overflow_risk_low_ratio:
        return "low"
    return None


def _overflow_severity_for_mode(risk_level: str, quality_mode: str) -> str:
    mode = _normalize_quality_mode(quality_mode)
    if risk_level == "low":
        return "advisory"
    if risk_level == "medium":
        return "warning"
    if risk_level == "high":
        # release-safe/premium warnings are blocking via strict_effective in caller.
        return "warning" if mode in {"dev-fast", "release-safe", "premium"} else "warning"
    return "warning"


def emit_quality(
    findings: list[LintFinding],
    path: str,
    quality_profile: str,
    code: str,
    message: str,
    *,
    severe: bool = False,
) -> None:
    if severe:
        severity = "error" if quality_profile == "strict" else "warning"
    else:
        severity = "advisory"
    emit(findings, severity, code, path, message)


def text_lines(elem: ET.Element) -> list[str]:
    tspans = [child for child in elem if local_name(child.tag) == "tspan"]
    if tspans:
        lines: list[str] = []
        current_parts: list[str] = []
        root_text = (elem.text or "").strip()
        if root_text:
            current_parts.append(root_text)
        for child in tspans:
            starts_new_line = any(child.get(attr) for attr in ("x", "y", "dy"))
            if starts_new_line and current_parts:
                line = "".join(current_parts).strip()
                if line:
                    lines.append(line)
                current_parts = []
            child_text = (child.text or "").strip()
            if child_text:
                current_parts.append(child_text)
            child_tail = (child.tail or "").strip()
            if child_tail:
                current_parts.append(child_tail)
        line = "".join(current_parts).strip()
        if line:
            lines.append(line)
        return lines
    value = (elem.text or "").strip()
    return [value] if value else []


def estimate_text_box(
    elem: ET.Element,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> tuple[float, float, float, float] | None:
    tspans = [child for child in elem if local_name(child.tag) == "tspan"]
    if tspans and any(any(child.get(attr) for attr in ("x", "y", "dy")) for child in tspans):
        anchor = elem.get("text-anchor", "start")
        inherited_font_size = number(elem.get("font-size"), 18)
        current_x = number(elem.get("x")) + offset_x
        current_y = number(elem.get("y")) + offset_y
        boxes: list[tuple[float, float, float, float]] = []
        root_text = (elem.text or "").strip()
        if root_text:
            boxes.append(_estimate_text_fragment_box(root_text, current_x, current_y, inherited_font_size, anchor))
        for child in tspans:
            if child.get("x") is not None:
                current_x = number(child.get("x")) + offset_x
            if child.get("y") is not None:
                current_y = number(child.get("y")) + offset_y
            elif child.get("dy") is not None:
                current_y += number(child.get("dy"))
            font_size = number(child.get("font-size"), inherited_font_size)
            child_text = (child.text or "").strip()
            if child_text:
                boxes.append(_estimate_text_fragment_box(child_text, current_x, current_y, font_size, anchor))
        if boxes:
            return (
                min(box[0] for box in boxes),
                min(box[1] for box in boxes),
                max(box[2] for box in boxes),
                max(box[3] for box in boxes),
            )

    lines = text_lines(elem)
    if not lines:
        return None
    x = number(elem.get("x")) + offset_x
    y = number(elem.get("y")) + offset_y
    font_size = number(elem.get("font-size"), 18)
    anchor = elem.get("text-anchor", "start")
    # Keep text bbox estimation aligned with export-side conservative width math.
    width = max(1.0, max(visual_width(line) * font_size * 0.78 for line in lines))
    # Use tighter single-line vertical bounds so normal line stacks are not over-counted as overlaps.
    line_height = font_size * 0.84
    height = max(line_height, len(lines) * line_height)
    top = y - font_size * 0.72
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return left, top, left + width, top + height


def _estimate_text_fragment_box(
    text: str,
    x: float,
    y: float,
    font_size: float,
    anchor: str,
) -> tuple[float, float, float, float]:
    width = max(1.0, visual_width(text) * font_size * 0.78)
    top = y - font_size * 0.72
    height = font_size * 0.84
    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return left, top, left + width, top + height


def parse_slide_plan(project_dir: Path, findings: list[LintFinding]) -> dict[int, list[dict[str, Any]]]:
    plan_path = project_dir / "slide_plan.json"
    if not plan_path.exists():
        return {}
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        emit(findings, "error", "invalid-slide-plan-json", str(plan_path), f"Could not parse JSON: {exc}")
        return {}

    if not isinstance(payload, dict):
        emit(findings, "error", "invalid-slide-plan-root", str(plan_path), "slide_plan.json root must be an object.")
        return {}

    slides = payload.get("slides")
    if slides is None:
        return {}
    if not isinstance(slides, list):
        emit(findings, "error", "invalid-slide-plan-slides", str(plan_path), "slides must be an array when provided.")
        return {}

    parsed: dict[int, list[dict[str, Any]]] = {}
    for idx, slide in enumerate(slides, start=1):
        path = f"{plan_path}/slides/{idx}"
        if not isinstance(slide, dict):
            emit(findings, "warning", "invalid-slide-plan-slide", path, "Each slide entry should be an object.")
            continue
        slide_id = slide.get("slide_id", slide.get("id"))
        if not isinstance(slide_id, int):
            emit(findings, "warning", "invalid-slide-plan-id", path, "slide id should be an integer.")
            continue
        blocks = slide.get("blocks", [])
        if not isinstance(blocks, list):
            emit(findings, "warning", "invalid-slide-plan-blocks", path, "blocks should be an array.")
            continue
        valid_blocks: list[dict[str, Any]] = []
        for bidx, block in enumerate(blocks, start=1):
            bpath = f"{path}/blocks/{bidx}"
            if not isinstance(block, dict):
                emit(findings, "warning", "invalid-slide-plan-block", bpath, "block should be an object.")
                continue
            box = block.get("box")
            if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
                emit(findings, "warning", "invalid-slide-plan-box", bpath, "box should be [x, y, w, h] numbers.")
                continue
            required = {"id", "box", "max_lines", "font_size_range", "compress_rule"}
            missing_required = required - set(block)
            if missing_required:
                emit(
                    findings,
                    "error",
                    "missing-slide-plan-block-keys",
                    bpath,
                    f"Missing keys: {', '.join(sorted(missing_required))}.",
                )
                continue
            priority = block.get("priority")
            if priority is not None and priority not in {"must", "should", "can"}:
                emit(findings, "warning", "invalid-slide-plan-priority", bpath, "priority should be must|should|can.")
            compress_rule = block.get("compress_rule")
            if compress_rule is not None and compress_rule not in {"shorten", "drop_secondary", "split"}:
                emit(
                    findings,
                    "warning",
                    "invalid-slide-plan-compress-rule",
                    bpath,
                    "compress_rule should be shorten|drop_secondary|split.",
                )
            section = block.get("section")
            if section is not None and not (isinstance(section, str) and section.strip()):
                emit(findings, "warning", "invalid-slide-plan-section", bpath, "section should be a non-empty string.")
            valid_blocks.append(block)
        if valid_blocks:
            parsed[slide_id] = valid_blocks
    return parsed


def _boxes_overlap(a: TextBlock, b: TextBlock) -> bool:
    if _looks_like_stacked_lines(a, b):
        return False
    ix = min(a.right, b.right) - max(a.left, b.left)
    iy = min(a.bottom, b.bottom) - max(a.top, b.top)
    return ix > 6 and iy > 4


def _looks_like_stacked_lines(a: TextBlock, b: TextBlock) -> bool:
    """Suppress false-positive overlaps between adjacent wrapped lines in one column."""
    if len(a.lines) != 1 or len(b.lines) != 1:
        return False
    if abs(a.x - b.x) > 10:
        return False
    dy = abs(a.y - b.y)
    fs = max(a.font_size, b.font_size)
    if dy < fs * 0.65 or dy > fs * 1.45:
        return False
    x_overlap = min(a.right, b.right) - max(a.left, b.left)
    min_width = min(a.right - a.left, b.right - b.left)
    if min_width <= 1:
        return False
    return x_overlap / min_width >= 0.6


def _inside_box(cx: float, cy: float, box: list[float]) -> bool:
    x, y, w, h = box
    return x <= cx <= x + w and y <= cy <= y + h


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _text_payload(block: TextBlock) -> str:
    return " ".join(line.strip() for line in block.lines if line.strip())


def _check_anchor_integrity(
    texts: list[TextBlock],
    svg_file: Path,
    findings: list[LintFinding],
    canvas: CanvasContext,
) -> None:
    if not texts:
        return

    # Conclusion anchors should stay inside the footer band.
    for block in texts:
        payload = _text_payload(block)
        if not payload or not CONCLUSION_ANCHOR_RE.search(payload):
            continue
        cy = (block.top + block.bottom) / 2.0
        if cy < (canvas.footer_start - 18.0):
            emit(
                findings,
                "warning",
                "layout-anchor-conclusion-outside-footer",
                str(svg_file),
                (
                    "Conclusion-style sentence appears above footer anchor band "
                    f"(center_y={cy:.1f}, footer_start={canvas.footer_start:.1f})."
                ),
            )

    # Engine-style hub titles should be in the center stage and top band of body area.
    engine_candidates = [
        block
        for block in texts
        if ENGINE_TITLE_RE.search(_text_payload(block))
        and block.font_size >= 24
        and len(_text_payload(block)) <= 40
    ]
    if not engine_candidates:
        return
    focus = max(engine_candidates, key=lambda item: item.font_size)
    cx = (focus.left + focus.right) / 2.0
    cy = (focus.top + focus.bottom) / 2.0
    center_left = canvas.safe_x + canvas.safe_w / 3.0 - 40.0
    center_right = canvas.safe_x + 2.0 * canvas.safe_w / 3.0 + 40.0
    top_band_min = canvas.safe_y + 90.0
    top_band_max = canvas.safe_y + 230.0
    if not (center_left <= cx <= center_right and top_band_min <= cy <= top_band_max):
        emit(
            findings,
            "warning",
            "layout-anchor-engine-title-misaligned",
            str(svg_file),
            (
                "Engine hub title appears away from center-top anchor zone "
                f"(center=({cx:.1f},{cy:.1f}), expected x=[{center_left:.1f},{center_right:.1f}] "
                f"y=[{top_band_min:.1f},{top_band_max:.1f}])."
            ),
        )


def _check_copyfit_budget(
    blocks: list[dict[str, Any]],
    text_blocks: list[TextBlock],
    svg_file: Path,
    findings: list[LintFinding],
    metrics: dict[str, int],
    *,
    profile: str,
    quality_mode: str,
) -> None:
    for item in text_blocks:
        cx = (item.left + item.right) / 2
        cy = (item.top + item.bottom) / 2
        for block in blocks:
            box = block.get("box")
            if not isinstance(box, list):
                continue
            if not _inside_box(cx, cy, box):
                continue
            max_lines = block.get("max_lines")
            if isinstance(max_lines, int) and max_lines > 0:
                lines_ratio = len(item.lines) / float(max_lines)
                lines_risk = _classify_overflow_risk(lines_ratio, profile)
                if lines_risk:
                    metrics[f"overflow_risk_{lines_risk}_count"] += 1
                    emit(
                        findings,
                        _overflow_severity_for_mode(lines_risk, quality_mode),
                        f"overflow-risk-{lines_risk}",
                        str(svg_file),
                        (
                            "Copyfit lines risk in constrained block "
                            f"(lines={len(item.lines)}, max_lines={max_lines}, ratio={lines_ratio:.2f})."
                        ),
                    )
            max_chars = block.get("max_chars_per_line")
            if isinstance(max_chars, int):
                longest = max((len(line) for line in item.lines), default=0)
                if max_chars > 0:
                    chars_ratio = longest / float(max_chars)
                    chars_risk = _classify_overflow_risk(chars_ratio, profile)
                else:
                    chars_ratio = 0.0
                    chars_risk = None
                if chars_risk:
                    metrics[f"overflow_risk_{chars_risk}_count"] += 1
                    emit(
                        findings,
                        _overflow_severity_for_mode(chars_risk, quality_mode),
                        f"overflow-risk-{chars_risk}",
                        str(svg_file),
                        (
                            "Copyfit chars risk in constrained block "
                            f"(longest_chars={longest}, max_chars_per_line={max_chars}, ratio={chars_ratio:.2f})."
                        ),
                    )
            font_range = block.get("font_size_range")
            if (
                isinstance(font_range, list)
                and len(font_range) == 2
                and all(isinstance(v, (int, float)) for v in font_range)
            ):
                low, high = float(font_range[0]), float(font_range[1])
                if item.font_size < low or item.font_size > high:
                    emit(
                        findings,
                        "warning",
                        "copyfit-font-range",
                        str(svg_file),
                        f"font-size={item.font_size:g}px outside block range [{low:g}, {high:g}]px.",
                    )
            box_width = float(box[2]) if isinstance(box, list) and len(box) == 4 else 0.0
            if box_width <= 360 and len(item.lines) == 1:
                line = item.lines[0]
                if _contains_cjk(line):
                    max_units = max(1.0, (max(40.0, box_width - 16.0)) / max(item.font_size * 0.92, 1.0))
                    line_units = visual_width(line)
                    narrow_ratio = line_units / max_units
                    narrow_risk = _classify_overflow_risk(narrow_ratio, profile)
                    if narrow_risk:
                        metrics[f"overflow_risk_{narrow_risk}_count"] += 1
                        emit(
                            findings,
                            _overflow_severity_for_mode(narrow_risk, quality_mode),
                            f"overflow-risk-{narrow_risk}",
                            str(svg_file),
                            (
                                "Detected narrow-column overflow risk for CJK single-line text "
                                f"(box_w={box_width:.1f}, line_units={line_units:.1f}, "
                                f"max_units={max_units:.1f}, ratio={narrow_ratio:.2f})."
                            ),
                        )
            break


def lint_svg_file(
    svg_file: Path,
    findings: list[LintFinding],
    canvas: CanvasContext,
    slide_plan_blocks: list[dict[str, Any]] | None = None,
    safe_area_profile: str = "legacy",
    safe_edge_whitelist: set[str] | None = None,
    profile: str = "presentation",
    quality_mode: str = "dev-fast",
) -> tuple[dict[str, int], list[TextBlock]]:
    metrics = {
        "text_nodes": 0,
        "text_overlap_pairs": 0,
        "text_outside_canvas": 0,
        "text_near_safe_edge": 0,
        "overflow_risk_high_count": 0,
        "overflow_risk_medium_count": 0,
        "overflow_risk_low_count": 0,
    }
    try:
        tree = ET.parse(svg_file)
    except Exception as exc:
        emit(findings, "error", "invalid-svg", str(svg_file), f"Could not parse SVG: {exc}")
        return metrics, []

    root = tree.getroot()
    if local_name(root.tag) != "svg":
        emit(findings, "error", "invalid-svg-root", str(svg_file), "Root element must be <svg>.")
        return metrics, []

    width = number(root.get("width"), canvas.width)
    height = number(root.get("height"), canvas.height)
    view_box = root.get("viewBox")
    if not math.isclose(width, canvas.width) or not math.isclose(height, canvas.height):
        emit(
            findings,
            "warning",
            "unexpected-canvas-size",
            str(svg_file),
            f"Expected {canvas.width:g}x{canvas.height:g}, got {width:g}x{height:g}.",
        )
    if view_box and view_box != canvas.viewbox:
        emit(
            findings,
            "warning",
            "unexpected-viewbox",
            str(svg_file),
            f"Expected viewBox {canvas.viewbox!r}, got {view_box!r}.",
        )

    safe_profile = SAFE_AREA_PROFILES.get(safe_area_profile, SAFE_AREA_PROFILES["legacy"])
    safe_left = canvas.safe_x - safe_profile["pad_x"]
    safe_right = canvas.safe_x + canvas.safe_w + safe_profile["pad_x"]
    safe_top = canvas.safe_y - safe_profile["pad_top"]
    safe_bottom = canvas.safe_y + canvas.safe_h + safe_profile["pad_bottom"]

    texts: list[TextBlock] = []
    for elem, offset_x, offset_y in iter_text_elements_with_offsets(root):
        box = estimate_text_box(elem, offset_x, offset_y)
        if box is None:
            continue
        lines = text_lines(elem)
        font_size = number(elem.get("font-size"), 18)
        x = number(elem.get("x")) + offset_x
        y = number(elem.get("y")) + offset_y
        left, top, right, bottom = box
        text_block = TextBlock(svg_file, x, y, left, top, right, bottom, font_size, lines)
        texts.append(text_block)
        metrics["text_nodes"] += 1

        if left < -2 or right > canvas.width + 2 or top < -2 or bottom > canvas.height + 2:
            metrics["text_outside_canvas"] += 1
            emit(
                findings,
                "error",
                "text-outside-canvas",
                str(svg_file),
                f"Text bbox outside canvas: left={left:.1f}, top={top:.1f}, right={right:.1f}, bottom={bottom:.1f}.",
            )
        elif left < safe_left or right > safe_right or top < safe_top or bottom > safe_bottom:
            metrics["text_near_safe_edge"] += 1
            cy = (top + bottom) / 2.0
            in_whitelist = False
            for region in safe_edge_whitelist or set():
                ranges = canvas.safe_edge_ranges().get(region)
                if ranges and ranges[0] <= cy <= ranges[1]:
                    in_whitelist = True
                    break
            emit(
                findings,
                "warning",
                "text-near-safe-edge-whitelist" if in_whitelist else "text-near-safe-edge",
                str(svg_file),
                f"Text near safe edge: left={left:.1f}, top={top:.1f}, right={right:.1f}, bottom={bottom:.1f}.",
            )

    for i, left_item in enumerate(texts):
        for right_item in texts[i + 1 :]:
            if _boxes_overlap(left_item, right_item):
                metrics["text_overlap_pairs"] += 1
                emit(
                    findings,
                    "error",
                    "text-overlap",
                    str(svg_file),
                    (
                        "Detected overlapping text boxes "
                        f"({left_item.left:.1f},{left_item.top:.1f},{left_item.right:.1f},{left_item.bottom:.1f}) "
                        "vs "
                        f"({right_item.left:.1f},{right_item.top:.1f},{right_item.right:.1f},{right_item.bottom:.1f})."
                    ),
                )

    if slide_plan_blocks:
        _check_copyfit_budget(
            slide_plan_blocks,
            texts,
            svg_file,
            findings,
            metrics,
            profile=profile,
            quality_mode=quality_mode,
        )
    _check_anchor_integrity(texts, svg_file, findings, canvas)

    return metrics, texts


def _evaluate_quality_metrics(
    all_text_blocks: list[TextBlock],
    findings: list[LintFinding],
    metrics: dict[str, Any],
    project_dir: Path,
    quality_profile: str,
    canvas: CanvasContext,
) -> None:
    if not all_text_blocks:
        return

    slide_groups: dict[str, list[TextBlock]] = {}
    for block in all_text_blocks:
        slide_groups.setdefault(str(block.svg_file), []).append(block)
    slide_count = max(1, len(slide_groups))
    metrics["quality_slide_count"] = slide_count

    safe_area = float(canvas.safe_w * canvas.safe_h * slide_count)
    total_text_area = sum(max(0.0, (b.right - b.left) * (b.bottom - b.top)) for b in all_text_blocks)
    density = total_text_area / safe_area if safe_area > 0 else 0.0
    metrics["text_density"] = round(density, 4)
    if density >= 0.30:
        emit_quality(
            findings,
            str(project_dir),
            quality_profile,
            "layout-quality-text-density",
            f"Text density is high ({density:.3f}); page may feel crowded.",
            severe=density >= 0.36,
        )

    split_y = canvas.safe_y + canvas.safe_h / 2.0
    vertical_ratios: list[float] = []
    for blocks in slide_groups.values():
        top_area = 0.0
        bottom_area = 0.0
        for block in blocks:
            area = max(0.0, (block.right - block.left) * (block.bottom - block.top))
            cy = (block.top + block.bottom) / 2.0
            if cy < split_y:
                top_area += area
            else:
                bottom_area += area
        min_area = max(1.0, min(top_area, bottom_area))
        vertical_ratios.append(max(top_area, bottom_area) / min_area)
    vertical_ratio = sum(vertical_ratios) / len(vertical_ratios)
    metrics["section_balance_vertical_ratio"] = round(vertical_ratio, 3)
    if vertical_ratio >= 2.4:
        emit_quality(
            findings,
            str(project_dir),
            quality_profile,
            "layout-quality-section-balance-vertical",
            f"Top/bottom load is imbalanced (ratio={vertical_ratio:.2f}).",
            severe=vertical_ratio >= 3.2,
        )

    col_edges = [
        canvas.safe_x,
        canvas.safe_x + canvas.safe_w / 3.0,
        canvas.safe_x + 2 * canvas.safe_w / 3.0,
        canvas.safe_x + canvas.safe_w,
    ]
    col_ratios: list[float] = []
    for blocks in slide_groups.values():
        col_areas = [0.0, 0.0, 0.0]
        for block in blocks:
            area = max(0.0, (block.right - block.left) * (block.bottom - block.top))
            cx = (block.left + block.right) / 2.0
            if cx < col_edges[1]:
                col_areas[0] += area
            elif cx < col_edges[2]:
                col_areas[1] += area
            else:
                col_areas[2] += area
        active_cols = [value for value in col_areas if value >= 1800.0]
        if len(active_cols) < 2:
            continue
        min_col = max(1.0, min(active_cols))
        col_ratios.append(max(active_cols) / min_col)
    col_ratio = (sum(col_ratios) / len(col_ratios)) if col_ratios else 1.0
    metrics["section_balance_cards_ratio"] = round(col_ratio, 3)
    metrics["section_balance_cards_sampled_slides"] = len(col_ratios)
    if col_ratio >= 2.6:
        emit_quality(
            findings,
            str(project_dir),
            quality_profile,
            "layout-quality-section-balance-cards",
            f"Three-column/card load is imbalanced (ratio={col_ratio:.2f}).",
            severe=col_ratio >= 3.6,
        )

    sizes = sorted(block.font_size for block in all_text_blocks if block.font_size > 0)
    if sizes:
        unique_sizes = sorted({round(v, 1) for v in sizes})
        body_candidates = [v for v in sizes if 11 <= v <= 16]
        body_size = body_candidates[len(body_candidates) // 2] if body_candidates else sizes[len(sizes) // 2]
        heading_size = max(sizes)
        heading_gap = heading_size - body_size
        metrics["hierarchy_font_unique_count"] = len(unique_sizes)
        metrics["hierarchy_heading_gap"] = round(heading_gap, 2)
        if len(unique_sizes) < 3 or heading_gap < 5.0:
            emit_quality(
                findings,
                str(project_dir),
                quality_profile,
                "layout-quality-hierarchy-strength",
                (
                    "Typography hierarchy is weak "
                    f"(unique_sizes={len(unique_sizes)}, heading_gap={heading_gap:.1f}px)."
                ),
                severe=(len(unique_sizes) < 2 or heading_gap < 3.5),
            )


def _slide_id_from_name(path: Path) -> int | None:
    match = re.match(r"slide_(\d+)\.svg$", path.name)
    if not match:
        return None
    return int(match.group(1))


def write_reports(report: LayoutLintReport, qa_dir: Path) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "layout-lint-report.json").write_text(
        json.dumps(
            {
                "project": report.project,
                "ok": report.ok,
                "errors": report.errors,
                "warnings": report.warnings,
                "advisories": report.advisories,
                "findings": [asdict(item) for item in report.findings],
                "metrics": report.metrics,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Layout Lint Report",
        "",
        f"- project: `{report.project}`",
        f"- ok: `{report.ok}`",
        f"- errors: `{report.errors}`",
        f"- warnings: `{report.warnings}`",
        f"- advisories: `{report.advisories}`",
        "",
        "## Metrics",
        "",
    ]
    for key, value in report.metrics.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No findings.")
    else:
        for item in report.findings:
            lines.append(f"- **{item.severity}** `{item.code}` at `{item.path}`: {item.message}")
    (qa_dir / "layout-lint-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_layout_lint(
    project_dir: Path,
    svg_dir_name: str = "svg_output",
    strict: bool = False,
    slide_id: int | None = None,
    quality_profile: str = "standard",
    safe_area_profile: str = "legacy",
    safe_edge_whitelist: set[str] | None = None,
    profile: str = "presentation",
    quality_mode: str = "dev-fast",
) -> LayoutLintReport:
    project_dir = project_dir.resolve()
    canvas = load_canvas_context(project_dir)
    svg_dir = project_dir / svg_dir_name
    findings: list[LintFinding] = []
    metrics: dict[str, Any] = {
        "svg_dir": str(svg_dir),
        "checked_slide": slide_id if slide_id is not None else "all",
        "slide_plan_present": (project_dir / "slide_plan.json").exists(),
        "layout_quality_profile": quality_profile,
        "quality_mode": _normalize_quality_mode(quality_mode),
        "profile": profile,
        "safe_area_profile": safe_area_profile,
        "canvas_key": canvas.key,
        "canvas_width": canvas.width,
        "canvas_height": canvas.height,
        "canvas_viewbox": canvas.viewbox,
        "svg_files": 0,
        "text_nodes": 0,
        "text_overlap_pairs": 0,
        "text_outside_canvas": 0,
        "text_near_safe_edge": 0,
        "overflow_risk_high_count": 0,
        "overflow_risk_medium_count": 0,
        "overflow_risk_low_count": 0,
    }
    all_text_blocks: list[TextBlock] = []
    if safe_edge_whitelist is None:
        safe_edge_whitelist = {"header", "footer"}

    if not svg_dir.exists():
        emit(findings, "error", "missing-svg-dir", str(svg_dir), "SVG directory does not exist.")
        report = LayoutLintReport(str(project_dir), False, 1, 0, findings, metrics)
        write_reports(report, project_dir / "qa")
        return report

    slide_plan = parse_slide_plan(project_dir, findings)
    files = sorted(svg_dir.glob("slide_*.svg"))
    if slide_id is not None:
        files = [path for path in files if path.name == f"slide_{slide_id:02d}.svg"]
    metrics["svg_files"] = len(files)
    if not files:
        emit(findings, "error", "no-svg-files", str(svg_dir), "No slide_*.svg files found for linting.")

    for svg_file in files:
        sid = _slide_id_from_name(svg_file)
        block_plan = slide_plan.get(sid or -1, [])
        file_metrics, text_blocks = lint_svg_file(
            svg_file,
            findings,
            canvas,
            block_plan,
            safe_area_profile=safe_area_profile,
            safe_edge_whitelist=safe_edge_whitelist,
            profile=profile,
            quality_mode=quality_mode,
        )
        all_text_blocks.extend(text_blocks)
        for key in (
            "text_nodes",
            "text_overlap_pairs",
            "text_outside_canvas",
            "text_near_safe_edge",
            "overflow_risk_high_count",
            "overflow_risk_medium_count",
            "overflow_risk_low_count",
        ):
            metrics[key] += file_metrics[key]

    _evaluate_quality_metrics(all_text_blocks, findings, metrics, project_dir, quality_profile, canvas)
    metrics["quality_warning_count"] = sum(
        1 for item in findings if item.code.startswith("layout-quality-") and item.severity == "warning"
    )
    metrics["quality_error_count"] = sum(
        1 for item in findings if item.code.startswith("layout-quality-") and item.severity == "error"
    )
    metrics["quality_advisory_count"] = sum(
        1 for item in findings if item.code.startswith("layout-quality-") and item.severity == "advisory"
    )

    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    advisories = sum(1 for item in findings if item.severity == "advisory")
    overflow_high = int(metrics.get("overflow_risk_high_count", 0))
    overflow_medium = int(metrics.get("overflow_risk_medium_count", 0))
    overflow_low = int(metrics.get("overflow_risk_low_count", 0))
    metrics["overflow_risk_total_count"] = overflow_high + overflow_medium + overflow_low
    metrics["overflow_risk_blocking_count"] = (
        overflow_high
        if _normalize_quality_mode(quality_mode) in {"release-safe", "premium"}
        else 0
    )
    metrics["quality_tiers"] = {
        "blocking": errors,
        "warning": warnings,
        "advisory": advisories,
    }
    mode = _normalize_quality_mode(quality_mode)
    overflow_blocked = mode in {"release-safe", "premium"} and overflow_high > 0
    ok = errors == 0 and (warnings == 0 if strict else True) and not overflow_blocked
    report = LayoutLintReport(str(project_dir), ok, errors, warnings, findings, metrics, advisories=advisories)
    write_reports(report, project_dir / "qa")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SVG layout lint checks before export.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--svg-dir", default="svg_output", help="Relative SVG directory to lint (default: svg_output).")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures.")
    parser.add_argument("--slide", type=int, help="Lint one slide id only.")
    parser.add_argument(
        "--quality-profile",
        choices=("standard", "strict"),
        default="standard",
        help="Layout quality severity profile for non-geometric metrics.",
    )
    parser.add_argument(
        "--safe-area-profile",
        choices=("legacy", "presentation"),
        default="legacy",
        help="Safe-area warning profile. presentation is stricter near slide edges.",
    )
    parser.add_argument(
        "--safe-edge-whitelist",
        default="header,footer",
        help="Comma-separated regions allowed near safe edge (header,footer).",
    )
    parser.add_argument(
        "--profile",
        choices=("presentation", "print_a4", "proposal_consulting"),
        default="presentation",
        help="Governance profile for overflow-risk thresholds.",
    )
    parser.add_argument(
        "--quality-mode",
        choices=QUALITY_MODES,
        default="dev-fast",
        help="Severity mode affecting overflow-risk blocking semantics.",
    )
    args = parser.parse_args(argv)

    report = run_layout_lint(
        args.project_dir,
        svg_dir_name=args.svg_dir,
        strict=args.strict,
        slide_id=args.slide,
        quality_profile=args.quality_profile,
        safe_area_profile=args.safe_area_profile,
        safe_edge_whitelist={token.strip() for token in args.safe_edge_whitelist.split(",") if token.strip()},
        profile=args.profile,
        quality_mode=args.quality_mode,
    )
    print(f"Layout lint {'passed' if report.ok else 'failed'}: errors={report.errors}, warnings={report.warnings}")
    print(Path(report.project) / "qa" / "layout-lint-report.md")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
