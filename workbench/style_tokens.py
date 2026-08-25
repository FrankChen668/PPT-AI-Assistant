from __future__ import annotations

import re
from typing import Any


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _parse_rgb(text: str) -> list[tuple[int, int, int]]:
    values: list[tuple[int, int, int]] = []
    pattern = re.compile(r"RGB\s*\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", re.I)
    for matched in pattern.finditer(str(text or "")):
        r, g, b = (int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))
        if all(0 <= value <= 255 for value in (r, g, b)):
            values.append((r, g, b))
    return values


def _extract_labeled_rgb(prompt_text: str, labels: tuple[str, ...]) -> str:
    source = str(prompt_text or "")
    for segment in re.split(r"[\r\n。；;]", source):
        clean = segment.strip()
        if not clean:
            continue
        if not any(label in clean for label in labels):
            continue
        rgb_values = _parse_rgb(clean)
        if rgb_values:
            return _rgb_to_hex(*rgb_values[0])
    return ""


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(value: int) -> float:
        normalized = value / 255
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(value) for value in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _hex_to_rgb(value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return None
    return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))


def _contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    lighter = max(_relative_luminance(a), _relative_luminance(b))
    darker = min(_relative_luminance(a), _relative_luminance(b))
    return (lighter + 0.05) / (darker + 0.05)


def _ensure_safe_text_background_contrast(tokens: dict[str, Any], fallback_background: object) -> None:
    text_rgb = _hex_to_rgb(tokens.get("text_color"))
    bg_rgb = _hex_to_rgb(tokens.get("background_color"))
    if text_rgb is None or bg_rgb is None:
        return
    if _contrast_ratio(text_rgb, bg_rgb) >= 4.5:
        return
    fallback = str(fallback_background or "").strip()
    fallback_rgb = _hex_to_rgb(fallback)
    if fallback_rgb is not None and _contrast_ratio(text_rgb, fallback_rgb) >= 4.5:
        tokens["background_color"] = fallback.upper()
        return
    tokens["background_color"] = "#FFFFFF"


def _extract_background_rgb(prompt_text: str) -> str:
    source = str(prompt_text or "")
    for segment in re.split(r"[\r\n。；;]", source):
        clean = segment.strip()
        if not clean or not any(label in clean for label in ("背景色", "底色")):
            continue
        rgb_values = _parse_rgb(clean)
        if not rgb_values:
            continue
        lightest = max(rgb_values, key=_relative_luminance)
        return _rgb_to_hex(*lightest)
    return ""


def canonicalize_style_tokens(style: dict[str, Any], prompt_text: str) -> dict[str, Any]:
    """Return style tokens with prompt-explicit colors taking precedence over profile defaults."""
    tokens = dict(style or {})
    source = str(prompt_text or "")

    primary_override = _extract_labeled_rgb(source, ("主色调", "主色", "主色系"))
    accent_override = _extract_labeled_rgb(source, ("辅助色", "次色", "强调色", "酒红", "暗红"))
    background_override = _extract_background_rgb(source)

    has_override = False
    if primary_override:
        tokens["primary_color"] = primary_override
        has_override = True
    if accent_override:
        tokens["accent_color"] = accent_override
        has_override = True
    if background_override:
        tokens["background_color"] = background_override
        has_override = True

    _ensure_safe_text_background_contrast(tokens, (style or {}).get("background_color"))
    tokens["style_source"] = "prompt_explicit" if has_override else "profile_default"
    return tokens
