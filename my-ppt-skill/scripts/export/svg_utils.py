from __future__ import annotations

import re
import xml.etree.ElementTree as ET

PRESENTATION_ATTRS = {
    "fill",
    "fill-opacity",
    "stroke",
    "stroke-width",
    "stroke-opacity",
    "stroke-linecap",
    "stroke-linejoin",
    "font-family",
    "font-size",
    "font-weight",
    "text-anchor",
    "opacity",
}

INHERITABLE_ATTRS = {
    "fill",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "fill-opacity",
    "stroke-opacity",
    "font-family",
    "font-size",
    "font-weight",
    "text-anchor",
}


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def style_map(elem: ET.Element) -> dict[str, str]:
    style = elem.get("style") or ""
    pairs = [part.strip() for part in style.split(";") if ":" in part]
    return {key.strip(): value.strip() for key, value in (part.split(":", 1) for part in pairs)}


def svg_attr(elem: ET.Element, name: str, default: str | None = None) -> str | None:
    return elem.get(name) or style_map(elem).get(name) or default


def resolve_attr(
    elem: ET.Element,
    inherited: dict[str, str | float],
    name: str,
    default: str | None = None,
) -> str | None:
    value = svg_attr(elem, name)
    if value is not None:
        return value
    inherited_value = inherited.get(name)
    if inherited_value is not None:
        return str(inherited_value)
    return default


def number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    match = re.search(r"[-+]?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else default


def parse_points(value: str | None) -> list[tuple[float, float]]:
    if not value:
        return []
    matches = re.findall(r"([-+]?\d+(?:\.\d+)?)[,\s]+([-+]?\d+(?:\.\d+)?)", value.strip())
    return [(float(x), float(y)) for x, y in matches]


def path_points(d: str | None) -> tuple[list[tuple[float, float]], bool]:
    if not d:
        return [], False

    tokens = re.findall(r"[MmLlHhVvZz]|[-+]?\d+(?:\.\d+)?", d)
    points: list[tuple[float, float]] = []
    closed = False
    current = (0.0, 0.0)
    command = ""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.match(r"[A-Za-z]", token):
            command = token
            if command in {"Z", "z"}:
                closed = True
            i += 1
            continue

        absolute = command.isupper()
        cmd = command.upper()
        if cmd in {"M", "L"} and i + 1 < len(tokens):
            x = float(tokens[i])
            y = float(tokens[i + 1])
            if not absolute:
                x += current[0]
                y += current[1]
            current = (x, y)
            points.append(current)
            i += 2
        elif cmd == "H":
            x = float(tokens[i])
            if not absolute:
                x += current[0]
            current = (x, current[1])
            points.append(current)
            i += 1
        elif cmd == "V":
            y = float(tokens[i])
            if not absolute:
                y += current[1]
            current = (current[0], y)
            points.append(current)
            i += 1
        else:
            i += 1

    return points, closed


def text_lines(elem: ET.Element) -> list[str]:
    tspans = [child for child in elem if local_name(child.tag) == "tspan"]
    if tspans:
        return [(child.text or "").strip() for child in tspans if (child.text or "").strip()]
    value = (elem.text or "").strip()
    return [value] if value else []


def extract_inheritable_styles(elem: ET.Element) -> dict[str, str]:
    """Extract inheritable presentation attributes from element, including style=."""
    styles: dict[str, str] = {}
    for attr in INHERITABLE_ATTRS:
        val = svg_attr(elem, attr)
        if val is not None:
            styles[attr] = val
    return styles

