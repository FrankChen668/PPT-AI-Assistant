#!/usr/bin/env python3
"""Pure helpers for slide text budget governance."""

from __future__ import annotations

from typing import Any

from profile_policy import resolve_profile_policy

RISK_LEVELS = ("none", "low", "medium", "high")
OVERFLOW_ACTIONS = {
    "none": "keep_current_layout",
    "low": "review_density",
    "medium": "reduce_secondary_copy",
    "high": "split_or_reduce_secondary_copy",
}


def _iter_text_values(node: Any):
    if isinstance(node, str):
        value = node.strip()
        if value:
            yield value
        return
    if isinstance(node, dict):
        for value in node.values():
            yield from _iter_text_values(value)
        return
    if isinstance(node, list):
        for value in node:
            yield from _iter_text_values(value)


def estimate_slide_text_load(slide: dict[str, Any]) -> dict[str, int]:
    display_slide = {key: value for key, value in slide.items() if key != "prompt"}
    text_values = list(_iter_text_values(display_slide))
    actual_chars = sum(len(value) for value in text_values)
    actual_text_nodes = len(text_values)
    return {
        "actual_chars": int(actual_chars),
        "actual_text_nodes": int(actual_text_nodes),
    }


def classify_budget_risk(actual_chars: int, actual_nodes: int, profile: str) -> str:
    policy = resolve_profile_policy(profile)
    chars = max(0, int(actual_chars))
    nodes = max(0, int(actual_nodes))
    char_ratio = chars / float(policy.max_chars_per_slide) if policy.max_chars_per_slide > 0 else 0.0
    node_ratio = nodes / float(policy.max_text_nodes_per_slide) if policy.max_text_nodes_per_slide > 0 else 0.0
    ratio = max(char_ratio, node_ratio)

    if ratio >= policy.overflow_risk_high_ratio:
        return "high"
    if ratio >= policy.overflow_risk_medium_ratio:
        return "medium"
    if ratio >= policy.overflow_risk_low_ratio:
        return "low"
    return "none"


def overflow_action_for_risk(risk: str) -> str:
    return OVERFLOW_ACTIONS.get((risk or "").strip().lower(), "review_density")


def build_slide_budget(slide: dict[str, Any], profile: str) -> dict[str, Any]:
    policy = resolve_profile_policy(profile)
    load = estimate_slide_text_load(slide)
    risk = classify_budget_risk(load["actual_chars"], load["actual_text_nodes"], policy.key)
    return {
        "profile": policy.key,
        "max_chars": int(policy.max_chars_per_slide),
        "max_text_nodes": int(policy.max_text_nodes_per_slide),
        "actual_chars": int(load["actual_chars"]),
        "actual_text_nodes": int(load["actual_text_nodes"]),
        "risk": risk,
        "overflow_action": overflow_action_for_risk(risk),
    }
