#!/usr/bin/env python3
"""Pure helper for M3 design-token QA guardrails."""

from __future__ import annotations

import re
from typing import Any

from design_spec_tokens import parse_color_list, split_design_spec_lines
from profile_policy import resolve_profile_policy

CORE_TOKEN_ALIASES: dict[str, tuple[str, ...]] = {
    "text": ("text_color", "text", "font_color"),
    "background": ("background_color", "background", "canvas_background"),
    "card": ("card_bg", "card", "card_background"),
}

COLOR_TOKEN_KEYS = {
    "primary_color",
    "accent_color",
    "background_color",
    "text_color",
    "card_bg",
    "muted_color",
    "line_color",
    "soft_color",
    "secondary_accent",
    "canvas_background",
    "text",
    "background",
    "card",
    "data_palette",
}

FONT_LADDER_KEYS = ("font_ladder", "typography_ladder")
FONT_SIZE_ALIASES = {
    "title": ("font_title_size", "title_font_size", "h1_size", "title_size"),
    "body": ("font_body_size", "body_font_size", "body_size"),
    "caption": ("font_caption_size", "caption_font_size", "caption_size", "meta_size"),
}

HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
LADDER_ITEM_RE = re.compile(r"([a-zA-Z0-9_]+)\s+(\d+(?:\.\d+)?)\s*/")


def _normalize_hex(value: str) -> str | None:
    raw = (value or "").strip()
    if not HEX_COLOR_RE.fullmatch(raw):
        return None
    token = raw.lower().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    return f"#{token}"


def _hex_to_linear_rgb(hex_color: str) -> tuple[float, float, float] | None:
    normalized = _normalize_hex(hex_color)
    if normalized is None:
        return None
    token = normalized.lstrip("#")
    r = int(token[0:2], 16) / 255.0
    g = int(token[2:4], 16) / 255.0
    b = int(token[4:6], 16) / 255.0

    def lin(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4

    return lin(r), lin(g), lin(b)


def _contrast_ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la = 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2]
    lb = 0.2126 * b[0] + 0.7152 * b[1] + 0.0722 * b[2]
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


def _parse_design_spec(spec: str | dict[str, Any] | None) -> dict[str, str]:
    if isinstance(spec, dict):
        return {str(key).strip(): str(value).strip() for key, value in spec.items() if str(key).strip()}
    if not isinstance(spec, str):
        return {}
    return split_design_spec_lines(spec)


def _pick_core_value(tokens: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = tokens.get(alias)
        if value:
            return value
    return None


def _color_candidates(tokens: dict[str, str]) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    for key, value in tokens.items():
        lowered = key.strip().lower()
        if lowered.endswith("_color") or lowered in COLOR_TOKEN_KEYS:
            parts = parse_color_list(value)
            candidates[key] = parts or [value.strip()]
    return candidates


def _parse_font_sizes(tokens: dict[str, str]) -> dict[str, float]:
    out: dict[str, float] = {}
    ladder_text = ""
    for key in FONT_LADDER_KEYS:
        if tokens.get(key):
            ladder_text = tokens[key]
            break
    if ladder_text:
        for label, size in LADDER_ITEM_RE.findall(ladder_text):
            lowered = label.strip().lower()
            size_value = float(size)
            if lowered in {"h1", "title", "headline"}:
                out["title"] = max(out.get("title", 0.0), size_value)
            elif lowered in {"h2", "body", "content", "text"}:
                out["body"] = max(out.get("body", 0.0), size_value)
            elif lowered in {"caption", "meta", "footnote"}:
                out["caption"] = max(out.get("caption", 0.0), size_value)
    for role, aliases in FONT_SIZE_ALIASES.items():
        if role in out:
            continue
        for alias in aliases:
            raw = tokens.get(alias)
            if not raw:
                continue
            match = re.search(r"\d+(?:\.\d+)?", raw)
            if match:
                out[role] = float(match.group(0))
                break
    return out


def _finding(
    *,
    code: str,
    severity: str,
    message: str,
    token: str,
    recommendation: str,
) -> dict[str, str]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "token": token,
        "recommendation": recommendation,
    }


