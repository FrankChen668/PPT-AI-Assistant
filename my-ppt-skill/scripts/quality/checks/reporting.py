"""Shared reporting helpers for quality and manifest metrics."""

from __future__ import annotations

from typing import Any


def extract_quality_tiers(
    metrics: dict[str, Any],
    *,
    fallback_errors: int = 0,
    fallback_warnings: int = 0,
) -> dict[str, int]:
    raw = metrics.get("quality_tiers")
    if isinstance(raw, dict):
        blocking = int(raw.get("blocking", fallback_errors))
        warning = int(raw.get("warning", fallback_warnings))
        advisory = int(raw.get("advisory", 0))
        return {"blocking": blocking, "warning": warning, "advisory": advisory}
    return {"blocking": int(fallback_errors), "warning": int(fallback_warnings), "advisory": 0}

