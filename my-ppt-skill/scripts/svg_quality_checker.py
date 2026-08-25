#!/usr/bin/env python3
"""SVG quality checks aligned with PPT export compatibility.

This is inspired by ppt-master's svg_quality_checker, tailored to this repo's
1280x720 canvas + safe area conventions and our banned feature set.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from config_registry import get_canvas_spec, get_svg_forbidden_rules


@dataclass(frozen=True)
class SvgQualityResult:
    path: str
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"', re.IGNORECASE)
_FORBIDDEN_RULES = get_svg_forbidden_rules()
_FORBIDDEN_ELEMENTS = set(_FORBIDDEN_RULES.get("elements", set()))
_FORBIDDEN_ATTRIBUTES = set(_FORBIDDEN_RULES.get("attributes", set()))
_FORBIDDEN_PATTERNS = tuple(_FORBIDDEN_RULES.get("patterns", tuple()))

_DEFAULT_CANVAS = get_canvas_spec("ppt169")
# Skip contrast on likely footer / watermark band (see design footers ~y=675).
_CONTRAST_FOOTER_Y_MIN_RATIO = 635.0 / 720.0
# Ratio below this always fails (near-invisible regardless of hue).
_CONTRAST_CATASTROPHE_BELOW = 1.25
# Between this and ~2.0, fail only when **both** colors are very light (white/cream on off-white).
_CONTRAST_LIGHT_PAIR_RATIO_BELOW = 2.0
_CONTRAST_LIGHT_PAIR_DARKER_LUM_MIN = 0.92
# Warn between error threshold and a pragmatic floor (accent labels often land ~2.8:1 on light gray).
_CONTRAST_WARN_BELOW = 2.5
# Large glyphs (badges, step numbers): relax toward WCAG 鈥渓arge text鈥?3:1 where impractical on brand fills.
_CONTRAST_WARN_BELOW_LARGE = 2.25
_CONTRAST_LARGE_FONT_MIN = 18.0
_CONTRAST_LABEL_FONT_MAX = 13.0
_CONTRAST_LABEL_MAX_CHARS = 10
_CONTRAST_NUMERIC_DECORATION_FONT_MIN = 28.0
_CONTRAST_NUMERIC_DECORATION_MAX_DIGITS = 3
# Ignore very transparent decorations.
_CONTRAST_MIN_OPACITY = 0.88
_MARKER_REF_ATTRS = ("marker-start", "marker-mid", "marker-end", "marker")
_OPTIONAL_MARKER_IDS = {"arrow"}
_UNSAFE_URL_PREFIXES = ("http://", "https://", "javascript:", "data:")
_SAFE_EMBEDDED_IMAGE_RE = re.compile(
    r"^data:image/(?:png|jpe?g);base64,[a-z0-9+/=\s]+$",
    re.IGNORECASE,
)


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    text = value.strip().replace("px", "")
    try:
        return float(text)
    except ValueError:
        return default


def _hex_to_linear_rgb(hex_color: str) -> tuple[float, float, float] | None:
    s = hex_color.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return None
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError:
        return None

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return lin(r), lin(g), lin(b)


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    la = _relative_luminance(a)
    lb = _relative_luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


def _parse_fill_rgb(fill: str | None) -> tuple[float, float, float] | None:
    if not fill or fill.strip().lower() in {"none", "transparent"}:
        return None
    raw = fill.strip()
    if raw.lower() in {"currentcolor", "currentColor"}:
        return None
    if raw.startswith("#"):
        return _hex_to_linear_rgb(raw)
    return None


def _apply_opacity(
    rgb: tuple[float, float, float],
    element: ET.Element,
    canvas_bg: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> tuple[float, float, float]:
    """Blend rgb with canvas_bg by the element's effective opacity.

    Reads fill-opacity (SVG paint opacity) and opacity (generic element opacity).
    Both are CSS-style multipliers in [0, 1]; default 1.0 means fully opaque.
    """
    fill_opacity = _number(element.get("fill-opacity"), 1.0)
    elem_opacity = _number(element.get("opacity"), 1.0)
    effective = max(0.0, min(1.0, fill_opacity * elem_opacity))
    if effective >= 1.0:
        return rgb
    # Alpha blend: result = fill * alpha + background * (1 - alpha)
    return tuple(c * effective + bg * (1.0 - effective) for c, bg in zip(rgb, canvas_bg))


def _fill_from_style_attr(style: str | None) -> str | None:
    if not style:
        return None
    match = re.search(r"(?:^|;)\s*fill\s*:\s*([^;]+)", style, re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def _element_fill_value(el: ET.Element) -> str | None:
    fill = el.get("fill")
    if fill is not None and str(fill).strip():
        return str(fill).strip()
    return _fill_from_style_attr(el.get("style"))


def _resolve_inherited_fill(el: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> str | None:
    current: ET.Element | None = el
    while current is not None:
        fill = _element_fill_value(current)
        if fill:
            return fill
        current = parent_map.get(current)
    return None


def _iter_paint_order(root: ET.Element):
    """Depth-first paint order, skipping top-level <defs> subtrees."""
    for child in root:
        if _local_name(child.tag) == "defs":
            continue
        yield from _depth_first_paint(child)


def _depth_first_paint(el: ET.Element):
    yield el
    for ch in el:
        yield from _depth_first_paint(ch)


def _rect_contains(x: float, y: float, w: float, h: float, px: float, py: float) -> bool:
    return x - 0.25 <= px <= x + w + 0.25 and y - 0.25 <= py <= y + h + 0.25


def _circle_contains(cx: float, cy: float, r: float, px: float, py: float) -> bool:
    return (px - cx) ** 2 + (py - cy) ** 2 <= (r + 1.0) ** 2


def _parse_polygon_points(raw: str | None) -> list[tuple[float, float]]:
    if not raw or not raw.strip():
        return []
    nums = [float(x) for x in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", raw)]
    if len(nums) < 6 or len(nums) % 2:
        return []
    return list(zip(nums[0::2], nums[1::2]))


def _path_axis_aligned_rect_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    """Return (x, y, w, h) for simple closed rect-like paths, else None.

    Accepts path streams that only use line-like + arc corner commands commonly
    emitted by finalize for rounded rectangles.
    """
    if not raw or not raw.strip():
        return None
    tokens = re.findall(r"[MmLlHhVvAaZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", raw)
    if not tokens:
        return None
    allowed = {"M", "L", "H", "V", "A", "Z", "m", "l", "h", "v", "a", "z"}
    points: list[tuple[float, float]] = []
    i = 0
    cmd: str | None = None
    cx = 0.0
    cy = 0.0
    sx = 0.0
    sy = 0.0
    closed = False

    def is_cmd(tok: str) -> bool:
        return len(tok) == 1 and tok.isalpha()

    while i < len(tokens):
        tok = tokens[i]
        if is_cmd(tok):
            if tok not in allowed:
                return None
            cmd = tok
            i += 1
            if cmd in {"Z", "z"}:
                cx, cy = sx, sy
                points.append((cx, cy))
                closed = True
            continue
        if cmd is None:
            return None

        if cmd in {"M", "m"}:
            if i + 1 >= len(tokens):
                return None
            x = float(tokens[i])
            y = float(tokens[i + 1])
            if cmd == "m":
                cx += x
                cy += y
            else:
                cx, cy = x, y
            sx, sy = cx, cy
            points.append((cx, cy))
            i += 2
            cmd = "L" if cmd == "M" else "l"
            continue

        if cmd in {"L", "l"}:
            if i + 1 >= len(tokens):
                return None
            x = float(tokens[i])
            y = float(tokens[i + 1])
            if cmd == "l":
                cx += x
                cy += y
            else:
                cx, cy = x, y
            points.append((cx, cy))
            i += 2
            continue

        if cmd in {"H", "h"}:
            x = float(tokens[i])
            cx = cx + x if cmd == "h" else x
            points.append((cx, cy))
            i += 1
            continue

        if cmd in {"V", "v"}:
            y = float(tokens[i])
            cy = cy + y if cmd == "v" else y
            points.append((cx, cy))
            i += 1
            continue

        if cmd in {"A", "a"}:
            if i + 6 >= len(tokens):
                return None
            x = float(tokens[i + 5])
            y = float(tokens[i + 6])
            if cmd == "a":
                cx += x
                cy += y
            else:
                cx, cy = x, y
            points.append((cx, cy))
            i += 7
            continue

        return None

    if not closed or len(points) < 4:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    w = max_x - min_x
    h = max_y - min_y
    if w <= 0.0 or h <= 0.0:
        return None
    return min_x, min_y, w, h


def _point_in_polygon(px: float, py: float, verts: list[tuple[float, float]]) -> bool:
    if len(verts) < 3:
        return False
    inside = False
    n = len(verts)
    j = n - 1
    for i in range(n):
        xi, yi = verts[i]
        xj, yj = verts[j]
        denom = (yj - yi) or 1e-9
        if (yi > py) != (yj > py) and (px < (xj - xi) * (py - yi) / denom + xi):
            inside = not inside
        j = i
    return inside


def _text_sample_point(elem: ET.Element, font_size: float) -> tuple[float, float]:
    x = _number(elem.get("x"))
    y = _number(elem.get("y"))
    anchor = (elem.get("text-anchor") or "start").strip()
    if anchor == "middle":
        px = x
    elif anchor == "end":
        px = x - min(4.0, font_size * 0.25)
    else:
        px = x + min(4.0, font_size * 0.25)
    py = y - font_size * 0.35
    return px, py


def _slide_background_rgb(
    root: ET.Element,
    canvas_w: float,
    canvas_h: float,
) -> tuple[tuple[float, float, float], bool]:
    """Return (linear RGB, found_explicit_rect). If no full-canvas rect, assume white."""
    for child in root:
        if _local_name(child.tag) != "rect":
            continue
        x, y = _number(child.get("x")), _number(child.get("y"))
        w, h = _number(child.get("width")), _number(child.get("height"))
        if x <= 1.0 and y <= 1.0 and w >= canvas_w - 1.0 and h >= canvas_h - 1.0:
            rgb = _parse_fill_rgb(child.get("fill"))
            if rgb is not None:
                return rgb, True
    return (1.0, 1.0, 1.0), False


def _text_visible_fragments(text_el: ET.Element) -> list[str]:
    parts: list[str] = []
    if (text_el.text or "").strip():
        parts.append((text_el.text or "").strip())
    for child in text_el:
        if _local_name(child.tag) != "tspan":
            continue
        if (child.text or "").strip():
            parts.append((child.text or "").strip())
        if (child.tail or "").strip():
            parts.append((child.tail or "").strip())
    if (text_el.tail or "").strip():
        parts.append((text_el.tail or "").strip())
    return [p for p in parts if p]


def _effective_fills_for_text(
    text_el: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
) -> list[str]:
    """Collect fill colors used on tspans (or the parent text) that carry visible text."""
    base_fill = _resolve_inherited_fill(text_el, parent_map)
    out: list[str] = []
    for child in text_el:
        if _local_name(child.tag) != "tspan":
            continue
        if not (child.text or "").strip():
            continue
        cfill = _resolve_inherited_fill(child, parent_map) or base_fill
        if cfill:
            out.append(cfill)
    if not out and _text_visible_fragments(text_el):
        if base_fill:
            out.append(base_fill)
    return out


def _is_short_label_text(fragments: list[str], font_size: float) -> bool:
    if font_size > _CONTRAST_LABEL_FONT_MAX:
        return False
    compact = re.sub(r"\s+", "", "".join(fragments))
    return 0 < len(compact) <= _CONTRAST_LABEL_MAX_CHARS


def _is_large_numeric_decoration_text(fragments: list[str], font_size: float) -> bool:
    if font_size < _CONTRAST_NUMERIC_DECORATION_FONT_MIN:
        return False
    compact = re.sub(r"\s+", "", "".join(fragments))
    if not compact.isdigit():
        return False
    return 1 <= len(compact) <= _CONTRAST_NUMERIC_DECORATION_MAX_DIGITS


def _has_unsafe_url(value: str | None) -> bool:
    if not value:
        return False
    text = value.strip().lower()
    if any(prefix in text for prefix in _UNSAFE_URL_PREFIXES):
        return True
    # Ban external marker refs such as url(http://...) while allowing url(#local-id).
    if "url(" in text and "url(#" not in text:
        return True
    return False


def _is_safe_embedded_image_href(tag: str, attr_name: str, value: str | None) -> bool:
    key = _local_name(attr_name).lower()
    return tag == "image" and key == "href" and bool(_SAFE_EMBEDDED_IMAGE_RE.fullmatch((value or "").strip()))


def _validate_marker_policy(root: ET.Element) -> list[str]:
    errors: list[str] = []
    marker_ids: set[str] = set()
    marker_refs: set[str] = set()
    parent_map = {child: parent for parent in root.iter() for child in parent}

    for elem in root.iter():
        tag = _local_name(elem.tag)
        parent = parent_map.get(elem)
        parent_tag = _local_name(parent.tag) if parent is not None else ""

        for attr_name, attr_value in elem.attrib.items():
            key = attr_name.lower()
            if key.startswith("on"):
                errors.append("Forbidden marker policy: script/event attribute is not allowed.")
                break
            if (
                _local_name(key) == "href"
                and _has_unsafe_url(attr_value)
                and not _is_safe_embedded_image_href(tag, key, attr_value)
            ):
                errors.append("Forbidden marker policy: external or script-like href is not allowed.")
                break
            if key in _MARKER_REF_ATTRS:
                raw = (attr_value or "").strip()
                if _has_unsafe_url(raw):
                    errors.append("Forbidden marker policy: external marker URL is not allowed.")
                    continue
                m = re.fullmatch(r"url\(#([^)]+)\)", raw)
                if m:
                    marker_refs.add(m.group(1))
                elif raw:
                    errors.append("Forbidden marker policy: marker reference must use local url(#id).")

        if tag != "marker":
            continue
        if parent_tag != "defs":
            errors.append("Forbidden <marker>: markers must be defined inside <defs>.")
        marker_id = (elem.get("id") or "").strip()
        if not marker_id:
            errors.append("Forbidden <marker>: marker must declare a non-empty id.")
        else:
            marker_ids.add(marker_id)

    for marker_id in sorted(marker_ids):
        if marker_id in _OPTIONAL_MARKER_IDS:
            continue
        if marker_id not in marker_refs:
            errors.append(f"Forbidden <marker>: marker #{marker_id} is defined but never referenced.")
    for marker_ref in sorted(marker_refs):
        if marker_ref not in marker_ids:
            errors.append(f"Forbidden <marker>: reference url(#{marker_ref}) points to missing marker.")
    return errors


def contrast_checks(
    root: ET.Element,
    path: str,
    *,
    canvas_w: float | None = None,
    canvas_h: float | None = None,
    footer_y_min: float | None = None,
) -> tuple[list[str], list[str]]:
    """WCAG-style contrast vs estimated local background (paint order) or slide canvas."""
    errors: list[str] = []
    warnings: list[str] = []
    if _local_name(root.tag) != "svg":
        return errors, warnings
    if canvas_w is None:
        canvas_w = float(_DEFAULT_CANVAS.width)
    if canvas_h is None:
        canvas_h = float(_DEFAULT_CANVAS.height)
    if footer_y_min is None:
        footer_y_min = canvas_h * _CONTRAST_FOOTER_Y_MIN_RATIO

    bg_rgb, bg_explicit = _slide_background_rgb(root, canvas_w, canvas_h)
    if not bg_explicit:
        warnings.append("Contrast: no full-canvas <rect> background found; assuming #FFFFFF for slide-level check.")

    parent_map = {child: parent for parent in root.iter() for child in parent}
    shapes: list[tuple[int, tuple[float, float, float], Callable[[float, float], bool]]] = []

    for idx, el in enumerate(_iter_paint_order(root)):
        ln = _local_name(el.tag)
        if ln == "rect":
            rgb = _parse_fill_rgb(el.get("fill"))
            if rgb is None:
                continue
            rgb = _apply_opacity(rgb, el, bg_rgb)
            rx, ry = _number(el.get("x")), _number(el.get("y"))
            rw, rh = _number(el.get("width")), _number(el.get("height"))

            def hit_rect(px: float, py: float, rx=rx, ry=ry, rw=rw, rh=rh) -> bool:
                return _rect_contains(rx, ry, rw, rh, px, py)

            shapes.append((idx, rgb, hit_rect))
        elif ln == "circle":
            rgb = _parse_fill_rgb(el.get("fill"))
            if rgb is None:
                continue
            rgb = _apply_opacity(rgb, el, bg_rgb)
            cx, cy, r = _number(el.get("cx")), _number(el.get("cy")), _number(el.get("r"))

            def hit_circ(px: float, py: float, cx=cx, cy=cy, r=r) -> bool:
                return _circle_contains(cx, cy, r, px, py)

            shapes.append((idx, rgb, hit_circ))
        elif ln == "polygon":
            rgb = _parse_fill_rgb(el.get("fill"))
            if rgb is None:
                continue
            rgb = _apply_opacity(rgb, el, bg_rgb)
            verts = _parse_polygon_points(el.get("points"))
            if len(verts) < 3:
                continue

            def hit_poly(px: float, py: float, verts=tuple(verts)) -> bool:
                return _point_in_polygon(px, py, list(verts))

            shapes.append((idx, rgb, hit_poly))
        elif ln == "path":
            rgb = _parse_fill_rgb(el.get("fill"))
            if rgb is None:
                continue
            rgb = _apply_opacity(rgb, el, bg_rgb)
            rect_bbox = _path_axis_aligned_rect_bbox(el.get("d"))
            if rect_bbox is None:
                continue
            rx, ry, rw, rh = rect_bbox

            def hit_path_rect(px: float, py: float, rx=rx, ry=ry, rw=rw, rh=rh) -> bool:
                return _rect_contains(rx, ry, rw, rh, px, py)

            shapes.append((idx, rgb, hit_path_rect))
        elif ln == "text":
            frags = _text_visible_fragments(el)
            if not frags:
                continue
            y = _number(el.get("y"))
            if y >= footer_y_min:
                continue
            opacity = _number(el.get("opacity"), 1.0)
            if opacity < _CONTRAST_MIN_OPACITY:
                continue

            font_size = _number(el.get("font-size"), 16.0)
            px, py = _text_sample_point(el, font_size)
            fills = _effective_fills_for_text(el, parent_map)
            label_like = _is_short_label_text(frags, font_size)
            numeric_decoration_like = _is_large_numeric_decoration_text(frags, font_size)
            if not fills:
                warnings.append(f"Contrast: <text> near y={y:.0f} has visible glyphs but no parseable fill (skipped).")
                continue

            best_i = -1
            local_bg = bg_rgb
            for si, rgb, hit_fn in shapes:
                if si >= idx:
                    continue
                if hit_fn(px, py) and si > best_i:
                    best_i = si
                    local_bg = rgb

            for fill in fills:
                ink = _parse_fill_rgb(fill)
                if ink is None:
                    warnings.append(f"Contrast: unhandled fill {fill!r} on <text> near y={y:.0f} (skipped).")
                    continue
                ratio = _contrast_ratio(ink, local_bg)
                loc = f"y~{y:.0f}px, ratio={ratio:.2f}:1"
                lum_ink = _relative_luminance(ink)
                lum_bg = _relative_luminance(local_bg)
                dark_l = min(lum_ink, lum_bg)
                if ratio < _CONTRAST_CATASTROPHE_BELOW or (
                    ratio < _CONTRAST_LIGHT_PAIR_RATIO_BELOW and dark_l > _CONTRAST_LIGHT_PAIR_DARKER_LUM_MIN
                ):
                    if numeric_decoration_like:
                        warnings.append(
                            f"Contrast low numeric decoration ({loc}); large standalone number is treated as "
                            "decorative, but readability is weak."
                        )
                        continue
                    if label_like:
                        warnings.append(
                            f"Contrast low label ({loc}); short small label is likely "
                            "decorative, but readability is weak."
                        )
                        continue
                    errors.append(
                        f"Contrast too low ({loc}) - ink likely invisible or illegible on estimated background "
                        f"(check theme.text vs card/table fills)."
                    )
                else:
                    warn_floor = (
                        _CONTRAST_WARN_BELOW_LARGE if font_size >= _CONTRAST_LARGE_FONT_MIN else _CONTRAST_WARN_BELOW
                    )
                    if ratio < warn_floor and font_size >= 9.0:
                        warnings.append(
                            f"Contrast low ({loc}); consider darker text or richer background for body copy."
                        )

    return errors, warnings


def check_svg_text(content: str, path: str, expected_viewbox: str | None = None) -> SvgQualityResult:
    errors: list[str] = []
    warnings: list[str] = []

    lower = content.lower()

    # viewBox required
    m = _VIEWBOX_RE.search(content)
    if not m:
        errors.append("Missing viewBox attribute.")
    else:
        viewbox = m.group(1).strip()
        expected = expected_viewbox or _DEFAULT_CANVAS.viewbox
        if viewbox != expected:
            warnings.append(f"Unexpected viewBox: {viewbox!r} (expected {expected!r}).")

    # Forbidden / brittle features (shared SSOT from ppt_ai_core_standards)
    forbidden_elements = {name for name in _FORBIDDEN_ELEMENTS if name.lower() != "marker"}
    for elem in sorted(forbidden_elements):
        if f"<{elem.lower()}" in lower:
            errors.append(f"Forbidden <{elem}>.")

    for attr in sorted(_FORBIDDEN_ATTRIBUTES):
        if re.search(rf"\b{re.escape(attr)}\s*=", lower):
            errors.append(f"Forbidden attribute {attr}=.")

    for patt in _FORBIDDEN_PATTERNS:
        if patt.search(content):
            errors.append(f"Forbidden pattern matched: {patt.pattern}")

    return SvgQualityResult(path=path, errors=errors, warnings=warnings)


def check_svg_file(path: Path, canvas_key: str | None = None) -> SvgQualityResult:
    canvas = get_canvas_spec(canvas_key)
    canvas_w = float(canvas.width)
    canvas_h = float(canvas.height)
    footer_y_min = canvas_h * _CONTRAST_FOOTER_Y_MIN_RATIO
    content = path.read_text(encoding="utf-8", errors="replace")
    base = check_svg_text(content, str(path), expected_viewbox=canvas.viewbox)
    errors = list(base.errors)
    warnings = list(base.warnings)
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        warnings.append(f"Contrast check skipped: could not parse XML ({exc}).")
    else:
        errors.extend(_validate_marker_policy(root))
        ce, cw = contrast_checks(root, str(path), canvas_w=canvas_w, canvas_h=canvas_h, footer_y_min=footer_y_min)
        errors.extend(ce)
        warnings.extend(cw)
    return SvgQualityResult(path=str(path), errors=errors, warnings=warnings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check SVG compatibility for PPT export.")
    parser.add_argument("target", type=Path, help="SVG file or directory containing SVG files.")
    parser.add_argument("--canvas", help="Canvas key from design_spec/canvas-formats (e.g. ppt169, a4).")
    args = parser.parse_args(argv)

    target = args.target.resolve()
    paths: list[Path]
    if target.is_dir():
        paths = sorted(target.glob("*.svg"))
    else:
        paths = [target]

    results = [check_svg_file(path, canvas_key=args.canvas) for path in paths if path.exists()]
    errors = sum(len(r.errors) for r in results)
    warnings = sum(len(r.warnings) for r in results)
    ok = errors == 0

    for result in results:
        if result.errors or result.warnings:
            print(f"- {result.path}")
            for item in result.errors:
                print(f"  [E] {item}")
            for item in result.warnings:
                print(f"  [W] {item}")

    print(f"SVG quality: ok={ok} errors={errors} warnings={warnings}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