def run_design_token_guard(spec: str | dict[str, Any] | None, *, profile: str = "presentation") -> dict[str, Any]:
    policy = resolve_profile_policy(profile)
    tokens = _parse_design_spec(spec)
    findings: list[dict[str, str]] = []

    invalid_color_count = 0
    missing_token_count = 0
    contrast_warning_count = 0
    font_scale_warning_count = 0

    colors = _color_candidates(tokens)
    for key, values in colors.items():
        for value in values:
            if _normalize_hex(value) is None:
                invalid_color_count += 1
                findings.append(
                    _finding(
                        code="design-token-invalid-color",
                        severity="warning",
                        message=f"Color token {key} has invalid hex value: {value}.",
                        token=key,
                        recommendation="Use #RRGGBB or #RGB format.",
                    )
                )

    core_values: dict[str, str] = {}
    for role, aliases in CORE_TOKEN_ALIASES.items():
        core_value = _pick_core_value(tokens, aliases)
        if not core_value:
            missing_token_count += 1
            findings.append(
                _finding(
                    code="design-token-missing-core",
                    severity="warning",
                    message=f"Missing core token for {role}.",
                    token=role,
                    recommendation="Define core tokens for text/background/card in design_spec.md.",
                )
            )
        else:
            core_values[role] = core_value

    text_rgb = _hex_to_linear_rgb(core_values.get("text", ""))
    bg_rgb = _hex_to_linear_rgb(core_values.get("background", ""))
    card_rgb = _hex_to_linear_rgb(core_values.get("card", ""))
    min_contrast = float(policy.min_theme_contrast)
    if text_rgb is not None and bg_rgb is not None:
        ratio = _contrast_ratio(text_rgb, bg_rgb)
        if ratio < min_contrast:
            contrast_warning_count += 1
            findings.append(
                _finding(
                    code="design-token-low-contrast",
                    severity="warning",
                    message=f"text/background contrast is low ({ratio:.2f}:1 < {min_contrast:.1f}:1).",
                    token="text/background",
                    recommendation="Darken text or lighten background tokens.",
                )
            )
    if text_rgb is not None and card_rgb is not None:
        ratio = _contrast_ratio(text_rgb, card_rgb)
        if ratio < min_contrast:
            contrast_warning_count += 1
            findings.append(
                _finding(
                    code="design-token-low-contrast",
                    severity="warning",
                    message=f"text/card contrast is low ({ratio:.2f}:1 < {min_contrast:.1f}:1).",
                    token="text/card",
                    recommendation="Adjust text_color or card_bg to improve contrast.",
                )
            )

    font_sizes = _parse_font_sizes(tokens)
    if not {"title", "body", "caption"}.issubset(font_sizes):
        missing_token_count += 1
        findings.append(
            _finding(
                code="design-token-missing-core",
                severity="warning",
                message="Missing font hierarchy tokens for title/body/caption.",
                token="font_hierarchy",
                recommendation="Provide font_ladder (or equivalent title/body/caption size tokens).",
            )
        )
    else:
        title = font_sizes["title"]
        body = font_sizes["body"]
        caption = font_sizes["caption"]
        if title <= body or body <= caption:
            font_scale_warning_count += 1
            findings.append(
                _finding(
                    code="design-token-font-scale",
                    severity="advisory",
                    message=(
                        f"Font scale looks inverted or flat (title={title:g}, body={body:g}, caption={caption:g})."
                    ),
                    token="font_hierarchy",
                    recommendation="Keep title > body > caption with clear visual separation.",
                )
            )

    return {
        "profile": policy.key,
        "checked_token_count": len(tokens),
        "invalid_color_count": invalid_color_count,
        "missing_token_count": missing_token_count,
        "contrast_warning_count": contrast_warning_count,
        "font_scale_warning_count": font_scale_warning_count,
        "findings": findings,
    }
