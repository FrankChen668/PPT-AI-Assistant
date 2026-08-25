"""Shared warning/blocking classification helpers for QA flows.

This module intentionally keeps pure classification logic only.
"""

from __future__ import annotations

from typing import Protocol

QUALITY_MODES = ("dev-fast", "release-safe", "premium")

RELEASE_SAFE_NON_BLOCKING_WARNING_CODES = {
    "style-hard-token-color-limit",
    "style-hard-token-consecutive-homogeneous",
    "style-hard-token-conclusion-hierarchy-weak",
    "visual-contract-missing",
    "visual-contract-incomplete",
    "visual-contract-invalid-read-path",
    "visual-contract-invalid-density-budget",
    "visual-contract-invalid-anti-patterns",
    "visual-contract-scene-mismatch",
}

BUDGET_NON_BLOCKING_WARNING_CODES = {
    "slide-budget-high",
    "slide-budget-medium",
}

DESIGN_TOKEN_NON_BLOCKING_WARNING_CODES = {
    "design-token-invalid-color",
    "design-token-missing-core",
    "design-token-low-contrast",
    "design-token-font-scale",
}

ASSET_NON_BLOCKING_WARNING_CODES = {
    "theme-data-palette-missing",
    "icon-ref-missing",
    "chart-color-outside-palette",
}


class FindingLike(Protocol):
    severity: str
    code: str


def normalize_quality_mode(value: str | None) -> str:
    mode = (value or "dev-fast").strip().lower()
    if mode not in QUALITY_MODES:
        return "dev-fast"
    return mode


def is_warning_non_blocking(code: str, quality_mode: str) -> bool:
    mode = normalize_quality_mode(quality_mode)
    if code in BUDGET_NON_BLOCKING_WARNING_CODES:
        return True
    if code in DESIGN_TOKEN_NON_BLOCKING_WARNING_CODES:
        return True
    if code in ASSET_NON_BLOCKING_WARNING_CODES:
        return True
    if mode == "release-safe" and code in RELEASE_SAFE_NON_BLOCKING_WARNING_CODES:
        return True
    return False


def is_visual_delivery_code(code: str) -> bool:
    return code.startswith("visual-") or code.startswith("style-") or code.startswith("prompt-pattern-")


def is_delivery_blocking_finding(finding: FindingLike, quality_mode: str, strict_effective: bool) -> bool:
    if finding.severity == "error":
        return True
    if finding.severity != "warning":
        return False
    if not strict_effective:
        return False
    return not is_warning_non_blocking(finding.code, quality_mode)

