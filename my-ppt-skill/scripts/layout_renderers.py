#!/usr/bin/env python3
"""Layout geometry renderers for the AI-PPT Layout DSL."""

from __future__ import annotations

import math
from typing import Any, Callable

from render_theme import Theme, as_list, as_text, clamp_count, pick
from svg_canvas import SvgCanvas


def _semantic_text_roles(slide: dict[str, Any]) -> dict[str, str]:
    """Map rendered copy to stable content roles from blueprint field semantics."""
    roles: dict[str, str] = {}

    def register(value: Any, role: str) -> None:
        if isinstance(value, (str, int, float)):
            key = " ".join(str(value).split())
            if key:
                roles.setdefault(key, role)

    register(slide.get("title"), "title")
    content = slide.get("content")
    if not isinstance(content, dict):
        return roles

    def walk(value: Any, parent_key: str = "") -> None:
        if isinstance(value, dict):
            for raw_key, child in value.items():
                key = str(raw_key).strip().lower().replace("-", "_")
                if key in {"title", "headline"}:
                    register(child, "title")
                elif key in {"statement", "core_conclusion", "conclusion", "takeaway", "insight", "summary"}:
                    register(child, "core-conclusion")
                elif key in {"value", "metric_value", "kpi_value"}:
                    register(child, "key-metric")
                elif key in {"primary_content", "north_star"}:
                    register(child, "primary-content")
                walk(child, key)
        elif isinstance(value, list):
            for item in value:
                walk(item, parent_key)

    walk(content)
    return roles


