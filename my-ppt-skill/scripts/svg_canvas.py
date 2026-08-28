#!/usr/bin/env python3
"""SVG primitive layer for AI-PPT rendering."""

from __future__ import annotations

from html import escape

from render_theme import H, Theme, W, as_text, fit_text_block


class SvgCanvas:
    def __init__(
        self,
        title: str,
        theme: Theme,
        background: str | None = None,
        semantic_roles: dict[str, str] | None = None,
    ) -> None:
        self.title = title
        self.theme = theme
        self.semantic_roles = semantic_roles or {}
        self.elements: list[str] = []
        self._arrow_marker_included = False
        self.defs: list[str] = [
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#101216" flood-opacity="0.12"/>'
            "</filter>",
        ]
        self.rect(0, 0, W, H, background or theme.canvas_background)

    @staticmethod
    def _semantic_key(value: str) -> str:
        return " ".join(as_text(value).split())

    def _with_semantic_role(self, value: str, extra_attrs: str = "") -> str:
        attrs = extra_attrs.strip()
        if "data-content-role=" in attrs:
            return attrs
        role = self.semantic_roles.get(self._semantic_key(value))
        semantic_attr = f'data-content-role="{escape(role, quote=True)}"' if role else ""
        return " ".join(part for part in (attrs, semantic_attr) if part)

    def add(self, value: str) -> None:
        self.elements.append(value)

    def _ensure_arrow_marker(self) -> None:
        if self._arrow_marker_included:
            return
        self.defs.append(
            '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            '<path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/>'
            "</marker>"
        )
        self._arrow_marker_included = True

    def rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: str,
        stroke: str = "none",
        sw: float = 1,
        rx: float = 0,
        opacity: float = 1,
        extra: str = "",
    ) -> None:
        self.add(
            f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{rx:g}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}" {extra}/>'
        )

    def circle(
        self,
        cx: float,
        cy: float,
        r: float,
        fill: str,
        stroke: str = "none",
        sw: float = 1,
        opacity: float = 1,
    ) -> None:
        self.add(
            f'<circle cx="{cx:g}" cy="{cy:g}" r="{r:g}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}"/>'
        )

    def ellipse(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        fill: str,
        stroke: str = "none",
        sw: float = 1,
        opacity: float = 1,
    ) -> None:
        self.add(
            f'<ellipse cx="{cx:g}" cy="{cy:g}" rx="{rx:g}" ry="{ry:g}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}"/>'
        )

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        stroke: str,
        sw: float = 2,
        opacity: float = 1,
        arrow: bool = False,
        extra_attrs: str = "",
    ) -> None:
        if arrow:
            self._ensure_arrow_marker()
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        self.add(
            f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" '
            f'stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}"{marker} {extra_attrs}/>'
        )

    def polygon(
        self,
        points: list[tuple[float, float]],
        fill: str,
        stroke: str = "none",
        sw: float = 1,
        opacity: float = 1,
    ) -> None:
        value = " ".join(f"{x:g},{y:g}" for x, y in points)
        self.add(
            f'<polygon points="{value}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}" opacity="{opacity:g}"/>'
        )

    def polyline(
        self,
        points: list[tuple[float, float]],
        stroke: str,
        sw: float = 3,
        fill: str = "none",
        opacity: float = 1,
        arrow: bool = False,
        extra_attrs: str = "",
    ) -> None:
        if arrow:
            self._ensure_arrow_marker()
        marker = ' marker-end="url(#arrow)"' if arrow else ""
        value = " ".join(f"{x:g},{y:g}" for x, y in points)
        self.add(
            f'<polyline points="{value}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:g}" '
            f'opacity="{opacity:g}"{marker} {extra_attrs}/>'
        )

    def image(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        href: str,
        *,
        content_role: str | None = None,
        element_id: str | None = None,
        opacity: float = 1,
    ) -> None:
        attrs = []
        if element_id:
            attrs.append(f'id="{escape(element_id, quote=True)}"')
        if content_role:
            attrs.append(f'data-content-role="{escape(content_role, quote=True)}"')
        opacity_attr = f' opacity="{opacity:g}"' if opacity < 1 else ""
        self.add(
            f'<image x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" '
            f'href="{escape(href, quote=True)}"{opacity_attr} {" ".join(attrs)}/>'
        )

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 18,
        color: str | None = None,
        weight: int = 400,
        anchor: str = "start",
        opacity: float = 1,
        family: str | None = None,
        extra_attrs: str = "",
    ) -> None:
        color = color or self.theme.text
        family = family or self.theme.font_body
        attrs = self._with_semantic_role(value, extra_attrs)
        self.add(
            f'<text x="{x:g}" y="{y:g}" font-family="{escape(family, quote=True)}" '
            f'font-size="{size:g}" font-weight="{weight}" text-anchor="{anchor}" '
            f'fill="{color}" opacity="{opacity:g}" {attrs}>{escape(as_text(value))}</text>'
        )

    def text_lines(
        self,
        x: float,
        y: float,
        values: list[str],
        size: float = 18,
        color: str | None = None,
        weight: int = 400,
        anchor: str = "start",
        line_height: float | None = None,
        opacity: float = 1,
        family: str | None = None,
        extra_attrs: str = "",
    ) -> None:
        if not values:
            return
        color = color or self.theme.text
        family = family or self.theme.font_body
        line_height = line_height or size * 1.35
        attrs = self._with_semantic_role(" ".join(values), extra_attrs)
        parts = [
            f'<text x="{x:g}" y="{y:g}" font-family="{escape(family, quote=True)}" '
            f'font-size="{size:g}" font-weight="{weight}" text-anchor="{anchor}" '
            f'fill="{color}" opacity="{opacity:g}" {attrs}>'
        ]
        for idx, line in enumerate(values):
            dy = 0 if idx == 0 else line_height
            parts.append(f'<tspan x="{x:g}" dy="{dy:g}">{escape(as_text(line))}</tspan>')
        parts.append("</text>")
        self.add("".join(parts))

    def wrapped_text(
        self,
        x: float,
        y: float,
        value: str,
        width: float,
        size: float = 18,
        color: str | None = None,
        weight: int = 400,
        anchor: str = "start",
        max_lines: int = 3,
        line_height: float | None = None,
        min_size: float | None = None,
        ellipsis: bool = True,
        shrink_step: float = 1.0,
        extra_attrs: str = "",
    ) -> None:
        lines, fitted_size = fit_text_block(
            value,
            width,
            size,
            max_lines=max_lines,
            min_font_size=min_size,
            step=shrink_step,
            ellipsis=ellipsis,
        )
        effective_line_height = line_height
        if line_height is not None and size > 0:
            effective_line_height = line_height * (fitted_size / size)
        attr_parts = [
            self._with_semantic_role(value, extra_attrs),
            f'data-max-width="{width:g}"',
            f'data-max-lines="{max_lines}"',
        ]
        merged_attrs = " ".join(part for part in attr_parts if part)
        self.text_lines(
            x,
            y,
            lines,
            size=fitted_size,
            color=color,
            weight=weight,
            anchor=anchor,
            line_height=effective_line_height,
            extra_attrs=merged_attrs,
        )

    def card(self, x: float, y: float, w: float, h: float, fill: str | None = None) -> None:
        self.rect(x, y, w, h, fill or self.theme.card, self.theme.line, 1, rx=8, extra='filter="url(#shadow)"')

    def footer(self, dark: bool = False) -> None:
        color = "#FFFFFF" if dark else self.theme.muted
        self.rect(0, 700, 1280, 8, self.theme.accent)
        self.text(80, 675, "AI PPT", 13, color, 500, opacity=0.7)

    def output(self) -> str:
        defs = "<defs>" + "".join(self.defs) + "</defs>"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
            f"<title>{escape(self.title)}</title>\n"
            f"{defs}\n" + "\n".join(self.elements) + "\n</svg>\n"
        )
