"""Fallback policy loader for export-stage degrade behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FallbackPolicy:
    version: str
    export_subprocess_timeout_sec: float | None
    fallback_on_locked_stable_target: bool
    max_locked_fallback_attempts: int


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def default_fallback_policy() -> FallbackPolicy:
    return FallbackPolicy(
        version="v1",
        export_subprocess_timeout_sec=None,
        fallback_on_locked_stable_target=True,
        max_locked_fallback_attempts=1,
    )


def load_fallback_policy(policy_path: Path) -> FallbackPolicy:
    if not policy_path.exists():
        return default_fallback_policy()
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception:
        return default_fallback_policy()
    if not isinstance(payload, dict):
        return default_fallback_policy()
    export_payload = payload.get("export")
    if not isinstance(export_payload, dict):
        export_payload = {}
    return FallbackPolicy(
        version=str(payload.get("version", "v1")).strip() or "v1",
        export_subprocess_timeout_sec=_safe_float(export_payload.get("subprocess_timeout_sec")),
        fallback_on_locked_stable_target=bool(export_payload.get("fallback_on_locked_stable_target", True)),
        max_locked_fallback_attempts=_safe_int(export_payload.get("max_locked_fallback_attempts"), 1),
    )
