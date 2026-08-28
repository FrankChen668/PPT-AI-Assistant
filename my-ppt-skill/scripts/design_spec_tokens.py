#!/usr/bin/env python3
"""Shared parsers for design_spec token lines."""

from __future__ import annotations

import json
import re

HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def split_design_spec_lines(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        values[key.strip()] = value.strip()
    return values


def normalize_hex_color(value: str) -> str | None:
    raw = value.strip()
    if not HEX_COLOR_RE.fullmatch(raw):
        return None
    token = raw.lower().lstrip("#")
    if len(token) == 3:
        token = "".join(ch * 2 for ch in token)
    return f"#{token}"


def parse_color_list(value: str | None) -> list[str]:
    if value is None:
        return []
    raw = value.strip()
    if not raw:
        return []

    if raw.startswith("[") and raw.endswith("]"):
        try:
            payload = json.loads(raw)
        except Exception:
            payload = None
        if isinstance(payload, list):
            parsed: list[str] = []
            for item in payload:
                if isinstance(item, str):
                    token = item.strip().strip('"').strip("'")
                    if token:
                        parsed.append(token)
            return parsed

    return [part.strip().strip('"').strip("'") for part in raw.split(",") if part.strip()]


def parse_data_palette(value: str | None) -> tuple[str, ...]:
    parsed: list[str] = []
    for token in parse_color_list(value):
        normalized = normalize_hex_color(token)
        if normalized:
            parsed.append(normalized)
    return tuple(parsed)