class LayoutRenderer:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self.palette = [theme.accent, theme.secondary, theme.gold, theme.primary, "#7B61FF", "#2D9CDB"]
        self.registry: dict[str, Callable[[SvgCanvas, dict[str, Any], str], None]] = {
            "Cover-Center": self.cover_center,
            "Statement-Bold": self.statement_bold,
            "Content-List-Left": lambda c, d, t: self.content_list(c, d, t, "left"),
            "Content-List-Right": lambda c, d, t: self.content_list(c, d, t, "right"),
            "Section-Divider": self.section_divider,
            "End-Page": self.end_page,
            "Two-Columns-Split": self.two_columns,
            "Before-After": self.before_after,
            "Pros-Cons": self.pros_cons,
            "Grid-Three-Cards": lambda c, d, t: self.card_grid(c, d, t, 3),
            "Grid-Four-Cards": lambda c, d, t: self.card_grid(c, d, t, 4),
            "Grid-Six-Icons": self.grid_six_icons,
            "Pyramid-Three": self.pyramid_three,
            "Timeline-Horizontal": self.timeline_horizontal,
            "Timeline-Vertical": self.timeline_vertical,
            "Flow-Steps": self.flow_steps,
            "Data-Single-KPI": self.data_single_kpi,
            "Data-Three-KPIs": self.data_three_kpis,
            "Chart-Bar": self.chart_bar,
            "Chart-Line": self.chart_line,
            "Image-Left-Text-Right": lambda c, d, t: self.image_text(c, d, t, "left"),
            "Image-Right-Text-Left": lambda c, d, t: self.image_text(c, d, t, "right"),
            "Strategy-Map": self.strategy_map,
            "Capability-Mapping": self.capability_mapping,
            "Roadmap-MultiPhase": self.roadmap_multi_phase,
            "TOC-Numbered-Bands": self.toc_numbered_bands,
            "Comparison-Matrix-SummaryBar": self.comparison_matrix_summarybar,
            "Regulation-Table-TwoAxis": self.regulation_table_two_axis,
            "Process-LeftCards-CenterFlow": self.process_leftcards_centerflow,
            "Architecture-Three-Zones": self.architecture_three_zones,
            "Maturity-Matrix-Radar": self.maturity_matrix_radar,
            "Stage-Objectives-Deliverables": self.stage_objectives_deliverables,
            "Case-Study-Evidence": self.case_study_evidence,
            "SLA-Double-Table": self.sla_double_table,
            "Roadmap-Lane-Milestones": self.roadmap_lane_milestones,
        }

    def render(self, slide: dict[str, Any]) -> str:
        title = as_text(slide.get("title") or f"Slide {slide.get('id', '')}")
        tag = as_text(slide.get("layout_tag"))
        raw_content = slide.get("content")
        content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
        dark = tag in {"Cover-Center", "Section-Divider"}
        canvas = SvgCanvas(
            title,
            self.theme,
            self.theme.primary if dark else self.theme.canvas_background,
            semantic_roles=_semantic_text_roles(slide),
        )
        renderer = self.registry.get(tag, self.statement_bold)
        renderer(canvas, content, title)
        return canvas.output()

    def draw_motif(self, c: SvgCanvas, dark: bool = False) -> None:
        color = self.theme.accent
        opacity = 0.55 if dark else 0.25
        points = [(955, 150), (1080, 210), (1000, 350), (1140, 430), (905, 500), (740, 255)]
        for idx, (x, y) in enumerate(points):
            c.circle(x, y, 5 + idx % 4, color, opacity=opacity)
        for a, b in zip(points, points[1:]):
            c.line(a[0], a[1], b[0], b[1], color, 1.5, opacity=opacity * 0.55)

    def _slot_blocks(self, d: dict[str, Any]) -> list[dict[str, Any]]:
        raw = d.get("__slot_blocks__")
        return [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def _slot_order(self, block_id: str, prefix: str) -> int:
        suffix = block_id.removeprefix(f"{prefix}-")
        try:
            return int(suffix)
        except ValueError:
            return 10_000

    def _slot_group(self, d: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
        blocks = []
        for block in self._slot_blocks(d):
            block_id = as_text(block.get("id") or block.get("name"))
            if block_id.startswith(f"{prefix}-"):
                blocks.append(block)
        return sorted(blocks, key=lambda item: self._slot_order(as_text(item.get("id") or item.get("name")), prefix))

    def _slot_block(self, d: dict[str, Any], block_id: str) -> dict[str, Any] | None:
        for block in self._slot_blocks(d):
            current_id = as_text(block.get("id") or block.get("name"))
            if current_id == block_id:
                return block
        return None

    def _slot_box(self, block: dict[str, Any]) -> tuple[float, float, float, float] | None:
        raw = block.get("box")
        if not (isinstance(raw, list) and len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw)):
            return None
        return float(raw[0]), float(raw[1]), float(raw[2]), float(raw[3])

    def _slot_bounds(self, blocks: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
        boxes = [self._slot_box(block) for block in blocks]
        valid = [box for box in boxes if box is not None]
        if not valid:
            return None
        left = min(box[0] for box in valid)
        top = min(box[1] for box in valid)
        right = max(box[0] + box[2] for box in valid)
        bottom = max(box[1] + box[3] for box in valid)
        return left, top, right - left, bottom - top

    def _slot_text_attrs(self, block: dict[str, Any]) -> str:
        block_id = as_text(block.get("id") or block.get("name"))
        box = self._slot_box(block)
        if not block_id or box is None:
            return ""
        x, y, w, h = box
        return f'data-slot-id="{block_id}" data-slot-box="{x:g},{y:g},{w:g},{h:g}"'

    def _render_architecture_three_zones_with_slots(self, c: SvgCanvas, d: dict[str, Any], title: str) -> bool:
        core_blocks = self._slot_group(d, "core_modules")
        if not core_blocks:
            return False

        left_items = clamp_count(as_list(d.get("left_systems")), len(self._slot_group(d, "left_systems")) or 7)
        core_items = clamp_count(as_list(d.get("core_modules")), len(core_blocks))
        right_blocks = self._slot_group(d, "right_modules")
        right_items = clamp_count(as_list(d.get("right_modules")), len(right_blocks) or 6)
        storage_blocks = self._slot_group(d, "storage")
        storage_items = clamp_count(as_list(d.get("storage")), len(storage_blocks) or 8)

        c.wrapped_text(80, 94, pick(d, "title", default=title), 1100, 36, self.theme.primary, 850, max_lines=1)
        subtitle = pick(d, "subtitle")
        if subtitle:
            c.wrapped_text(80, 130, subtitle, 1040, 16, self.theme.muted, 500, max_lines=1)

        top_blocks = self._slot_group(d, "left_systems")
        top_bounds = self._slot_bounds(top_blocks)
        if top_bounds and left_items:
            x, y, w, h = top_bounds
            top_text_block = top_blocks[min(1, len(top_blocks) - 1)] if top_blocks else None
            top_text_attrs = self._slot_text_attrs(top_text_block) if top_text_block else ""
            c.rect(x, y, w, h, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
            c.text(x + w / 2.0, y - 10, "外部系统", 16, self.theme.secondary, 800, "middle")
            top_text = " / ".join(as_text(item) for item in left_items if as_text(item))
            c.wrapped_text(
                x + w / 2.0,
                y + h / 2.0 + 6,
                top_text,
                max(80.0, w - 24.0),
                14,
                self.theme.primary,
                700,
                "middle",
                max_lines=2,
                extra_attrs=top_text_attrs,
            )

        core_bounds = self._slot_bounds(core_blocks)
        if core_bounds:
            cx, cy, cw, ch = core_bounds
            c.text(cx + cw / 2.0, cy - 10, "追溯系统", 18, self.theme.primary, 850, "middle")

        for idx, block in enumerate(core_blocks):
            box = self._slot_box(block)
            if box is None:
                continue
            x, y, w, h = box
            row_fill = self.theme.soft if idx >= max(0, len(core_blocks) - 2) else self.theme.card
            accent = self.palette[idx % len(self.palette)]
            label_fill = self.theme.secondary if idx < max(0, len(core_blocks) - 2) else self.theme.accent
            label_w = min(180.0, max(150.0, w * 0.24))
            content_x = x + label_w + 14.0
            content_w = max(120.0, w - label_w - 28.0)
            body_lines = 2 if h >= 48 else 1
            item = core_items[idx] if idx < len(core_items) else {}
            if not isinstance(item, dict):
                item = {"title": str(item)}

            c.rect(x, y, w, h, row_fill, stroke=self.theme.line, sw=1, rx=6)
            c.rect(x, y, label_w, h, label_fill, rx=6)
            c.rect(x, y, w, 6, accent, rx=3)
            c.wrapped_text(
                x + label_w / 2.0,
                y + h / 2.0 + 5,
                pick(item, "title", default=f"模块{idx + 1}"),
                max(70.0, label_w - 20.0),
                15,
                "#FFFFFF",
                800,
                "middle",
                max_lines=1,
                min_size=12,
                extra_attrs=self._slot_text_attrs(block),
            )
            c.wrapped_text(
                content_x,
                y + 18,
                pick(item, "body", "description"),
                content_w,
                12,
                self.theme.primary,
                500,
                max_lines=body_lines,
                line_height=15,
                min_size=10,
                extra_attrs=self._slot_text_attrs(block),
            )

        if top_bounds and core_bounds:
            tx, ty, tw, th = top_bounds
            cx, cy, cw, _ = core_bounds
            c.line(tx + tw / 2.0, ty + th, cx + cw / 2.0, cy - 6, self.theme.line, 2, 0.9, arrow=True)

        right_bounds = self._slot_bounds(right_blocks)
        if right_bounds and right_items:
            x, y, w, h = right_bounds
            panel_y = max(160.0, y - 44.0)
            panel_h = h + (y - panel_y) + 16.0
            c.rect(x, panel_y, w, panel_h, self.theme.card, stroke=self.theme.line, sw=1, rx=6)
            c.text(x + w / 2.0, panel_y + 28, "管理域", 18, self.theme.primary, 800, "middle")
            c.line(x + 18, panel_y + 40, x + w - 18, panel_y + 40, self.theme.line, 1)
            for idx, block in enumerate(right_blocks):
                box = self._slot_box(block)
                if box is None:
                    continue
                bx, by, bw, bh = box
                c.rect(bx, by, bw, bh, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
                item = right_items[idx] if idx < len(right_items) else ""
                c.wrapped_text(
                    bx + bw / 2.0,
                    by + bh / 2.0 + 5,
                    as_text(item),
                    max(60.0, bw - 20.0),
                    13,
                    self.theme.primary,
                    700,
                    "middle",
                    max_lines=2,
                    min_size=11,
                    extra_attrs=self._slot_text_attrs(block),
                )
            if core_bounds:
                cx, cy, cw, ch = core_bounds
                c.line(cx + cw, cy + ch / 2.0, x - 10, panel_y + panel_h / 2.0, self.theme.line, 2, 0.9, arrow=True)

        bottom_bounds = self._slot_bounds(storage_blocks)
        if bottom_bounds and storage_items:
            x, y, w, h = bottom_bounds
            band_y = max(0.0, y - 12.0)
            band_h = h + 24.0
            c.rect(x, band_y, w, band_h, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
            c.text(x + 20, band_y + 22, "数据存储", 16, self.theme.primary, 800)
            for idx, block in enumerate(storage_blocks):
                box = self._slot_box(block)
                if box is None:
                    continue
                bx, by, bw, bh = box
                c.rect(bx, by, bw, bh, self.theme.card, stroke=self.theme.line, sw=1, rx=4)
                item = storage_items[idx] if idx < len(storage_items) else ""
                c.wrapped_text(
                    bx + bw / 2.0,
                    by + bh / 2.0 + 4,
                    as_text(item),
                    max(60.0, bw - 20.0),
                    12,
                    self.theme.primary,
                    700,
                    "middle",
                    max_lines=2,
                    min_size=10,
                    extra_attrs=self._slot_text_attrs(block),
                )
            if core_bounds:
                cx, cy, cw, ch = core_bounds
                c.line(cx + cw / 2.0, cy + ch, x + w / 2.0, band_y - 8, self.theme.line, 2, 0.9, arrow=True)

        c.footer()
        return True

    def cover_center(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.rect(80, 78, 160, 34, self.theme.accent, rx=8)
        c.text(100, 101, "DEMO DECK", 14, self.theme.primary, 700)
        c.wrapped_text(
            160, 275, pick(d, "headline", default=title), 780, 58, "#FFFFFF", 800, max_lines=2, line_height=72
        )
        c.wrapped_text(160, 430, pick(d, "subtitle"), 780, 25, "#D7DEE8", max_lines=2)
        c.text(160, 486, pick(d, "date"), 16, "#AEB8C6")
        self.draw_motif(c, dark=True)
        c.footer(dark=True)

    def statement_bold(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.text(80, 100, pick(d, "eyebrow", default=title), 16, self.theme.secondary, 800)
        c.rect(60, 205, 12, 270, self.theme.accent, rx=6)
        c.wrapped_text(
            120,
            245,
            pick(d, "statement", "headline", default=title),
            950,
            50,
            self.theme.primary,
            800,
            max_lines=3,
            line_height=64,
        )
        c.wrapped_text(130, 510, pick(d, "support", "body"), 860, 22, self.theme.muted, max_lines=2, line_height=34)
        c.circle(1060, 155, 74, self.theme.soft)
        c.circle(1060, 155, 38, self.theme.accent, opacity=0.85)
        c.circle(1060, 155, 10, self.theme.primary)
        c.footer()

    def content_list(self, c: SvgCanvas, d: dict[str, Any], title: str, side: str) -> None:
        left_title = side == "left"
        title_x = 80 if left_title else 790
        items_x = 560 if left_title else 90
        c.wrapped_text(
            title_x, 145, pick(d, "title", default=title), 390, 39, self.theme.primary, 850, max_lines=3, line_height=52
        )
        c.wrapped_text(
            title_x + 2, 322, pick(d, "subtitle", "body"), 380, 20, self.theme.muted, max_lines=2, line_height=31
        )
        items = clamp_count(as_list(d.get("items")), 4)
        ys = [155, 270, 385, 500]
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                item = {"title": str(item), "body": ""}
            y = ys[idx]
            color = self.palette[idx % len(self.palette)]
            c.circle(items_x, y, 14, color)
            c.text(items_x + 35, y - 8, pick(item, "title", default=f"Item {idx + 1}"), 24, self.theme.primary, 800)
            c.wrapped_text(
                items_x + 35, y + 30, pick(item, "body", "description"), 560, 18, self.theme.muted, max_lines=2
            )
            if idx < len(items) - 1:
                c.line(items_x, y + 25, items_x, ys[idx + 1] - 25, self.theme.line, 2)
        c.footer()

    def section_divider(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.text(100, 180, pick(d, "section", default="SECTION"), 24, self.theme.accent, 900)
        c.wrapped_text(100, 315, pick(d, "title", default=title), 760, 56, "#FFFFFF", 850, max_lines=2, line_height=72)
        c.wrapped_text(105, 430, pick(d, "subtitle", "body"), 860, 23, "#D7DEE8", max_lines=2)
        c.rect(100, 545, 220, 5, self.theme.accent, rx=3)
        c.footer(dark=True)

    def end_page(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.circle(640, 205, 68, self.theme.soft)
        c.circle(640, 205, 28, self.theme.accent)
        c.wrapped_text(
            640, 342, pick(d, "headline", default=title), 820, 45, self.theme.primary, 850, "middle", max_lines=1
        )
        c.wrapped_text(640, 405, pick(d, "message", "body"), 820, 23, self.theme.muted, anchor="middle", max_lines=2)
        c.rect(500, 455, 280, 5, self.theme.accent, rx=3)
        c.wrapped_text(640, 535, pick(d, "contact"), 760, 16, self.theme.muted, 500, "middle", max_lines=1)
        c.footer()

    def two_columns(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 1000, 34, self.theme.primary, 800, max_lines=2)
        panels = [(80, d.get("left", {}), self.theme.secondary), (680, d.get("right", {}), self.theme.accent)]
        for x, panel, color in panels:
            panel = panel if isinstance(panel, dict) else {}
            c.card(x, 180, 520, 420)
            c.rect(x, 180, 520, 12, color, rx=6)
            c.wrapped_text(
                x + 34, 255, pick(panel, "title", default="Option"), 450, 34, self.theme.primary, 800, max_lines=1
            )
            c.wrapped_text(
                x + 34,
                330,
                pick(panel, "body", "description"),
                430,
                26,
                self.theme.text,
                700,
                max_lines=2,
                line_height=42,
            )
        c.line(610, 390, 670, 390, self.theme.primary, 3, 0.5, arrow=True)
        c.footer()

    def before_after(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 1000, 34, self.theme.primary, 800)
        panels = [
            (80, d.get("before", {}), self.theme.line, self.theme.muted),
            (700, d.get("after", {}), self.theme.soft, self.theme.accent),
        ]
        for x, panel, fill, color in panels:
            panel = panel if isinstance(panel, dict) else {}
            c.card(x, 190, 500, 380, fill)
            c.rect(x, 190, 500, 10, color, rx=5)
            c.wrapped_text(x + 34, 255, pick(panel, "title", default="State"), 420, 28, self.theme.primary, 800)
            c.wrapped_text(
                x + 34, 320, pick(panel, "body", "description"), 420, 20, self.theme.muted, max_lines=4, line_height=32
            )
        c.line(610, 365, 670, 365, self.theme.primary, 3, 0.5, arrow=True)
        c.footer()

    def pros_cons(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 1000, 34, self.theme.primary, 800)
        columns = [(80, "Pros", d.get("pros"), self.theme.accent), (680, "Cons", d.get("cons"), self.theme.secondary)]
        for x, label, raw_items, color in columns:
            c.card(x, 180, 520, 420)
            c.rect(x, 180, 520, 12, color, rx=6)
            c.text(x + 34, 245, label, 30, self.theme.primary, 850)
            for idx, item in enumerate(clamp_count(as_list(raw_items), 4)):
                item = item if isinstance(item, dict) else {"title": str(item)}
                y = 305 + idx * 70
                c.circle(x + 44, y - 8, 9, color)
                c.text(x + 70, y, pick(item, "title", default=f"Point {idx + 1}"), 20, self.theme.primary, 800)
                c.wrapped_text(
                    x + 70, y + 26, pick(item, "body", "description"), 390, 15, self.theme.muted, max_lines=1
                )
        c.footer()

    def card_grid(self, c: SvgCanvas, d: dict[str, Any], title: str, count: int) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 900, 36, self.theme.primary, 800, max_lines=2)
        cards = clamp_count(as_list(d.get("cards")), count)
        if count == 3:
            positions = [(80, 230, 330, 330), (455, 230, 330, 330), (830, 230, 330, 330)]
        else:
            positions = [(80, 165, 540, 190), (660, 165, 540, 190), (80, 400, 540, 190), (660, 400, 540, 190)]
        for idx, item in enumerate(cards):
            item = item if isinstance(item, dict) else {"title": str(item)}
            x, y, w, h = positions[idx]
            color = self.palette[idx % len(self.palette)]
            c.card(x, y, w, h)
            if count == 3:
                c.circle(x + 54, y + 45, 22, color)
                c.text(
                    x + 54,
                    y + 53,
                    str(idx + 1),
                    22,
                    "#FFFFFF" if color != self.theme.gold else self.theme.primary,
                    800,
                    "middle",
                )
                c.text(x + 28, y + 88, pick(item, "title", default=f"Card {idx + 1}"), 25, self.theme.primary, 800)
                c.wrapped_text(
                    x + 28,
                    y + 140,
                    pick(item, "body", "description"),
                    w - 56,
                    18,
                    self.theme.muted,
                    max_lines=3,
                    line_height=30,
                )
                c.rect(x + 28, y + h - 40, 90, 5, color, rx=3)
            else:
                c.rect(x, y, 12, h, color, rx=6)
                c.text(x + 34, y + 58, pick(item, "title", default=f"Card {idx + 1}"), 24, self.theme.primary, 800)
                c.wrapped_text(
                    x + 34,
                    y + 104,
                    pick(item, "body", "description"),
                    w - 80,
                    17,
                    self.theme.muted,
                    max_lines=2,
                    line_height=28,
                )
        c.footer()

    def grid_six_icons(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 100, pick(d, "title", default=title), 900, 36, self.theme.primary, 800)
        positions = [(90, 185), (455, 185), (820, 185), (90, 410), (455, 410), (820, 410)]
        for idx, item in enumerate(clamp_count(as_list(d.get("items") or d.get("cards")), 6)):
            item = item if isinstance(item, dict) else {"title": str(item)}
            x, y = positions[idx]
            color = self.palette[idx % len(self.palette)]
            c.circle(x + 32, y + 34, 22, color)
            c.text(
                x + 32,
                y + 42,
                str(idx + 1),
                18,
                "#FFFFFF" if color != self.theme.gold else self.theme.primary,
                800,
                "middle",
            )
            c.text(x + 72, y + 30, pick(item, "title", default=f"Item {idx + 1}"), 22, self.theme.primary, 800)
            c.wrapped_text(x + 72, y + 66, pick(item, "body", "description"), 220, 16, self.theme.muted, max_lines=3)
        c.footer()

    def pyramid_three(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 100, pick(d, "title", default=title), 900, 36, self.theme.primary, 800)
        layers = clamp_count(as_list(d.get("layers") or d.get("items")), 3)
        shapes = [
            ([(310.0, 560.0), (970.0, 560.0), (850.0, 430.0), (430.0, 430.0)], 500, self.theme.accent),
            ([(430.0, 410.0), (850.0, 410.0), (760.0, 290.0), (520.0, 290.0)], 360, self.theme.secondary),
            ([(520.0, 270.0), (760.0, 270.0), (700.0, 170.0), (580.0, 170.0)], 230, self.theme.gold),
        ]
        for idx, (pts, y, color) in enumerate(shapes):
            item = layers[idx] if isinstance(layers[idx], dict) else {"title": str(layers[idx])}
            c.polygon(pts, color, "#FFFFFF", 2, opacity=0.92)
            c.wrapped_text(
                640,
                y,
                pick(item, "title", default=f"Layer {idx + 1}"),
                360,
                24,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
            )
            c.wrapped_text(
                640, y + 34, pick(item, "body", "description"), 420, 15, self.theme.text, 500, "middle", max_lines=1
            )
        c.footer()

    def timeline_horizontal(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 900, 36, self.theme.primary, 800)
        events = clamp_count(
            as_list(d.get("events") or d.get("steps")),
            max(3, min(5, len(as_list(d.get("events") or d.get("steps"))) or 4)),
        )
        c.line(140, 390, 1140, 390, self.theme.line, 4)
        span = 920 / max(len(events) - 1, 1)
        for idx, item in enumerate(events):
            item = item if isinstance(item, dict) else {"title": str(item)}
            x = 180 + idx * span
            color = self.palette[idx % len(self.palette)]
            c.text(x, 335, pick(item, "date", "phase", default=f"T{idx + 1}"), 18, self.theme.primary, 800, "middle")
            c.circle(x, 390, 20, color)
            c.wrapped_text(
                x,
                435,
                pick(item, "title", default=f"Step {idx + 1}"),
                220,
                18,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
            )
            c.wrapped_text(
                x, 465, pick(item, "body", "description"), 220, 15, self.theme.muted, anchor="middle", max_lines=2
            )
        c.footer()

    def timeline_vertical(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 100, pick(d, "title", default=title), 900, 36, self.theme.primary, 800)
        events = clamp_count(as_list(d.get("events") or d.get("steps")), 4)
        c.line(640, 155, 640, 610, self.theme.line, 4)
        ys = [180, 300, 420, 540]
        for idx, item in enumerate(events):
            item = item if isinstance(item, dict) else {"title": str(item)}
            y = ys[idx]
            x = 110 if idx % 2 == 0 else 750
            color = self.palette[idx % len(self.palette)]
            c.circle(640, y, 17, color)
            c.card(x, y - 48, 420, 96)
            c.text(x + 24, y - 14, pick(item, "date", "phase", default=f"0{idx + 1}"), 15, self.theme.primary, 800)
            c.text(x + 100, y - 14, pick(item, "title", default=f"Milestone {idx + 1}"), 20, self.theme.primary, 800)
            c.wrapped_text(x + 24, y + 20, pick(item, "body", "description"), 360, 15, self.theme.muted, max_lines=2)
        c.footer()

    def flow_steps(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 108, pick(d, "title", default=title), 900, 36, self.theme.primary, 800)
        steps = clamp_count(
            as_list(d.get("steps") or d.get("items")),
            max(3, min(5, len(as_list(d.get("steps") or d.get("items"))) or 4)),
        )
        count = len(steps)
        gap = 36
        card_w = min(230, (1100 - gap * (count - 1)) / count)
        start_x = (1280 - (card_w * count + gap * (count - 1))) / 2
        for idx, item in enumerate(steps):
            item = item if isinstance(item, dict) else {"title": str(item)}
            x = start_x + idx * (card_w + gap)
            color = self.palette[idx % len(self.palette)]
            c.card(x, 250, card_w, 220)
            c.circle(x + 36, 305, 22, color)
            c.text(
                x + 36,
                313,
                str(idx + 1),
                20,
                "#FFFFFF" if color != self.theme.gold else self.theme.primary,
                800,
                "middle",
            )
            c.wrapped_text(
                x + 28,
                360,
                pick(item, "title", default=f"Step {idx + 1}"),
                card_w - 56,
                22,
                self.theme.primary,
                800,
                max_lines=2,
            )
            c.wrapped_text(
                x + 28, 420, pick(item, "body", "description"), card_w - 56, 15, self.theme.muted, max_lines=2
            )
            if idx < count - 1:
                c.line(x + card_w + 8, 360, x + card_w + gap - 8, 360, self.theme.primary, 2, 0.45, arrow=True)
        c.footer()

    def data_single_kpi(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.text(80, 102, pick(d, "eyebrow", default=title), 16, self.theme.secondary, 800)
        c.circle(640, 335, 150, self.theme.soft)
        c.circle(640, 335, 112, "#FFFFFF", self.theme.line)
        c.text(640, 374, pick(d, "value", default="1"), 132, self.theme.primary, 900, "middle")
        c.text(640, 438, pick(d, "label", default="KPI"), 28, self.theme.primary, 800, "middle")
        c.wrapped_text(
            640, 505, pick(d, "explanation", "body"), 760, 18, self.theme.muted, anchor="middle", max_lines=2
        )
        c.footer()

    def data_three_kpis(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 98, pick(d, "title", default=title), 760, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(
            80,
            148,
            pick(d, "summary", "explanation", "insight"),
            760,
            19,
            self.theme.muted,
            500,
            max_lines=2,
            line_height=28,
            min_size=16,
        )
        c.card(900, 90, 280, 108, self.theme.soft)
        c.text(924, 128, "KPI Summary", 17, self.theme.primary, 800)
        c.wrapped_text(
            924,
            156,
            pick(d, "trend_note", "insight", default="Track value, direction, and context together."),
            230,
            14,
            self.theme.muted,
            max_lines=3,
            min_size=12,
        )
        kpis = clamp_count(as_list(d.get("kpis") or d.get("cards")), 3)
        for idx, item in enumerate(kpis):
            item = item if isinstance(item, dict) else {"value": str(item)}
            x = [80, 455, 830][idx]
            color = self.palette[idx % len(self.palette)]
            c.card(x, 230, 330, 280)
            c.rect(x, 230, 330, 8, color, rx=4)
            c.text(x + 26, 270, f"KPI {idx + 1}", 14, self.theme.muted, 700)
            c.text(x + 165, 352, pick(item, "value", default="--"), 58, self.theme.primary, 900, "middle")
            c.wrapped_text(
                x + 165,
                402,
                pick(item, "label", "title", default=f"Metric {idx + 1}"),
                260,
                20,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
                min_size=16,
            )
            c.wrapped_text(
                x + 165,
                438,
                pick(item, "trend", "delta", default=""),
                260,
                16,
                color,
                800,
                "middle",
                max_lines=1,
                min_size=13,
            )
            c.wrapped_text(
                x + 165,
                470,
                pick(item, "body", "description"),
                260,
                15,
                self.theme.muted,
                anchor="middle",
                max_lines=2,
                min_size=12,
            )
        c.footer()

    def chart_bar(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 96, pick(d, "title", default=title), 760, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(
            80,
            146,
            pick(d, "summary", "explanation"),
            760,
            18,
            self.theme.muted,
            max_lines=2,
            min_size=15,
        )
        c.card(80, 186, 780, 410)
        bars = clamp_count(as_list(d.get("bars") or d.get("data")), 5)
        values = [
            max(0.0, float(item.get("value", idx + 1) if isinstance(item, dict) else idx + 1))
            for idx, item in enumerate(bars)
        ]
        max_v = max(values) if values else 1
        chart_left = 130
        chart_bottom = 548
        chart_height = 286
        chart_width = 660
        c.line(chart_left, chart_bottom, chart_left + chart_width, chart_bottom, self.theme.line, 2)
        bar_w = min(108, chart_width / max(len(bars), 1) * 0.7)
        gap = (chart_width - bar_w * len(bars)) / max(len(bars) - 1, 1)
        for idx, item in enumerate(bars):
            item = item if isinstance(item, dict) else {"label": str(item), "value": values[idx]}
            h = chart_height * values[idx] / max_v
            x = chart_left + 40 + idx * (bar_w + gap)
            y = chart_bottom - h
            color = self.palette[idx % len(self.palette)]
            c.rect(x, y, bar_w, h, color, rx=6)
            c.text(
                x + bar_w / 2, y - 14, as_text(item.get("value", values[idx])), 15, self.theme.primary, 800, "middle"
            )
            c.wrapped_text(
                x + bar_w / 2,
                576,
                pick(item, "label", default=f"Item {idx + 1}"),
                max(bar_w + 30, 120),
                14,
                self.theme.muted,
                anchor="middle",
                max_lines=2,
                min_size=12,
            )
        c.card(900, 186, 280, 410, self.theme.soft)
        c.text(924, 228, "Key Insight", 20, self.theme.primary, 800)
        c.wrapped_text(
            924,
            264,
            pick(d, "insight", default="Add one conclusion about trend, gap, and risk."),
            232,
            16,
            self.theme.primary,
            700,
            max_lines=6,
            line_height=25,
            min_size=13,
        )
        c.text(924, 438, "Action", 16, self.theme.primary, 800)
        c.wrapped_text(
            924,
            466,
            pick(d, "next_action", "support_summary"),
            232,
            14,
            self.theme.muted,
            max_lines=5,
            line_height=22,
            min_size=12,
        )
        c.footer()

    def chart_line(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 96, pick(d, "title", default=title), 760, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(
            80,
            146,
            pick(d, "summary", "explanation"),
            760,
            18,
            self.theme.muted,
            max_lines=2,
            min_size=15,
        )
        c.card(80, 186, 780, 410)
        points_raw = clamp_count(as_list(d.get("points") or d.get("data")), 5)
        values = [
            float(item.get("value", idx + 1) if isinstance(item, dict) else idx + 1)
            for idx, item in enumerate(points_raw)
        ]
        min_v, max_v = min(values), max(values)
        if math.isclose(min_v, max_v):
            max_v = min_v + 1
        chart_left = 130.0
        chart_right = 810.0
        chart_top = 238.0
        chart_bottom = 548.0
        for idx in range(4):
            y = chart_top + idx * 90
            c.line(chart_left, y, chart_right, y, self.theme.line, 1, 0.7)
        pts: list[tuple[float, float]] = []
        span = (chart_right - chart_left - 40) / max(len(points_raw) - 1, 1)
        for idx, item in enumerate(points_raw):
            x = chart_left + 20 + idx * span
            y = chart_bottom - (values[idx] - min_v) / (max_v - min_v) * 290
            pts.append((x, y))
            c.circle(x, y, 8, self.theme.accent)
            label = pick(item, "label", default=f"T{idx + 1}") if isinstance(item, dict) else f"T{idx + 1}"
            c.text(x, 578, label, 14, self.theme.muted, 500, "middle")
            c.text(
                x,
                y - 14,
                as_text(item.get("value", values[idx]) if isinstance(item, dict) else values[idx]),
                14,
                self.theme.primary,
                700,
                "middle",
            )
        c.polyline(pts, self.theme.accent, 4)
        c.card(900, 186, 280, 410, self.theme.soft)
        c.text(924, 228, "Trend Summary", 20, self.theme.primary, 800)
        c.wrapped_text(
            924,
            264,
            pick(d, "insight", default="Explain inflection point and expected stabilization window."),
            232,
            16,
            self.theme.primary,
            700,
            max_lines=6,
            line_height=25,
            min_size=13,
        )
        c.text(924, 438, "Risk / Follow-up", 16, self.theme.primary, 800)
        c.wrapped_text(
            924,
            466,
            pick(d, "next_action", "support_summary"),
            232,
            14,
            self.theme.muted,
            max_lines=5,
            line_height=22,
            min_size=12,
        )
        c.footer()

    def image_text(self, c: SvgCanvas, d: dict[str, Any], title: str, image_side: str) -> None:
        image_left = image_side == "left"
        image_x = 0 if image_left else 768
        text_x = 600 if image_left else 80
        c.rect(image_x, 0, 512, 720, self.theme.primary)
        c.circle(image_x + 256, 260, 98, self.theme.accent, opacity=0.25)
        c.circle(image_x + 256, 260, 44, self.theme.accent)
        c.line(image_x + 180, 410, image_x + 332, 410, self.theme.accent, 4, 0.8)
        c.wrapped_text(
            text_x, 145, pick(d, "title", default=title), 560, 42, self.theme.primary, 850, max_lines=2, line_height=56
        )
        c.wrapped_text(
            text_x + 2, 270, pick(d, "body", "description"), 520, 20, self.theme.muted, max_lines=4, line_height=32
        )
        for idx, item in enumerate(clamp_count(as_list(d.get("items")), 3)):
            item = item if isinstance(item, dict) else {"title": str(item)}
            y = 410 + idx * 72
            c.circle(text_x + 12, y - 6, 8, self.palette[idx % len(self.palette)])
            c.text(text_x + 36, y, pick(item, "title", default=f"Point {idx + 1}"), 20, self.theme.primary, 800)
            c.wrapped_text(
                text_x + 36, y + 25, pick(item, "body", "description"), 460, 15, self.theme.muted, max_lines=1
            )
        c.footer(dark=False)

    def strategy_map(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 96, pick(d, "title", default=title), 780, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(
            80,
            146,
            pick(d, "summary", "explanation"),
            760,
            18,
            self.theme.muted,
            max_lines=2,
            min_size=15,
        )
        c.card(80, 186, 1120, 108, self.theme.soft)
        c.rect(102, 204, 128, 30, self.theme.accent, rx=6)
        c.text(166, 225, "North Star", 15, "#101216", 800, "middle")
        c.wrapped_text(
            250,
            226,
            pick(d, "north_star", default="North star"),
            920,
            24,
            self.theme.primary,
            800,
            max_lines=2,
            min_size=19,
        )
        pillars = clamp_count(as_list(d.get("pillars")), 3)
        pillar_centers: list[float] = []
        for idx, raw in enumerate(pillars):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x = [80, 455, 830][idx]
            c.card(x, 322, 330, 164)
            color = self.palette[idx % len(self.palette)]
            center_x = x + 165
            pillar_centers.append(center_x)
            c.line(640, 294, center_x, 322, self.theme.line, 2, 0.8)
            c.rect(x, 322, 330, 8, color, rx=4)
            c.text(x + 24, 356, f"Pillar {idx + 1}", 14, self.theme.muted, 700)
            c.wrapped_text(
                x + 24,
                386,
                pick(item, "title", default=f"Pillar {idx + 1}"),
                282,
                22,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=18,
            )
            c.wrapped_text(
                x + 24,
                420,
                pick(item, "body", "description"),
                282,
                16,
                self.theme.muted,
                max_lines=2,
                min_size=13,
            )
        initiatives = clamp_count(as_list(d.get("initiatives")), 4)
        for idx, raw in enumerate(initiatives):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x = 80 + idx * 282
            center_x = x + 130
            pillar_idx = min(idx, len(pillar_centers) - 1) if pillar_centers else 0
            if pillar_centers:
                c.line(pillar_centers[pillar_idx], 486, center_x, 520, self.theme.line, 2, 0.65)
            c.card(x, 520, 260, 120)
            c.rect(x, 520, 260, 6, self.theme.line, rx=3)
            c.text(x + 18, 548, f"Action {idx + 1}", 13, self.theme.muted, 700)
            c.wrapped_text(
                x + 18,
                570,
                pick(item, "title", default=f"Initiative {idx + 1}"),
                224,
                17,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=14,
            )
            c.wrapped_text(
                x + 18,
                596,
                pick(item, "body", "description"),
                224,
                14,
                self.theme.muted,
                max_lines=2,
                min_size=12,
            )
        c.footer()

    def capability_mapping(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 96, pick(d, "title", default=title), 760, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(
            80,
            146,
            pick(d, "summary", "explanation"),
            760,
            18,
            self.theme.muted,
            max_lines=2,
            min_size=15,
        )
        headers = [("Capability", 80, 350), ("Execution", 450, 350), ("System Support", 820, 360)]
        y_header = 186
        for label, x, w in headers:
            is_support = label == "System Support"
            color = self.theme.accent if is_support else self.theme.line
            c.card(x, y_header, w, 48, self.theme.soft if is_support else self.theme.card)
            c.text(x + 18, y_header + 32, label, 18, self.theme.primary, 800)
            c.rect(x, y_header, w, 6, color, rx=3)
        capabilities = clamp_count(as_list(d.get("capabilities")), 3)
        row_y = [252, 372, 492]
        row_h = 104
        for idx, raw in enumerate(capabilities):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            y = row_y[idx]
            c.card(80, y, 350, row_h)
            c.card(450, y, 350, row_h)
            c.card(820, y, 360, row_h, self.theme.soft)
            c.wrapped_text(
                98,
                y + 40,
                pick(item, "title", default=f"Capability {idx + 1}"),
                320,
                20,
                self.theme.primary,
                800,
                max_lines=2,
                min_size=16,
            )
            c.wrapped_text(
                468,
                y + 40,
                pick(item, "body", "description"),
                320,
                16,
                self.theme.muted,
                max_lines=3,
                min_size=13,
            )
            c.wrapped_text(
                838,
                y + 40,
                pick(item, "system_support", default="Support rule"),
                324,
                16,
                self.theme.primary,
                700,
                max_lines=4,
                line_height=23,
                min_size=13,
            )
            if idx < len(capabilities) - 1:
                c.line(80, y + row_h + 8, 1180, y + row_h + 8, self.theme.line, 1, 0.5)
        c.wrapped_text(80, 646, pick(d, "support_summary"), 1100, 14, self.theme.muted, max_lines=1, min_size=12)
        c.footer()

    def roadmap_multi_phase(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 102, pick(d, "title", default=title), 900, 36, self.theme.primary, 850, max_lines=2)
        phases = clamp_count(as_list(d.get("phases")), 3)
        base_y = 330
        c.line(120, base_y, 1160, base_y, self.theme.line, 4)
        card_w = 310
        card_half = card_w / 2.0
        left_edge = 80 + card_half
        right_edge = 1200 - card_half
        if len(phases) <= 1:
            x_positions = [640.0]
        else:
            step = (right_edge - left_edge) / (len(phases) - 1)
            x_positions = [left_edge + idx * step for idx in range(len(phases))]
        for idx, raw in enumerate(phases):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x = x_positions[idx]
            color = self.palette[idx % len(self.palette)]
            c.circle(x, base_y, 22, color)
            c.card(x - card_half, 170, card_w, 132)
            c.text(x - 136, 210, pick(item, "phase", default=f"P{idx + 1}"), 16, self.theme.primary, 800)
            c.wrapped_text(
                x - 136,
                238,
                pick(item, "title", default=f"Phase {idx + 1}"),
                270,
                22,
                self.theme.primary,
                800,
                max_lines=1,
            )
            c.wrapped_text(x - 136, 268, pick(item, "body", "description"), 270, 14, self.theme.muted, max_lines=2)
            c.card(x - card_half, 382, card_w, 150)
            c.wrapped_text(x - 136, 430, "Deliverables", 270, 16, self.theme.primary, 800, max_lines=1)
            c.wrapped_text(
                x - 136,
                458,
                pick(item, "deliverable", "output", default="Scope definition and QA gates"),
                270,
                14,
                self.theme.muted,
                max_lines=3,
            )
        c.card(950, 560, 250, 70, self.theme.soft)
        c.text(972, 600, f"Milestone: {pick(d, 'milestone', default='v1')}", 16, self.theme.primary, 800)
        c.footer()

    def toc_numbered_bands(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 104, pick(d, "title", default=title), 900, 42, self.theme.primary, 850, max_lines=1)
        c.line(80, 126, 1160, 126, self.theme.line, 2)
        sections = clamp_count(as_list(d.get("sections")), 6)
        active = int(d.get("active", 1)) if str(d.get("active", "")).isdigit() else 1
        y0 = 190
        for idx, raw in enumerate(sections, start=1):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            y = y0 + (idx - 1) * 86
            is_active = idx == active
            band_fill = self.theme.accent if is_active else self.theme.card
            num_fill = self.theme.primary if is_active else self.theme.soft
            text_color = "#FFFFFF" if is_active else self.theme.primary
            c.rect(180, y, 980, 64, band_fill, stroke=self.theme.line, sw=1, rx=0)
            c.rect(80, y, 86, 64, num_fill, stroke=self.theme.line, sw=1, rx=0)
            c.text(
                123,
                y + 42,
                pick(item, "number", default=str(idx)),
                40,
                text_color if is_active else self.theme.primary,
                800,
                "middle",
            )
            c.wrapped_text(
                190,
                y + 42,
                pick(item, "title", default=f"章节 {idx}"),
                940,
                34,
                text_color,
                800,
                max_lines=1,
                min_size=22,
            )
        c.footer()

    def _render_comparison_matrix_summarybar_with_slots(self, c: SvgCanvas, d: dict[str, Any], title: str) -> bool:
        row_blocks = self._slot_group(d, "rows")
        if not row_blocks:
            return False

        rows = clamp_count(as_list(d.get("rows")), len(row_blocks))
        summary_slot = self._slot_block(d, "summary")
        if summary_slot is None:
            return False
        row_boxes = [self._slot_box(block) for block in row_blocks]
        summary_box = self._slot_box(summary_slot)
        if summary_box is None or any(box is None for box in row_boxes):
            return False

        left_title = pick(d, "left_title", default="\u65b9\u6848A")
        right_title = pick(d, "right_title", default="\u65b9\u6848B")
        summary_attrs = (
            f'{self._slot_text_attrs(summary_slot)} '
            'data-structural-anchor="comparison-summary-bar comparison-recommendation"'
        )

        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        c.card(80, 160, 1120, 452)
        c.rect(80, 160, 1120, 56, self.theme.soft, stroke=self.theme.line, sw=1, rx=0)
        c.wrapped_text(
            122,
            197,
            "\u7ef4\u5ea6",
            160,
            21,
            self.theme.primary,
            800,
            max_lines=1,
            extra_attrs='data-structural-anchor="comparison-dimension-header comparison-matrix"',
        )
        c.wrapped_text(
            392,
            197,
            left_title,
            280,
            21,
            self.theme.primary,
            800,
            max_lines=1,
            extra_attrs='data-structural-anchor="comparison-option comparison-option-left comparison-matrix"',
        )
        c.wrapped_text(
            792,
            197,
            right_title,
            320,
            21,
            self.theme.primary,
            800,
            max_lines=1,
            extra_attrs='data-structural-anchor="comparison-option comparison-option-right comparison-matrix"',
        )
        c.line(320, 216, 320, 566, self.theme.line, 1)
        c.line(720, 216, 720, 566, self.theme.line, 1)

        for idx, raw in enumerate(rows):
            item = raw if isinstance(raw, dict) else {
                "dimension": f"\u7ef4\u5ea6{idx + 1}",
                "left": str(raw),
                "right": "",
            }
            block = row_blocks[idx]
            box = row_boxes[idx]
            if box is None:
                return False
            x, y, w, h = box
            slot_attrs = self._slot_text_attrs(block)
            pad = 16.0
            gap = 24.0
            dim_w = min(220.0, max(180.0, w * 0.2))
            value_w = max(120.0, (w - (pad * 2.0) - (gap * 2.0) - dim_w) / 2.0)
            text_y = y + min(h - 12.0, 30.0)
            dim_x = x + pad
            left_x = dim_x + dim_w + gap
            right_x = left_x + value_w + gap

            c.line(x, y + h, x + w, y + h, self.theme.line, 1, 0.55)
            c.wrapped_text(
                dim_x,
                text_y,
                pick(item, "dimension", default=f"\u7ef4\u5ea6{idx + 1}"),
                dim_w,
                17,
                self.theme.primary,
                800,
                max_lines=2,
                min_size=14,
                extra_attrs=slot_attrs,
            )
            c.wrapped_text(
                left_x,
                text_y,
                pick(item, "left", default="-"),
                value_w,
                15,
                self.theme.muted,
                max_lines=2,
                min_size=13,
                extra_attrs=slot_attrs,
            )
            c.wrapped_text(
                right_x,
                text_y,
                pick(item, "right", default="-"),
                value_w,
                15,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=13,
                extra_attrs=slot_attrs,
            )

        sx, sy, sw, sh = summary_box
        c.rect(sx, sy, sw, sh, self.theme.accent, rx=4)
        c.wrapped_text(
            sx + 16.0,
            sy + min(sh - 12.0, 35.0),
            pick(d, "summary", default="\u7ed3\u8bba\u6761"),
            max(120.0, sw - 32.0),
            20,
            "#FFFFFF",
            800,
            max_lines=1,
            min_size=16,
            extra_attrs=summary_attrs,
        )
        c.footer()
        return True

    def comparison_matrix_summarybar(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        if self._render_comparison_matrix_summarybar_with_slots(c, d, title):
            return
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        c.card(80, 160, 1120, 452)
        left_title = pick(d, "left_title", default="方案A")
        right_title = pick(d, "right_title", default="方案B")
        c.rect(80, 160, 1120, 56, self.theme.soft, stroke=self.theme.line, sw=1, rx=0)
        c.text(122, 197, "维度", 21, self.theme.primary, 800)
        c.text(392, 197, left_title, 21, self.theme.primary, 800)
        c.text(792, 197, right_title, 21, self.theme.primary, 800)
        c.line(320, 216, 320, 566, self.theme.line, 1)
        c.line(720, 216, 720, 566, self.theme.line, 1)

        rows = clamp_count(as_list(d.get("rows")), 5)
        row_h = 70
        for idx, raw in enumerate(rows):
            item = raw if isinstance(raw, dict) else {"dimension": f"维度{idx + 1}", "left": str(raw), "right": ""}
            y = 230 + idx * row_h
            c.line(80, y + 44, 1200, y + 44, self.theme.line, 1, 0.55)
            c.wrapped_text(
                96,
                y + 30,
                pick(item, "dimension", default=f"维度{idx + 1}"),
                210,
                17,
                self.theme.primary,
                800,
                max_lines=2,
                min_size=14,
            )
            c.wrapped_text(
                336, y + 28, pick(item, "left", default="-"), 360, 15, self.theme.muted, max_lines=2, min_size=13
            )
            c.wrapped_text(
                736,
                y + 28,
                pick(item, "right", default="-"),
                440,
                15,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=13,
            )

        c.rect(80, 624, 1120, 56, self.theme.accent, rx=4)
        c.wrapped_text(
            96, 659, pick(d, "summary", default="结论条"), 1080, 20, "#FFFFFF", 800, max_lines=1, min_size=16
        )
        c.footer()

    def regulation_table_two_axis(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1100, 34, self.theme.primary, 850, max_lines=2)
        columns = as_list(d.get("columns")) or ["标准名称", "内容摘要", "系统建设要求"]
        while len(columns) < 3:
            columns.append(f"列{len(columns) + 1}")
        rows = clamp_count(as_list(d.get("rows")), 7)
        c.card(80, 158, 1120, 486)
        c.rect(80, 158, 1120, 56, self.theme.soft, stroke=self.theme.line, sw=1, rx=0)
        col_x = [80, 250, 740, 1200]
        for idx in range(1, 3):
            c.line(col_x[idx], 158, col_x[idx], 644, self.theme.line, 1)
        for idx, col in enumerate(columns[:3]):
            c.wrapped_text(
                col_x[idx] + 12,
                194,
                as_text(col),
                col_x[idx + 1] - col_x[idx] - 24,
                19,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=15,
            )

        row_h = 58
        for ridx, row in enumerate(rows):
            y = 214 + ridx * row_h
            c.line(80, y, 1200, y, self.theme.line, 1, 0.55)
            cells: list[str] = []
            if isinstance(row, list):
                cells = [as_text(cell) for cell in row]
            elif isinstance(row, dict):
                if isinstance(row.get("cells"), list):
                    cells = [as_text(cell) for cell in row.get("cells", [])]
                else:
                    cells = [pick(row, "col1"), pick(row, "col2"), pick(row, "col3")]
            else:
                cells = [as_text(row)]
            while len(cells) < 3:
                cells.append("")
            c.wrapped_text(col_x[0] + 12, y + 34, cells[0], 146, 14, self.theme.primary, 700, max_lines=2, min_size=12)
            c.wrapped_text(col_x[1] + 12, y + 32, cells[1], 476, 13, self.theme.muted, max_lines=3, min_size=11)
            c.wrapped_text(col_x[2] + 12, y + 32, cells[2], 446, 13, self.theme.primary, 700, max_lines=3, min_size=11)

        c.wrapped_text(80, 676, pick(d, "footnote"), 1120, 13, self.theme.muted, max_lines=1, min_size=11)
        c.footer()

    def process_leftcards_centerflow(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        left_cards = clamp_count(as_list(d.get("left_cards")), 4)
        for idx, raw in enumerate(left_cards):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            y = 176 + idx * 118
            c.card(80, y, 290, 96)
            c.rect(80, y, 8, 96, self.palette[idx % len(self.palette)], rx=4)
            c.text(102, y + 34, pick(item, "title", default=f"要点{idx + 1}"), 24, self.theme.primary, 800)
            c.wrapped_text(
                102, y + 62, pick(item, "body", "description"), 252, 13, self.theme.muted, max_lines=2, min_size=11
            )

        c.ellipse(825, 404, 360, 156, self.theme.soft, stroke=self.theme.line, sw=2)
        nodes = clamp_count(as_list(d.get("flow_nodes")), 5)
        node_x = [520, 690, 860, 1030, 760]
        node_y = [230, 190, 230, 300, 364]
        for idx, raw in enumerate(nodes):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x = node_x[idx]
            y = node_y[idx]
            c.card(x - 90, y - 36, 180, 74)
            c.rect(x - 90, y - 36, 180, 10, self.palette[idx % len(self.palette)], rx=4)
            c.wrapped_text(
                x,
                y - 2,
                pick(item, "title", default=f"节点{idx + 1}"),
                156,
                16,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
                min_size=13,
            )
            if idx > 0:
                c.line(node_x[idx - 1] + 88, node_y[idx - 1], x - 88, y, self.theme.primary, 1.8, 0.45, arrow=True)

        systems = clamp_count(as_list(d.get("bottom_systems")), 7)
        c.rect(430, 548, 760, 112, self.theme.card, stroke=self.theme.line, sw=1, rx=8)
        c.text(452, 578, "接入系统", 18, self.theme.primary, 800)
        for idx, label in enumerate(systems):
            x = 454 + (idx % 4) * 180
            y = 592 + (idx // 4) * 42
            c.rect(x, y, 156, 30, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
            c.text(x + 78, y + 21, as_text(label), 14, self.theme.primary, 700, "middle")
        c.footer()

    def architecture_three_zones(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        if self._render_architecture_three_zones_with_slots(c, d, title):
            return
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1100, 36, self.theme.primary, 850, max_lines=1)
        left = clamp_count(as_list(d.get("left_systems")), 7)
        core = clamp_count(as_list(d.get("core_modules")), 4)
        right = clamp_count(as_list(d.get("right_modules")), 4)
        storage = clamp_count(as_list(d.get("storage")), 4)

        c.rect(80, 160, 140, 460, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
        c.text(150, 194, "外部系统", 20, self.theme.primary, 800, "middle")
        for idx, item in enumerate(left):
            y = 224 + idx * 54
            c.rect(98, y, 104, 36, self.theme.card, stroke=self.theme.line, sw=1, rx=4)
            c.text(150, y + 24, as_text(item), 13, self.theme.primary, 700, "middle")

        c.rect(280, 160, 650, 360, self.theme.card, stroke=self.theme.line, sw=1, rx=8)
        c.text(605, 194, "追溯系统", 22, self.theme.primary, 850, "middle")
        module_pos = [(310, 220), (620, 220), (310, 368), (620, 368)]
        for idx, raw in enumerate(core):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x, y = module_pos[idx]
            c.card(x, y, 280, 128, self.theme.soft if idx % 2 else self.theme.card)
            c.rect(x, y, 280, 8, self.palette[idx % len(self.palette)], rx=4)
            c.wrapped_text(
                x + 18,
                y + 35,
                pick(item, "title", default=f"模块{idx + 1}"),
                244,
                18,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=14,
            )
            c.wrapped_text(
                x + 18, y + 63, pick(item, "body", "description"), 244, 13, self.theme.muted, max_lines=3, min_size=11
            )
        c.line(220, 390, 280, 390, self.theme.primary, 2, 0.5, arrow=True)
        c.line(930, 390, 980, 390, self.theme.primary, 2, 0.5, arrow=True)

        c.rect(980, 160, 220, 460, self.theme.card, stroke=self.theme.line, sw=1, rx=6)
        c.text(1090, 194, "管理域", 20, self.theme.primary, 800, "middle")
        for idx, item in enumerate(right):
            y = 222 + idx * 104
            c.rect(998, y, 184, 86, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
            c.wrapped_text(
                1090, y + 50, as_text(item), 160, 16, self.theme.primary, 800, "middle", max_lines=2, min_size=13
            )

        c.rect(280, 536, 650, 84, self.theme.soft, stroke=self.theme.line, sw=1, rx=6)
        c.text(302, 566, "数据存储", 17, self.theme.primary, 800)
        for idx, item in enumerate(storage):
            x = 420 + idx * 122
            c.rect(x, 548, 112, 52, self.theme.card, stroke=self.theme.line, sw=1, rx=4)
            c.wrapped_text(
                x + 56, 579, as_text(item), 94, 12, self.theme.primary, 700, "middle", max_lines=2, min_size=10
            )
        c.footer()

    def maturity_matrix_radar(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 36, self.theme.primary, 850, max_lines=2)
        c.rect(80, 160, 760, 460, self.theme.card, stroke=self.theme.line, sw=1, rx=8)
        c.rect(80, 160, 760, 50, self.theme.soft, stroke=self.theme.line, sw=1, rx=0)
        c.text(104, 193, "维度", 16, self.theme.primary, 800)
        c.text(220, 193, "1分", 16, self.theme.primary, 800)
        c.text(345, 193, "2分", 16, self.theme.primary, 800)
        c.text(470, 193, "3分", 16, self.theme.primary, 800)
        c.text(595, 193, "4分", 16, self.theme.primary, 800)
        c.text(720, 193, "5分", 16, self.theme.primary, 800)
        c.line(180, 160, 180, 620, self.theme.line, 1)
        for gx in [300, 425, 550, 675]:
            c.line(gx, 210, gx, 620, self.theme.line, 1, 0.45)
        dimensions = clamp_count(as_list(d.get("dimensions")), 4)
        levels = clamp_count(as_list(d.get("levels")), 5)
        row_h = 102
        for idx, label in enumerate(dimensions):
            y = 226 + idx * row_h
            c.line(80, y + 62, 840, y + 62, self.theme.line, 1, 0.5)
            c.wrapped_text(94, y + 32, as_text(label), 76, 20, self.theme.primary, 800, max_lines=2, min_size=14)
            for lidx, raw in enumerate(levels):
                item = raw if isinstance(raw, dict) else {"desc": as_text(raw)}
                x = 194 + lidx * 125
                c.wrapped_text(
                    x, y + 24, pick(item, "desc", default="-"), 108, 12, self.theme.muted, max_lines=3, min_size=10
                )

        c.card(870, 160, 330, 260, self.theme.soft)
        cx, cy = 1035, 288
        r = 94
        for step in [0.2, 0.4, 0.6, 0.8, 1.0]:
            rr = r * step
            pts = []
            for i in range(4):
                angle = math.radians(-90 + i * 90)
                pts.append((cx + rr * math.cos(angle), cy + rr * math.sin(angle)))
            c.polygon(pts, "none", self.theme.line, 1, 0.45)
        radar = [0.45, 0.62, 0.58, 0.5]
        radar_pts = []
        for i, v in enumerate(radar):
            angle = math.radians(-90 + i * 90)
            radar_pts.append((cx + r * v * math.cos(angle), cy + r * v * math.sin(angle)))
        c.polygon(radar_pts, self.theme.accent, self.theme.accent, 2, 0.2)
        c.polyline(radar_pts + [radar_pts[0]], self.theme.accent, 3)
        c.text(cx, 402, "成熟度轮廓", 15, self.theme.primary, 800, "middle")

        points = clamp_count(as_list(d.get("summary_points")), 3)
        c.card(870, 438, 330, 182)
        c.text(892, 468, "评估结论", 18, self.theme.primary, 800)
        for idx, point in enumerate(points):
            y = 494 + idx * 40
            c.circle(902, y - 6, 4, self.theme.accent)
            c.wrapped_text(914, y, as_text(point), 268, 13, self.theme.muted, max_lines=2, min_size=11)
        c.footer()

    def stage_objectives_deliverables(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 36, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(80, 142, pick(d, "stage", default="阶段名称"), 1120, 24, self.theme.primary, 800, max_lines=1)
        c.card(80, 184, 1120, 432)

        labels = [("核心目标", 80, 198, 180), ("关键工作", 80, 320, 180), ("交付物", 80, 462, 180)]
        for text, x, y, h in labels:
            c.rect(x, y, 180, h, self.theme.accent, rx=0)
            c.wrapped_text(
                x + 90,
                y + h / 2 + 12,
                text,
                150,
                45 if text == "核心目标" else 40,
                "#FFFFFF",
                800,
                "middle",
                max_lines=2,
                min_size=30,
            )

        for start, end in [(198, 320), (320, 462), (462, 640)]:
            c.line(260, end, 1200, end, self.theme.line, 1)

        objectives = clamp_count(as_list(d.get("objectives")), 3)
        tasks = clamp_count(as_list(d.get("tasks")), 5)
        deliverables = clamp_count(as_list(d.get("deliverables")), 6)
        for idx, item in enumerate(objectives):
            y = 234 + idx * 42
            c.text(292, y, "–", 28, self.theme.primary, 800)
            c.wrapped_text(316, y, as_text(item), 860, 18, self.theme.primary, 700, max_lines=1, min_size=14)
        for idx, item in enumerate(tasks):
            y = 352 + idx * 24
            c.text(292, y, "–", 20, self.theme.primary, 800)
            c.wrapped_text(314, y, as_text(item), 860, 15, self.theme.muted, max_lines=1, min_size=12)
        cols = 2
        for idx, item in enumerate(deliverables):
            col = idx % cols
            row = idx // cols
            x = 292 + col * 430
            y = 494 + row * 40
            c.text(x, y, "–", 20, self.theme.primary, 800)
            c.wrapped_text(x + 22, y, as_text(item), 390, 16, self.theme.primary, 700, max_lines=1, min_size=12)
        c.footer()

    def case_study_evidence(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        c.card(80, 146, 1120, 110, self.theme.soft)
        c.wrapped_text(
            102,
            186,
            pick(d, "background", default="项目背景"),
            1072,
            18,
            self.theme.primary,
            700,
            max_lines=3,
            min_size=14,
        )

        c.rect(80, 274, 86, 338, self.theme.soft, stroke=self.theme.line, sw=1, rx=4)
        c.text(123, 332, "目", 42, self.theme.primary, 800, "middle")
        c.text(123, 384, "标", 42, self.theme.primary, 800, "middle")
        c.text(123, 466, "方", 42, self.theme.primary, 800, "middle")
        c.text(123, 518, "案", 42, self.theme.primary, 800, "middle")

        goals = clamp_count(as_list(d.get("goals")), 4)
        c.card(184, 274, 1016, 102)
        for idx, goal in enumerate(goals):
            y = 304 + idx * 20
            c.circle(204, y - 4, 4, self.palette[idx % len(self.palette)])
            c.wrapped_text(216, y, as_text(goal), 960, 14, self.theme.primary, 700, max_lines=1, min_size=11)

        blocks = clamp_count(as_list(d.get("evidence_blocks")), 3)
        widths = [320, 330, 330]
        x = 184
        for idx, raw in enumerate(blocks):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            w = widths[idx]
            c.card(x, 392, w, 220)
            c.rect(x, 392, w, 8, self.palette[idx % len(self.palette)], rx=4)
            c.wrapped_text(
                x + 16,
                424,
                pick(item, "title", default=f"证据块{idx + 1}"),
                w - 32,
                18,
                self.theme.primary,
                800,
                max_lines=2,
                min_size=14,
            )
            c.wrapped_text(
                x + 16, 458, pick(item, "body", "description"), w - 32, 13, self.theme.muted, max_lines=7, min_size=11
            )
            x += w + 18

        c.rect(184, 628, 1016, 42, self.theme.accent, rx=4)
        c.wrapped_text(
            196, 656, pick(d, "result", default="结果结论"), 988, 16, "#FFFFFF", 800, max_lines=1, min_size=13
        )
        c.footer()

    def sla_double_table(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        c.wrapped_text(80, 136, pick(d, "summary", "background"), 1120, 18, self.theme.muted, max_lines=2, min_size=14)
        c.card(80, 182, 520, 450)
        c.card(640, 182, 560, 450)

        c.rect(80, 182, 520, 52, self.theme.accent, rx=0)
        c.rect(640, 182, 560, 52, self.theme.secondary, rx=0)
        c.wrapped_text(
            96, 216, pick(d, "left_title", default="SLA指标与目标"), 488, 20, "#FFFFFF", 800, max_lines=1, min_size=15
        )
        c.wrapped_text(
            656, 216, pick(d, "right_title", default="严重级别定义"), 528, 20, "#FFFFFF", 800, max_lines=1, min_size=15
        )

        left_rows = clamp_count(as_list(d.get("left_rows")), 8)
        right_rows = clamp_count(as_list(d.get("right_rows")), 4)
        for idx, raw in enumerate(left_rows):
            item = raw if isinstance(raw, dict) else {"metric": str(raw)}
            y = 244 + idx * 48
            c.line(80, y, 600, y, self.theme.line, 1, 0.5)
            c.wrapped_text(
                96,
                y + 30,
                pick(item, "metric", default=f"指标{idx + 1}"),
                316,
                14,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=11,
            )
            c.wrapped_text(
                428, y + 30, pick(item, "target", "value"), 156, 14, self.theme.muted, 700, max_lines=2, min_size=11
            )
        c.line(420, 234, 420, 632, self.theme.line, 1)

        for idx, raw in enumerate(right_rows):
            item = raw if isinstance(raw, dict) else {"level": f"L{idx + 1}", "desc": str(raw)}
            y = 244 + idx * 98
            c.line(640, y, 1200, y, self.theme.line, 1, 0.5)
            c.wrapped_text(
                656,
                y + 30,
                pick(item, "level", default=f"等级{idx + 1}"),
                120,
                16,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=13,
            )
            c.wrapped_text(786, y + 26, pick(item, "desc", "body"), 398, 13, self.theme.muted, max_lines=4, min_size=11)
        c.line(776, 234, 776, 632, self.theme.line, 1)
        c.footer()

    def _render_roadmap_lane_milestones_with_slots(self, c: SvgCanvas, d: dict[str, Any], title: str) -> bool:
        phase_blocks = self._slot_group(d, "phases")
        if not phase_blocks:
            return False

        phase_items = clamp_count(as_list(d.get("phases")), len(phase_blocks))
        phase_boxes = [self._slot_box(block) for block in phase_blocks]
        if not phase_items or any(box is None for box in phase_boxes):
            return False

        summary_text = pick(d, "summary")
        summary_slot = self._slot_block(d, "summary")
        summary_box = self._slot_box(summary_slot) if summary_slot else None
        if summary_text and summary_box is None:
            return False

        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)

        valid_phase_boxes = [box for box in phase_boxes if box is not None]
        if not valid_phase_boxes:
            return False
        phase_top = min(box[1] for box in valid_phase_boxes)
        lane_y = phase_top + 22.0
        first_center = valid_phase_boxes[0][0] + valid_phase_boxes[0][2] / 2.0
        last_center = valid_phase_boxes[-1][0] + valid_phase_boxes[-1][2] / 2.0
        c.line(first_center, lane_y, last_center, lane_y, self.theme.line, 4)

        for idx, raw in enumerate(phase_items):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            block = phase_blocks[idx]
            box = phase_boxes[idx]
            if box is None:
                return False
            x, y, w, h = box
            center_x = x + w / 2.0
            color = self.palette[idx % len(self.palette)]
            slot_attrs = self._slot_text_attrs(block)
            phase_label = pick(item, "phase", default=f"P{idx + 1}")
            milestone_text = pick(item, "milestone", default=pick(item, "deliverable", default="Milestone"))
            card_y = y + 44.0
            card_h = max(120.0, h - 56.0)

            c.circle(center_x, lane_y, 16, color)
            if idx < len(valid_phase_boxes) - 1:
                next_box = valid_phase_boxes[idx + 1]
                next_center_x = next_box[0] + next_box[2] / 2.0
                c.line(center_x + 16, lane_y, next_center_x - 16, lane_y, self.theme.primary, 2, 0.35, arrow=True)

            c.wrapped_text(
                center_x,
                y + 18.0,
                phase_label,
                max(100.0, w - 20.0),
                15,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
                min_size=12,
                extra_attrs=slot_attrs,
            )
            c.card(x, card_y, w, card_h)
            c.rect(x, card_y, w, 8, color, rx=4)
            c.wrapped_text(
                x + 18.0,
                card_y + 34.0,
                pick(item, "title", default=f"Phase {idx + 1}"),
                max(120.0, w - 36.0),
                18,
                self.theme.primary,
                800,
                max_lines=2,
                min_size=14,
                extra_attrs=slot_attrs,
            )
            c.wrapped_text(
                x + 18.0,
                card_y + 64.0,
                pick(item, "body", "description"),
                max(120.0, w - 36.0),
                14,
                self.theme.muted,
                max_lines=4,
                min_size=11,
                extra_attrs=slot_attrs,
            )
            c.wrapped_text(
                x + 18.0,
                card_y + card_h - 22.0,
                f"Milestone: {milestone_text}",
                max(120.0, w - 36.0),
                12,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=10,
                extra_attrs=slot_attrs,
            )

        if summary_box is not None:
            sx, sy, sw, sh = summary_box
            summary_attrs = self._slot_text_attrs(summary_slot) if summary_slot else ""
            c.rect(sx, sy, sw, sh, self.theme.soft, stroke=self.theme.line, sw=1, rx=4)
            c.wrapped_text(
                sx + 16.0,
                sy + min(sh - 14.0, 28.0),
                summary_text,
                max(120.0, sw - 32.0),
                15,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=12,
                extra_attrs=summary_attrs,
            )

        c.footer()
        return True

    def roadmap_lane_milestones(self, c: SvgCanvas, d: dict[str, Any], title: str) -> None:
        if self._render_roadmap_lane_milestones_with_slots(c, d, title):
            return
        c.wrapped_text(80, 94, pick(d, "title", default=title), 1120, 34, self.theme.primary, 850, max_lines=2)
        phases = clamp_count(as_list(d.get("phases")), 4)
        c.line(120, 300, 1160, 300, self.theme.line, 4)
        c.rect(80, 338, 1120, 236, self.theme.soft, stroke=self.theme.line, sw=1, rx=8)
        if len(phases) <= 1:
            xs = [640.0]
        else:
            step = 830 / (len(phases) - 1)
            xs = [225 + idx * step for idx in range(len(phases))]
        for idx, raw in enumerate(phases):
            item = raw if isinstance(raw, dict) else {"title": str(raw)}
            x = xs[idx]
            color = self.palette[idx % len(self.palette)]
            c.circle(x, 300, 20, color)
            if idx < len(phases) - 1:
                c.line(x + 20, 300, xs[idx + 1] - 20, 300, self.theme.primary, 2, 0.35, arrow=True)
            c.wrapped_text(
                x,
                272,
                pick(item, "phase", default=f"P{idx + 1}"),
                120,
                16,
                self.theme.primary,
                800,
                "middle",
                max_lines=1,
                min_size=12,
            )
            c.card(x - 145, 356, 290, 194)
            c.rect(x - 145, 356, 290, 8, color, rx=4)
            c.wrapped_text(
                x - 126,
                392,
                pick(item, "title", default=f"阶段{idx + 1}"),
                252,
                19,
                self.theme.primary,
                800,
                max_lines=1,
                min_size=14,
            )
            c.wrapped_text(
                x - 126, 422, pick(item, "body", "description"), 252, 14, self.theme.muted, max_lines=4, min_size=11
            )
            c.wrapped_text(
                x - 126,
                508,
                "里程碑: " + pick(item, "milestone", default=pick(item, "deliverable", default="阶段验收")),
                252,
                12,
                self.theme.primary,
                700,
                max_lines=2,
                min_size=10,
            )

        c.rect(80, 594, 1120, 42, self.theme.soft, stroke=self.theme.line, sw=1, rx=4)
        c.wrapped_text(
            96,
            620,
            pick(d, "summary", default="路线图摘要"),
            1080,
            15,
            self.theme.primary,
            700,
            max_lines=1,
            min_size=12,
        )
        c.footer()
