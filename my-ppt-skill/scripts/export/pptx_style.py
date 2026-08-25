from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

from .svg_utils import PRESENTATION_ATTRS, resolve_attr, svg_attr

PX_PER_INCH = 96


def px(value: float | int) -> int:
    return Inches(float(value) / PX_PER_INCH)


def pt_from_px(value: float | int) -> int:
    return Pt(float(value) * 0.75)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def opacity_number(value: str | None, default: float = 1.0) -> float:
    if value is None:
        return default
    return clamp(number(value, default))


def number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else default


def svg_color(value: str | None) -> RGBColor | None:
    if not value or value == "none":
        return None
    value = value.strip()
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) == 3:
            hex_value = "".join(ch * 2 for ch in hex_value)
        if len(hex_value) == 6:
            return RGBColor.from_string(hex_value.upper())
    match = re.match(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)", value)
    if match:
        return RGBColor(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return None


def remove_children(parent, tag_name: str) -> None:
    for child in list(parent):
        if child.tag == qn(tag_name):
            parent.remove(child)


def add_alpha(parent, opacity: float) -> None:
    color = parent.find(f".//{qn('a:srgbClr')}")
    if color is None:
        return
    remove_children(color, "a:alpha")
    if opacity >= 0.999:
        return
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(int(clamp(opacity) * 100000)))
    color.append(alpha)


def shape_sp_pr(shape):
    return shape._element.find(qn("p:spPr"))


def set_shape_fill(shape, color_value: str | None, opacity: float = 1.0) -> None:
    color = svg_color(color_value)
    if color is None:
        shape.fill.background()
        return
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    sp_pr = shape_sp_pr(shape)
    solid_fill = sp_pr.find(qn("a:solidFill")) if sp_pr is not None else None
    if solid_fill is not None:
        add_alpha(solid_fill, opacity)


def set_shape_line(
    shape,
    color_value: str | None,
    width_value: str | None = None,
    opacity: float = 1.0,
    arrow_end: bool = False,
) -> None:
    color = svg_color(color_value)
    if color is None:
        shape.line.fill.background()
        return
    shape.line.color.rgb = color
    width = max(number(width_value, 1), 0.5)
    shape.line.width = pt_from_px(width)
    sp_pr = shape_sp_pr(shape)
    line = sp_pr.find(qn("a:ln")) if sp_pr is not None else None
    if line is not None:
        solid_fill = line.find(qn("a:solidFill"))
        if solid_fill is not None:
            add_alpha(solid_fill, opacity)
        if arrow_end:
            remove_children(line, "a:tailEnd")
            tail = OxmlElement("a:tailEnd")
            tail.set("type", "triangle")
            tail.set("w", "med")
            tail.set("len", "med")
            line.append(tail)


def add_outer_shadow(shape, opacity: float = 0.16) -> None:
    sp_pr = shape_sp_pr(shape)
    if sp_pr is None:
        return
    remove_children(sp_pr, "a:effectLst")
    effect_lst = OxmlElement("a:effectLst")
    shadow = OxmlElement("a:outerShdw")
    shadow.set("blurRad", "127000")
    shadow.set("dist", "38100")
    shadow.set("dir", "5400000")
    shadow.set("rotWithShape", "0")
    color = OxmlElement("a:srgbClr")
    color.set("val", "101216")
    alpha = OxmlElement("a:alpha")
    alpha.set("val", str(int(clamp(opacity) * 100000)))
    color.append(alpha)
    shadow.append(color)
    effect_lst.append(shadow)
    sp_pr.append(effect_lst)


def element_context(elem: ET.Element, inherited: dict[str, str | float]) -> dict[str, str | float]:
    context = dict(inherited)
    element_opacity = svg_attr(elem, "opacity")
    if element_opacity is not None:
        context["_opacity"] = float(context.get("_opacity", 1.0)) * opacity_number(element_opacity)
    for name in PRESENTATION_ATTRS - {"opacity"}:
        value = svg_attr(elem, name)
        if value is not None:
            context[name] = value
    return context


def effective_opacity(
    elem: ET.Element,
    inherited: dict[str, str | float],
    kind: str,
) -> float:
    base = float(inherited.get("_opacity", 1.0))
    if kind == "fill":
        return base * opacity_number(resolve_attr(elem, inherited, "fill-opacity"), 1.0)
    if kind == "stroke":
        return base * opacity_number(resolve_attr(elem, inherited, "stroke-opacity"), 1.0)
    return base


def has_shadow(elem: ET.Element) -> bool:
    filter_value = svg_attr(elem, "filter", "") or ""
    return "shadow" in filter_value.lower()


def marker_end(elem: ET.Element) -> bool:
    value = svg_attr(elem, "marker-end", "") or ""
    return bool(value and value != "none")

