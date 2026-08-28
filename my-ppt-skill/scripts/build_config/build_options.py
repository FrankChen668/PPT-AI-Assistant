"""Typed option models used by build pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseOptions:
    auto_copyfit: bool
    delivery_ready: bool
    enable_layout_lint: bool
    safe_area_profile: str
    deterministic_repair: bool
    used_legacy_repair_flag: bool

