from __future__ import annotations

import math
from typing import Any

SCENE_TO_LAYOUT = {
    "architecture_flow": "vertical_layers_with_side_panel",
    "roadmap": "horizontal_flow",
    "comparison": "center_radial",
    "core_orbit_relationship": "core_orbit",
}

_LAYOUT_TAG_TO_SCENE = {
    "Architecture-Three-Zones": "architecture_flow",
    "Roadmap-Lane-Milestones": "roadmap",
    "Comparison-Matrix-SummaryBar": "comparison",
}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resolve_scene_type(slide_dict: dict[str, Any], content: dict[str, Any]) -> str:
    scene_type = str(slide_dict.get("scene_type") or "").strip()
    if scene_type in SCENE_TO_LAYOUT:
        return scene_type

    layout_tag = str(slide_dict.get("layout_tag") or "").strip()
    inferred = _LAYOUT_TAG_TO_SCENE.get(layout_tag)
    if inferred:
        return inferred

    if _as_list(content.get("core_modules")):
        return "architecture_flow"
    if _as_list(content.get("phases")):
        return "roadmap"
    if _as_list(content.get("rows")):
        return "comparison"

    raise ValueError("unsupported scene_type")


def _validate_slots(slots: list[dict[str, Any]], canvas_w: int, canvas_h: int) -> None:
    for slot in slots:
        box = slot.get("box")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, int) for v in box)):
            raise RuntimeError(f"invalid slot box for {slot.get('block_id')}")
        x, y, w, h = box
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > canvas_w or y + h > canvas_h:
            raise RuntimeError(f"slot out of bounds for {slot.get('block_id')}")
    for idx, slot in enumerate(slots):
        ax, ay, aw, ah = slot["box"]
        for other in slots[idx + 1 :]:
            bx, by, bw, bh = other["box"]
            if min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by):
                raise RuntimeError(f"slot overlap: {slot.get('block_id')} vs {other.get('block_id')}")


