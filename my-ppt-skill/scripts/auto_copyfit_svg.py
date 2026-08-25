#!/usr/bin/env python3
"""Automatic copyfit guard for AI-authored SVG slides.

This utility applies a unified fit_text_block engine with optional slide_plan budgets,
then performs conservative fallback shrinking for overlap/safe-area risks.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPT_DIR))

from render_theme import SAFE_H, SAFE_W, SAFE_X, SAFE_Y, fit_text_block, visual_width  # noqa: E402

SAFE_AREA_PROFILES: dict[str, dict[str, float]] = {
    "legacy": {"pad_x": 28.0, "pad_top": 28.0, "pad_bottom": 40.0},
    "presentation": {"pad_x": 24.0, "pad_top": 24.0, "pad_bottom": 20.0},
}

COPYFIT_PROFILES: dict[str, dict[str, float | int | str]] = {
    "preserve-design": {
        "safe_area_profile": "legacy",
        "step": 1.0,
        "min_font_size": 15.0,
        "max_rounds": 4,
    },
    "balanced": {
        "safe_area_profile": "presentation",
        "step": 2.0,
        "min_font_size": 14.0,
        "max_rounds": 6,
    },
    "strict": {
        "safe_area_profile": "presentation",
        "step": 2.0,
        "min_font_size": 13.0,
        "max_rounds": 9,
    },
}


@dataclass
class CopyfitStats:
    scanned_files: int
    changed_files: int
    adjusted_text_nodes: int
    total_size_reduction: float
    report_path: Path


def _resolve_copyfit_config(
    profile: str,
    safe_area_profile: str | None,
    step: float | None,
    min_font_size: float | None,
    max_rounds: int | None,
) -> tuple[str, float, float, int]:
    base = COPYFIT_PROFILES.get(profile, COPYFIT_PROFILES["balanced"])
    resolved_safe = str(base["safe_area_profile"]) if safe_area_profile is None else safe_area_profile
    resolved_step = float(base["step"]) if step is None else step
    resolved_min = float(base["min_font_size"]) if min_font_size is None else min_font_size
    resolved_rounds = int(base["max_rounds"]) if max_rounds is None else max_rounds
    return resolved_safe, resolved_step, resolved_min, resolved_rounds


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    text = value.strip().replace("px", "")
    try:
        return float(text)
    except ValueError:
        return default


def _text_lines(elem: ET.Element) -> list[str]:
    tspans = [child for child in elem if _local_name(child.tag) == "tspan"]
    if tspans:
        lines = []
        for t in tspans:
            value = (t.text or "").strip()
            if value:
                lines.append(value)
        return lines
    value = (elem.text or "").strip()
    return [value] if value else []


def _set_text_lines(elem: ET.Element, x: float, lines: list[str], line_height: float) -> None:
    for child in list(elem):
        elem.remove(child)
    elem.text = lines[0] if lines else ""
    for line in lines[1:]:
        tspan = ET.SubElement(elem, "tspan")
        tspan.set("x", f"{x:g}")
        tspan.set("dy", f"{line_height:g}")
        tspan.text = line


def _extract_font_size(elem: ET.Element, default: float = 18.0) -> float:
    attr = elem.get("font-size")
    if attr:
        return _number(attr, default)
    style = elem.get("style") or ""
    for token in style.split(";"):
        if ":" not in token:
            continue
        key, value = token.split(":", 1)
        if key.strip() == "font-size":
            return _number(value.strip(), default)
    return default


def _set_font_size(elem: ET.Element, size: float) -> None:
    elem.set("font-size", f"{size:g}")
    style = elem.get("style")
    if not style:
        return
    parts = []
    updated = False
    for token in style.split(";"):
        if ":" not in token:
            if token.strip():
                parts.append(token.strip())
            continue
        key, value = token.split(":", 1)
        k = key.strip()
        v = value.strip()
        if k == "font-size":
            parts.append(f"font-size:{size:g}px")
            updated = True
        elif k:
            parts.append(f"{k}:{v}")
    if not updated:
        parts.append(f"font-size:{size:g}px")
    elem.set("style", "; ".join(parts))


def _estimate_box(elem: ET.Element, font_size: float) -> tuple[float, float, float, float] | None:
    lines = _text_lines(elem)
    if not lines:
        return None
    x = _number(elem.get("x"))
    y = _number(elem.get("y"))
    anchor = elem.get("text-anchor", "start")

    width = max(1.0, max(visual_width(line) * font_size * 1.00 for line in lines))
    height = max(font_size * 1.35, len(lines) * font_size * 1.35)
    top = y - font_size
    if anchor == "middle":
        left = x - width / 2.0
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return left, top, left + width, top + height


def _outside_safe_bounds(
    box: tuple[float, float, float, float],
    safe_left: float,
    safe_top: float,
    safe_right: float,
    safe_bottom: float,
) -> bool:
    left, top, right, bottom = box
    return left < safe_left or right > safe_right or top < safe_top or bottom > safe_bottom


def _boxes_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    ix = min(a[2], b[2]) - max(a[0], b[0])
    iy = min(a[3], b[3]) - max(a[1], b[1])
    return ix > 6 and iy > 4


def _contains_point(box: list[float], x: float, y: float) -> bool:
    bx, by, bw, bh = box
    return bx <= x <= bx + bw and by <= y <= by + bh


def _slide_id_from_name(path: Path) -> int | None:
    match = re.match(r"slide_(\d+)\.svg$", path.name)
    if not match:
        return None
    return int(match.group(1))


def _parse_slide_plan(project_dir: Path) -> dict[int, list[dict[str, object]]]:
    path = project_dir / "slide_plan.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    slides = payload.get("slides")
    if not isinstance(slides, list):
        return {}

    parsed: dict[int, list[dict[str, object]]] = {}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id", slide.get("id"))
        blocks = slide.get("blocks")
        if not isinstance(slide_id, int) or not isinstance(blocks, list):
            continue
        valid_blocks: list[dict[str, object]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            box = block.get("box")
            if not (
                isinstance(box, list)
                and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)
            ):
                continue
            valid_blocks.append(block)
        parsed[slide_id] = valid_blocks
    return parsed


def _matching_block(blocks: list[dict[str, object]], center_x: float, center_y: float) -> dict[str, object] | None:
    for block in blocks:
        box = block.get("box")
        if isinstance(box, list) and _contains_point(box, center_x, center_y):
            return block
    return None


def _block_index(blocks: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    indexed: dict[str, dict[str, object]] = {}
    for block in blocks:
        block_id = block.get("id", block.get("name"))
        if isinstance(block_id, str) and block_id.strip():
            indexed[block_id.strip()] = block
    return indexed


def _box_height(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[3] - box[1])


def _fit_svg_file(
    svg_file: Path,
    *,
    slide_blocks: list[dict[str, object]],
    safe_left: float,
    safe_top: float,
    safe_right: float,
    safe_bottom: float,
    step: float,
    min_font_size: float,
    max_rounds: int,
) -> tuple[bool, int, float, list[str]]:
    tree = ET.parse(svg_file)
    root = tree.getroot()
    changed = False
    adjusted_nodes = 0
    total_reduction = 0.0
    logs: list[str] = []

    text_elems: list[ET.Element] = []
    for elem in root.iter():
        if _local_name(elem.tag) != "text":
            continue
        lines = _text_lines(elem)
        if not lines:
            continue
        text_elems.append(elem)

    original_sizes: dict[int, float] = {}
    original_lines: dict[int, list[str]] = {}
    block_index = _block_index(slide_blocks)
    for elem in text_elems:
        original_sizes[id(elem)] = _extract_font_size(elem, default=18.0)
        original_lines[id(elem)] = _text_lines(elem)

    # Pass 1: fit with optional slide plan contract budgets.
    for elem in text_elems:
        start_size = _extract_font_size(elem, default=18.0)
        source_lines = _text_lines(elem)
        base_text = " ".join(line for line in source_lines if line).strip()
        if not base_text:
            continue

        box = _estimate_box(elem, start_size)
        if box is None:
            continue
        x = _number(elem.get("x"))
        center_x = (box[0] + box[2]) / 2.0
        center_y = (box[1] + box[3]) / 2.0

        slot_id = (elem.get("data-slot-id") or "").strip()
        matched_block = block_index.get(slot_id) if slot_id else None
        if matched_block is None:
            matched_block = _matching_block(slide_blocks, center_x, center_y)
        budget_width = max(40.0, box[2] - box[0])
        budget_lines = max(1, len(source_lines))
        budget_min_font = min_font_size
        budget_height: float | None = None
        if matched_block is not None:
            block_box = matched_block.get("box")
            if isinstance(block_box, list) and len(block_box) == 4:
                budget_width = max(40.0, float(block_box[2]) - 16.0)
                budget_height = max(18.0, float(block_box[3]) - 12.0)
            block_lines = matched_block.get("max_lines")
            if isinstance(block_lines, int) and block_lines > 0:
                budget_lines = block_lines
            font_range = matched_block.get("font_size_range")
            if (
                isinstance(font_range, list)
                and len(font_range) == 2
                and all(isinstance(v, (int, float)) for v in font_range)
            ):
                budget_min_font = max(budget_min_font, float(font_range[0]))

        fitted_lines, fitted_size = fit_text_block(
            base_text,
            max_width=budget_width,
            font_size=start_size,
            max_lines=budget_lines,
            min_font_size=budget_min_font,
            step=step,
            ellipsis=True,
        )
        if not fitted_lines:
            continue

        _set_text_lines(elem, x, fitted_lines, fitted_size * 1.35)
        _set_font_size(elem, fitted_size)
        elem.set("data-max-width", f"{budget_width:g}")
        elem.set("data-max-lines", str(budget_lines))
        if matched_block is not None:
            block_id = matched_block.get("id", matched_block.get("name"))
            if isinstance(block_id, str) and block_id.strip():
                elem.set("data-slot-id", block_id.strip())
        if budget_height is not None:
            elem.set("data-slot-height", f"{budget_height:g}")

        fitted_box = _estimate_box(elem, fitted_size)
        exceeds_box_height = (
            budget_height is not None
            and fitted_box is not None
            and _box_height(fitted_box) > budget_height
        )
        if fitted_box and (
            _outside_safe_bounds(fitted_box, safe_left, safe_top, safe_right, safe_bottom)
            or exceeds_box_height
        ):
            current_size = fitted_size
            for _ in range(max_rounds):
                if current_size <= budget_min_font:
                    break
                current_size = max(budget_min_font, current_size - step)
                retry_lines, retry_size = fit_text_block(
                    base_text,
                    max_width=budget_width,
                    font_size=current_size,
                    max_lines=budget_lines,
                    min_font_size=budget_min_font,
                    step=step,
                    ellipsis=True,
                )
                if not retry_lines:
                    continue
                _set_text_lines(elem, x, retry_lines, retry_size * 1.35)
                _set_font_size(elem, retry_size)
                fitted_box = _estimate_box(elem, retry_size)
                exceeds_box_height = (
                    budget_height is not None
                    and fitted_box is not None
                    and _box_height(fitted_box) > budget_height
                )
                if (
                    fitted_box
                    and not _outside_safe_bounds(
                        fitted_box, safe_left, safe_top, safe_right, safe_bottom
                    )
                    and not exceeds_box_height
                ):
                    break

        if fitted_size < start_size or fitted_lines != source_lines:
            changed = True

    # Pass 2: resolve text-vs-text overlaps by shrinking later blocks first.
    for _ in range(max_rounds):
        entries: list[tuple[int, ET.Element, float, tuple[float, float, float, float]]] = []
        for idx, elem in enumerate(text_elems):
            size = _extract_font_size(elem, default=18.0)
            box = _estimate_box(elem, size)
            if box is None:
                continue
            entries.append((idx, elem, size, box))

        overlap_indices: set[int] = set()
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if _boxes_overlap(entries[i][3], entries[j][3]):
                    overlap_indices.add(j)

        if not overlap_indices:
            break

        round_changed = False
        for idx in sorted(overlap_indices):
            _, elem, size, _ = entries[idx]
            if size <= min_font_size:
                continue
            new_size = max(min_font_size, size - step)
            if new_size < size:
                _set_font_size(elem, new_size)
                changed = True
                round_changed = True
        if not round_changed:
            break

    for elem in text_elems:
        before = original_sizes.get(id(elem), 18.0)
        after = _extract_font_size(elem, default=18.0)
        now_lines = _text_lines(elem)
        was_lines = original_lines.get(id(elem), [])
        if after < before:
            adjusted_nodes += 1
            reduction = before - after
            total_reduction += reduction
            preview = (now_lines[0] if now_lines else "").strip()[:28].replace("`", "'")
            logs.append(
                f"- `{svg_file.name}` text '{preview}' font-size {before:g} -> {after:g} (-{reduction:g})"
            )
        elif now_lines != was_lines:
            adjusted_nodes += 1
            preview = (now_lines[0] if now_lines else "").strip()[:28].replace("`", "'")
            logs.append(f"- `{svg_file.name}` text '{preview}' reflowed by fit_text_block")

    if changed:
        tree.write(svg_file, encoding="utf-8", xml_declaration=True)
    return changed, adjusted_nodes, total_reduction, logs


def run_auto_copyfit(
    project_dir: Path,
    *,
    profile: str = "balanced",
    svg_dir_name: str = "svg_output",
    safe_area_profile: str | None = None,
    step: float | None = None,
    min_font_size: float | None = None,
    max_rounds: int | None = None,
) -> CopyfitStats:
    project_dir = project_dir.resolve()
    svg_dir = project_dir / svg_dir_name
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_path = qa_dir / "copyfit-report.md"

    safe_area_profile, step, min_font_size, max_rounds = _resolve_copyfit_config(
        profile,
        safe_area_profile,
        step,
        min_font_size,
        max_rounds,
    )

    safe_cfg = SAFE_AREA_PROFILES.get(safe_area_profile, SAFE_AREA_PROFILES["presentation"])
    safe_left = SAFE_X - safe_cfg["pad_x"]
    safe_right = SAFE_X + SAFE_W + safe_cfg["pad_x"]
    safe_top = SAFE_Y - safe_cfg["pad_top"]
    safe_bottom = SAFE_Y + SAFE_H + safe_cfg["pad_bottom"]

    files = sorted(svg_dir.glob("slide_*.svg"))
    slide_plan = _parse_slide_plan(project_dir)
    changed_files = 0
    adjusted_nodes = 0
    total_reduction = 0.0
    log_lines: list[str] = []

    for svg_file in files:
        slide_id = _slide_id_from_name(svg_file)
        slide_blocks = slide_plan.get(slide_id, []) if slide_id is not None else []
        changed, node_count, reduction, file_logs = _fit_svg_file(
            svg_file,
            slide_blocks=slide_blocks,
            safe_left=safe_left,
            safe_top=safe_top,
            safe_right=safe_right,
            safe_bottom=safe_bottom,
            step=step,
            min_font_size=min_font_size,
            max_rounds=max_rounds,
        )
        if changed:
            changed_files += 1
        adjusted_nodes += node_count
        total_reduction += reduction
        log_lines.extend(file_logs)

    lines = [
        "# Copyfit Report",
        "",
        f"- project: `{project_dir}`",
        f"- svg_dir: `{svg_dir}`",
        f"- safe_area_profile: `{safe_area_profile}`",
        f"- profile: `{profile}`",
        f"- scanned_files: `{len(files)}`",
        f"- changed_files: `{changed_files}`",
        f"- adjusted_text_nodes: `{adjusted_nodes}`",
        f"- total_size_reduction: `{total_reduction:.1f}`",
        "",
        "## Adjustments",
        "",
    ]
    if log_lines:
        lines.extend(log_lines)
    else:
        lines.append("No adjustments.")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return CopyfitStats(
        scanned_files=len(files),
        changed_files=changed_files,
        adjusted_text_nodes=adjusted_nodes,
        total_size_reduction=total_reduction,
        report_path=report_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-shrink risky SVG text to reduce overflow issues.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--svg-dir", default="svg_output", help="Relative SVG directory (default: svg_output).")
    parser.add_argument(
        "--profile",
        choices=("preserve-design", "balanced", "strict"),
        default="balanced",
        help="Copyfit strategy profile.",
    )
    parser.add_argument(
        "--safe-area-profile",
        choices=("legacy", "presentation"),
        default=None,
        help="Safe-area profile used to decide shrink thresholds.",
    )
    parser.add_argument("--step", type=float, default=None, help="Font size decrement per round.")
    parser.add_argument("--min-font-size", type=float, default=None, help="Minimum font size limit.")
    parser.add_argument("--max-rounds", type=int, default=None, help="Maximum shrink rounds per text node.")
    args = parser.parse_args(argv)

    stats = run_auto_copyfit(
        args.project_dir,
        profile=args.profile,
        svg_dir_name=args.svg_dir,
        safe_area_profile=args.safe_area_profile,
        step=args.step,
        min_font_size=args.min_font_size,
        max_rounds=args.max_rounds,
    )
    print(
        "Copyfit auto-adjust complete: "
        f"changed_files={stats.changed_files}, adjusted_text_nodes={stats.adjusted_text_nodes}, "
        f"total_size_reduction={stats.total_size_reduction:.1f}"
    )
    print(stats.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
