#!/usr/bin/env python3
"""Design tokens and text helpers for the AI-PPT SVG renderer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from design_spec_tokens import parse_data_palette, split_design_spec_lines

W = 1280
H = 720
SAFE_X = 60
SAFE_Y = 60
SAFE_W = 1160
SAFE_H = 600
FONT_STACK = "PingFang SC, Microsoft YaHei, Arial, sans-serif"

# When `design_spec.md` contains `- style: minimalist|tech|creative`, these presets
# seed primary/accent/background/card/text/muted (and optional line/soft) before any
# explicit per-key overrides from the same file.
STYLE_PRESETS: dict[str, dict[str, str]] = {
    "minimalist": {
        "primary_color": "#1A1A2E",
        "accent_color": "#E94560",
        "secondary_accent": "#E94560",
        "background_color": "#FFFFFF",
        "card_bg": "#F8F9FA",
        "text_color": "#1A1A2E",
        "muted_color": "#9A9AB0",
        "line_color": "#E3E7ED",
        "soft_color": "#EAFBF7",
    },
    "tech": {
        "primary_color": "#FFFFFF",
        "accent_color": "#00F5FF",
        "secondary_accent": "#00A8CC",
        "background_color": "#0D0D0D",
        "card_bg": "#1A1A1A",
        "text_color": "#FFFFFF",
        "muted_color": "#CCCCCC",
        "line_color": "#333333",
        "soft_color": "#252525",
    },
    "creative": {
        "primary_color": "#2D2D2D",
        "accent_color": "#6C63FF",
        "secondary_accent": "#FF6584",
        "background_color": "#FAFAFA",
        "card_bg": "#FFFFFF",
        "text_color": "#4A4A4A",
        "muted_color": "#9A9A9A",
        "line_color": "#E3E7ED",
        "soft_color": "#F0EEFF",
    },
    "executive_exhibit": {
        "primary_color": "#1B2537",
        "accent_color": "#00A3A3",
        "secondary_accent": "#FFD166",
        "background_color": "#F8FAFC",
        "card_bg": "#FFFFFF",
        "text_color": "#1A2233",
        "muted_color": "#667085",
        "line_color": "#D9E2EC",
        "soft_color": "#ECFDFB",
        "density_profile": "balanced",
        "hierarchy_profile": "clear",
        "accent_ratio": "0.18",
        "card_style": "outline",
        "rhythm_profile": "staggered",
    },
    "luxury_finance": {
        "primary_color": "#0F172A",
        "accent_color": "#C8A96B",
        "secondary_accent": "#1D4ED8",
        "background_color": "#F8F7F4",
        "card_bg": "#FFFFFF",
        "text_color": "#111827",
        "muted_color": "#6B7280",
        "line_color": "#D6D3D1",
        "soft_color": "#F3EFE6",
        "density_profile": "balanced",
        "hierarchy_profile": "clear",
        "accent_ratio": "0.16",
        "card_style": "soft",
        "rhythm_profile": "balanced",
    },
    "engineering_blueprint": {
        "primary_color": "#0F172A",
        "accent_color": "#0EA5E9",
        "secondary_accent": "#22D3EE",
        "background_color": "#F1F5F9",
        "card_bg": "#FFFFFF",
        "text_color": "#0F172A",
        "muted_color": "#475569",
        "line_color": "#CBD5E1",
        "soft_color": "#E0F2FE",
        "density_profile": "dense",
        "hierarchy_profile": "clear",
        "accent_ratio": "0.14",
        "card_style": "outline",
        "rhythm_profile": "tight",
    },
    "ai_product_keynote": {
        "primary_color": "#111827",
        "accent_color": "#4F46E5",
        "secondary_accent": "#22D3EE",
        "background_color": "#F8FAFC",
        "card_bg": "#FFFFFF",
        "text_color": "#111827",
        "muted_color": "#4B5563",
        "line_color": "#D1D5DB",
        "soft_color": "#EEF2FF",
        "density_profile": "balanced",
        "hierarchy_profile": "dramatic",
        "accent_ratio": "0.22",
        "card_style": "solid",
        "rhythm_profile": "staggered",
    },
    "policy_institutional": {
        "primary_color": "#1E3A8A",
        "accent_color": "#2563EB",
        "secondary_accent": "#DC2626",
        "background_color": "#F8FAFC",
        "card_bg": "#FFFFFF",
        "text_color": "#111827",
        "muted_color": "#6B7280",
        "line_color": "#D1D5DB",
        "soft_color": "#EFF6FF",
        "density_profile": "balanced",
        "hierarchy_profile": "clear",
        "accent_ratio": "0.12",
        "card_style": "outline",
        "rhythm_profile": "balanced",
    },
    "editorial_report": {
        "primary_color": "#1F2937",
        "accent_color": "#0EA5E9",
        "secondary_accent": "#14B8A6",
        "background_color": "#FFFFFF",
        "card_bg": "#F8FAFC",
        "text_color": "#111827",
        "muted_color": "#6B7280",
        "line_color": "#E5E7EB",
        "soft_color": "#F0F9FF",
        "density_profile": "balanced",
        "hierarchy_profile": "editorial",
        "accent_ratio": "0.15",
        "card_style": "soft",
        "rhythm_profile": "balanced",
    },
}

PROFILE_TOKENS: dict[str, dict[str, str]] = {
    "executive_exhibit": {
        "composition_grammar": "Hero headline + takeaway bar + asymmetric evidence modules",
        "rhythm_grammar": "Set tone -> evidence peak -> reset -> decisive close",
        "font_ladder": "H1 46/700 | H2 30/600 | Body 20/400 | Meta 14/400",
        "taboo_patterns": "repetitive_equal_cards;centered_title_every_page;data_without_conclusion_label",
    },
    "luxury_finance": {
        "composition_grammar": "Premium signal strip + KPI stage + risk/reward evidence pairing",
        "rhythm_grammar": "Claim -> valuation proof -> risk control -> confidence close",
        "font_ladder": "H1 44/700 | H2 30/600 | Body 19/400 | Meta 13/400",
        "taboo_patterns": "rainbow_palette;playful_iconography;crowded_table_without_highlight",
    },
    "engineering_blueprint": {
        "composition_grammar": "Layered system map + directional connectors + bounded annotation zones",
        "rhythm_grammar": "Context map -> module deep-dive -> integration evidence -> rollout checkpoints",
        "font_ladder": "H1 40/700 | H2 28/600 | Body 18/400 | Meta 13/400",
        "taboo_patterns": "floating_decorative_shapes;ambiguous_connection_direction;low_contrast_code_labels",
    },
    "ai_product_keynote": {
        "composition_grammar": "Hero promise + product reveal + proof cards with dominant metric",
        "rhythm_grammar": "Problem framing -> feature reveal -> proof demo -> momentum close",
        "font_ladder": "H1 48/700 | H2 30/600 | Body 20/400 | Meta 14/400",
        "taboo_patterns": "feature_wall_without_priority;uniform_slide_density;generic_stock_illustration_overuse",
    },
    "policy_institutional": {
        "composition_grammar": "Stable bilateral grid + policy rail + compliance evidence blocks",
        "rhythm_grammar": "Mandate framing -> policy mechanism -> implementation controls -> governance outcome",
        "font_ladder": "H1 42/700 | H2 29/600 | Body 19/400 | Meta 13/400",
        "taboo_patterns": "casual_tone_copy;aggressive_color_contrast;layout_jumps_without_section_rails",
    },
    "editorial_report": {
        "composition_grammar": "Headline deck + sectional evidence blocks + disciplined whitespace cadence",
        "rhythm_grammar": "Context -> analysis -> implication -> recommendation",
        "font_ladder": "H1 40/700 | H2 28/600 | Body 18/400 | Meta 13/400",
        "taboo_patterns": "ornamental_background_noise;overly_nested_bullets;identical_split_layout_repetition",
    },
}


@dataclass(frozen=True)
class Theme:
    primary: str = "#101216"
    accent: str = "#00C2A8"
    secondary: str = "#FF5A5F"
    gold: str = "#FFD166"
    background: str = "#F7F8FA"
    canvas_background: str = "#F7F8FA"
    card: str = "#FFFFFF"
    text: str = "#14171F"
    muted: str = "#68707D"
    line: str = "#E3E7ED"
    soft: str = "#EAFBF7"
    density_profile: str = "balanced"
    hierarchy_profile: str = "clear"
    accent_ratio: float = 0.18
    card_style: str = "soft"
    rhythm_profile: str = "balanced"
    style_profile: str = "editorial_report"
    composition_grammar: str = "Headline deck + sectional evidence blocks + disciplined whitespace cadence"
    rhythm_grammar: str = "Context -> analysis -> implication -> recommendation"
    font_ladder: str = "H1 40/700 | H2 28/600 | Body 18/400 | Meta 13/400"
    taboo_patterns: tuple[str, ...] = (
        "ornamental_background_noise",
        "overly_nested_bullets",
        "identical_split_layout_repetition",
    )
    data_palette: tuple[str, ...] = ()
    font_title: str = FONT_STACK
    font_body: str = FONT_STACK

    @classmethod
    def from_design_spec(cls, path: Path) -> "Theme":
        values = _parse_design_spec(path)
        style = values.get("style", "").strip().lower()

        if style in STYLE_PRESETS or style in PROFILE_TOKENS:
            merged: dict[str, str] = {}
            if style in STYLE_PRESETS:
                merged.update(STYLE_PRESETS[style])
            if style in PROFILE_TOKENS:
                merged.update(PROFILE_TOKENS[style])
                merged["style_profile"] = style
            # Explicit keys in design_spec always win.
            for key, val in values.items():
                if val is not None and str(val).strip():
                    merged[key] = val.strip()
            values = merged

        return cls(
            primary=values.get("primary_color", cls.primary),
            accent=values.get("accent_color", cls.accent),
            secondary=values.get("secondary_accent", cls.secondary),
            background=values.get("background_color", cls.background),
            canvas_background=values.get(
                "canvas_background",
                values.get("background_color", cls.canvas_background),
            ),
            card=values.get("card_bg", cls.card),
            text=values.get("text_color", cls.text),
            muted=values.get("muted_color", cls.muted),
            line=values.get("line_color", cls.line),
            soft=values.get("soft_color", cls.soft),
            density_profile=values.get("density_profile", cls.density_profile),
            hierarchy_profile=values.get("hierarchy_profile", cls.hierarchy_profile),
            accent_ratio=_parse_ratio(values.get("accent_ratio"), cls.accent_ratio),
            card_style=values.get("card_style", cls.card_style),
            rhythm_profile=values.get("rhythm_profile", cls.rhythm_profile),
            style_profile=values.get("style_profile", style or cls.style_profile),
            composition_grammar=values.get("composition_grammar", cls.composition_grammar),
            rhythm_grammar=values.get("rhythm_grammar", cls.rhythm_grammar),
            font_ladder=values.get("font_ladder", cls.font_ladder),
            taboo_patterns=_parse_token_list(values.get("taboo_patterns"), cls.taboo_patterns),
            data_palette=parse_data_palette(values.get("data_palette")),
            font_title=strip_quotes(values.get("font_title", cls.font_title)),
            font_body=strip_quotes(values.get("font_body", cls.font_body)),
        )


def _parse_design_spec(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return split_design_spec_lines(path.read_text(encoding="utf-8"))


def strip_quotes(value: str) -> str:
    return value.strip().strip('"')


def _parse_ratio(value: str | None, default: float) -> float:
    if value is None:
        return default
    raw = value.strip().strip("%")
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    if parsed > 1:
        parsed = parsed / 100.0
    return max(0.0, min(1.0, parsed))


def _parse_token_list(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    parts = [item.strip() for item in value.replace("|", ";").split(";")]
    parsed = tuple(item for item in parts if item)
    return parsed if parsed else default


def as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def pick(content: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        if key in content and content[key] not in (None, ""):
            return as_text(content[key])
    return default


def visual_width(text: str) -> float:
    width = 0.0
    for char in text:
        if char.isspace():
            width += 0.45
        elif ord(char) < 128:
            width += 0.58
        else:
            width += 1.0
    return width


def _append_ellipsis(text: str) -> str:
    value = text.rstrip()
    if not value:
        return value
    if value.endswith("...") or value.endswith("…"):
        return value
    return value + "..."


def _trim_to_units(text: str, max_units: float) -> str:
    value = text.rstrip()
    while value and visual_width(value + "...") > max_units:
        value = value[:-1].rstrip()
    return _append_ellipsis(value) if value else "..."


def wrap_text(
    text: str,
    max_width: float,
    font_size: float,
    max_lines: int = 3,
    ellipsis: bool = True,
) -> list[str]:
    text = " ".join(as_text(text).split())
    if not text:
        return []

    # SVG and PowerPoint do not share a text layout engine. Use a conservative
    # width estimate so CJK-heavy lines wrap before they touch card edges.
    max_units = max_width / max(font_size * 0.92, 1)
    lines: list[str] = []
    current = ""
    truncated = False
    for idx, char in enumerate(text):
        candidate = current + char
        if current and visual_width(candidate) > max_units:
            lines.append(current.rstrip())
            current = char.lstrip()
            if len(lines) >= max_lines:
                truncated = idx < len(text) - 1
                break
        else:
            current = candidate

    if len(lines) < max_lines and current:
        lines.append(current.rstrip())

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    if lines and ellipsis and truncated:
        lines[-1] = _trim_to_units(lines[-1], max_units)

    return lines


def fit_text_block(
    text: str,
    max_width: float,
    font_size: float,
    max_lines: int = 3,
    min_font_size: float | None = None,
    step: float = 1.0,
    ellipsis: bool = True,
) -> tuple[list[str], float]:
    base_size = max(float(font_size), 1.0)
    floor_size = float(min_font_size) if min_font_size is not None else max(10.0, base_size - 4.0)
    floor_size = min(base_size, max(6.0, floor_size))
    step = max(0.5, float(step))

    best_lines = wrap_text(text, max_width, base_size, max_lines=max_lines, ellipsis=ellipsis)
    if not best_lines:
        return best_lines, base_size

    # Preserve typographic hierarchy when the base size already fits.
    if not best_lines[-1].endswith(("...", "…")) and len(best_lines) <= max_lines:
        return best_lines, base_size

    size = base_size
    while size - step >= floor_size - 1e-6:
        size = round(size - step, 2)
        candidate = wrap_text(text, max_width, size, max_lines=max_lines, ellipsis=ellipsis)
        if not candidate:
            continue
        best_lines = candidate
        # Stop early once candidate no longer needs truncation.
        if not candidate[-1].endswith(("...", "…")):
            return candidate, size

    return best_lines, size


def clamp_count(items: list[Any], count: int) -> list[Any]:
    return items[:count] + [{} for _ in range(max(0, count - len(items)))]