def _string_slots(
    values: list[Any],
    *,
    prefix: str,
    x: int,
    y: int,
    width: int,
    height: int,
    gap: int,
    horizontal: bool,
    priority: str,
    section: str,
    max_lines: int,
    max_chars_per_line: int,
    font_size_range: list[int],
    compress_rule: str,
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    if not values:
        return slots
    for idx, _ in enumerate(values, start=1):
        slot_x = x + (idx - 1) * (width + gap) if horizontal else x
        slot_y = y if horizontal else y + (idx - 1) * (height + gap)
        slots.append(
            {
                "block_id": f"{prefix}-{idx}",
                "box": [slot_x, slot_y, width, height],
                "priority": priority,
                "section": section,
                "max_lines": max_lines,
                "max_chars_per_line": max_chars_per_line,
                "font_size_range": font_size_range,
                "compress_rule": compress_rule,
            }
        )
    return slots


def _vertical_layers_with_side_panel(content: dict[str, Any]) -> list[dict[str, Any]]:
    top_items = _as_list(content.get("left_systems"))
    core_items = _as_list(content.get("core_modules"))
    right_items = _as_list(content.get("right_modules"))
    bottom_items = _as_list(content.get("storage"))
    if not core_items:
        raise RuntimeError("slot calculation error: architecture_flow requires core_modules")
    if len(core_items) > 8 or len(right_items) > 6 or len(top_items) > 6 or len(bottom_items) > 8:
        raise RuntimeError("slot calculation error: architecture_flow content exceeds supported capacity")

    slots: list[dict[str, Any]] = []
    if top_items:
        top_gap = 12
        top_width = (840 - top_gap * (len(top_items) - 1)) // len(top_items)
        slots.extend(
            _string_slots(
                top_items,
                prefix="left_systems",
                x=72,
                y=152,
                width=top_width,
                height=40,
                gap=top_gap,
                horizontal=True,
                priority="should",
                section="top-band",
                max_lines=2,
                max_chars_per_line=12,
                font_size_range=[11, 16],
                compress_rule="drop_secondary",
            )
        )

    row_gap = 8
    core_height = 356
    row_height = (core_height - row_gap * (len(core_items) - 1)) // len(core_items)
    slots.extend(
        _string_slots(
            core_items,
            prefix="core_modules",
            x=72,
            y=204,
            width=840,
            height=row_height,
            gap=row_gap,
            horizontal=False,
            priority="must",
            section="core",
            max_lines=4,
            max_chars_per_line=24,
            font_size_range=[13, 19],
            compress_rule="shorten",
        )
    )

    if right_items:
        right_gap = 12
        right_height = (356 - right_gap * (len(right_items) - 1)) // len(right_items)
        slots.extend(
            _string_slots(
                right_items,
                prefix="right_modules",
                x=946,
                y=204,
                width=258,
                height=right_height,
                gap=right_gap,
                horizontal=False,
                priority="should",
                section="right-panel",
                max_lines=3,
                max_chars_per_line=12,
                font_size_range=[11, 15],
                compress_rule="drop_secondary",
            )
        )

    if bottom_items:
        bottom_gap = 10
        bottom_width = (1132 - bottom_gap * (len(bottom_items) - 1)) // len(bottom_items)
        slots.extend(
            _string_slots(
                bottom_items,
                prefix="storage",
                x=72,
                y=580,
                width=bottom_width,
                height=52,
                gap=bottom_gap,
                horizontal=True,
                priority="should",
                section="bottom-band",
                max_lines=2,
                max_chars_per_line=14,
                font_size_range=[11, 15],
                compress_rule="drop_secondary",
            )
        )
    return slots


def _horizontal_flow(content: dict[str, Any]) -> list[dict[str, Any]]:
    phase_items = _as_list(content.get("phases"))
    if not phase_items:
        raise RuntimeError("slot calculation error: roadmap requires phases")
    if len(phase_items) > 6:
        raise RuntimeError("slot calculation error: roadmap content exceeds supported capacity")

    gap = 36
    width = (1136 - gap * (len(phase_items) - 1)) // len(phase_items)
    slots = _string_slots(
        phase_items,
        prefix="phases",
        x=72,
        y=228,
        width=width,
        height=236,
        gap=gap,
        horizontal=True,
        priority="must",
        section="flow",
        max_lines=6,
        max_chars_per_line=20,
        font_size_range=[12, 18],
        compress_rule="split",
    )

    summary = str(content.get("summary") or "").strip()
    if summary:
        slots.append(
            {
                "block_id": "summary",
                "box": [160, 580, 960, 56],
                "priority": "should",
                "section": "bottom-band",
                "max_lines": 2,
                "max_chars_per_line": 42,
                "font_size_range": [11, 16],
                "compress_rule": "shorten",
            }
        )
    return slots


def _comparison_matrix_summarybar(content: dict[str, Any]) -> list[dict[str, Any]]:
    row_items = _as_list(content.get("rows"))
    if not row_items:
        raise RuntimeError("slot calculation error: comparison requires rows")
    if len(row_items) > 5:
        raise RuntimeError("slot calculation error: comparison content exceeds supported capacity")

    slots = _string_slots(
        row_items,
        prefix="rows",
        x=140,
        y=228,
        width=1000,
        height=54,
        gap=16,
        horizontal=False,
        priority="must",
        section="matrix",
        max_lines=2,
        max_chars_per_line=36,
        font_size_range=[13, 18],
        compress_rule="split",
    )

    summary = str(content.get("summary") or "").strip()
    if summary:
        slots.append(
            {
                "block_id": "summary",
                "box": [96, 624, 1080, 56],
                "priority": "should",
                "section": "bottom-band",
                "max_lines": 1,
                "max_chars_per_line": 48,
                "font_size_range": [16, 20],
                "compress_rule": "shorten",
            }
        )
    return slots


def _center_radial(content: dict[str, Any]) -> list[dict[str, Any]]:
    satellites = _as_list(content.get("rows"))
    if not satellites:
        raise RuntimeError("slot calculation error: comparison requires rows")
    if len(satellites) > 6:
        raise RuntimeError("slot calculation error: comparison content exceeds supported capacity")

    anchor_boxes = [
        [492, 140, 296, 82],
        [900, 228, 240, 96],
        [892, 438, 240, 96],
        [148, 438, 240, 96],
        [140, 228, 240, 96],
        [492, 566, 296, 58],
    ]
    center_id = "summary" if str(content.get("summary") or "").strip() else "comparison-core"
    slots: list[dict[str, Any]] = [
        {
            "block_id": center_id,
            "box": [404, 268, 472, 176],
            "priority": "must",
            "section": "center",
            "max_lines": 4,
            "max_chars_per_line": 28,
            "font_size_range": [13, 20],
            "compress_rule": "shorten",
        }
    ]
    for idx, box in enumerate(anchor_boxes[: len(satellites)], start=1):
        slots.append(
            {
                "block_id": f"rows-{idx}",
                "box": box,
                "priority": "should",
                "section": "satellite",
                "max_lines": 3,
                "max_chars_per_line": 20,
                "font_size_range": [11, 16],
                "compress_rule": "drop_secondary",
            }
        )
    return slots


def _core_orbit_relationship(content: dict[str, Any]) -> list[dict[str, Any]]:
    satellites = _as_list(content.get("rows"))
    if not str(content.get("summary") or "").strip():
        raise RuntimeError("slot calculation error: core_orbit_relationship requires summary")
    if not 4 <= len(satellites) <= 6:
        raise RuntimeError("slot calculation error: core_orbit_relationship requires 4 to 6 rows")

    center_x = 640
    center_y = 360
    core_size = 168
    satellite_w = 230
    satellite_h = 96
    radius_x = 390
    radius_y = 220
    start_angle = -90.0
    step = 360.0 / len(satellites)

    slots: list[dict[str, Any]] = [
        {
            "block_id": "core-node",
            "box": [center_x - core_size // 2, center_y - core_size // 2, core_size, core_size],
            "priority": "must",
            "section": "core",
            "max_lines": 4,
            "max_chars_per_line": 18,
            "font_size_range": [16, 24],
            "compress_rule": "shorten",
        }
    ]
    for idx, _ in enumerate(satellites, start=1):
        angle = math.radians(start_angle + (idx - 1) * step)
        satellite_cx = center_x + radius_x * math.cos(angle)
        satellite_cy = center_y + radius_y * math.sin(angle)
        slots.append(
            {
                "block_id": f"satellite-{idx}",
                "box": [
                    int(round(satellite_cx - satellite_w / 2)),
                    int(round(satellite_cy - satellite_h / 2)),
                    satellite_w,
                    satellite_h,
                ],
                "priority": "should",
                "section": "satellite",
                "max_lines": 3,
                "max_chars_per_line": 20,
                "font_size_range": [12, 17],
                "compress_rule": "drop_secondary",
            }
        )
    return slots


def generate_auto_slots(slide_dict: dict, canvas_w: int = 1280, canvas_h: int = 720) -> list[dict]:
    """
    输入: slide_dict 含 scene_type / content / blocks / narrative_intent
    输出: List[{"block_id": str, "box": [x,y,w,h], "priority": str}]
    规则: 从 SCENE_TO_LAYOUT 映射表推断 layout_type,再按几何规则算槽位
    失败: raise ValueError("unsupported scene_type") 或 RuntimeError,不吞错、不返回 None
    """

    content = slide_dict.get("content")
    if not isinstance(content, dict):
        raise RuntimeError("slot calculation error: slide content must be a dict")

    scene_type = str(slide_dict.get("scene_type") or "").strip()
    layout_tag = str(slide_dict.get("layout_tag") or "").strip()
    if scene_type == "core_orbit_relationship":
        slots = _core_orbit_relationship(content)
    elif layout_tag == "Comparison-Matrix-SummaryBar":
        slots = _comparison_matrix_summarybar(content)
    else:
        scene_type = _resolve_scene_type(slide_dict, content)
        layout_type = SCENE_TO_LAYOUT.get(scene_type)
        if layout_type is None:
            raise ValueError("unsupported scene_type")

        if layout_type == "vertical_layers_with_side_panel":
            slots = _vertical_layers_with_side_panel(content)
        elif layout_type == "horizontal_flow":
            slots = _horizontal_flow(content)
        elif layout_type == "center_radial":
            slots = _center_radial(content)
        elif layout_type == "core_orbit":
            slots = _core_orbit_relationship(content)
        else:
            raise RuntimeError(f"slot calculation error: unsupported layout_type {layout_type!r}")

    _validate_slots(slots, canvas_w=canvas_w, canvas_h=canvas_h)
    return slots
