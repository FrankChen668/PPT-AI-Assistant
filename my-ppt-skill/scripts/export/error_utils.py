#!/usr/bin/env python3
"""Export-error classification and formatting utilities.

Extracted from build_project.py to reduce the shallow-monolith surface.
Contains pure (I/O-free) classification helpers for PPTX export failures.
"""

from __future__ import annotations

from pathlib import Path


def looks_like_locked_pptx_error(exc: BaseException) -> bool:
    """Check if an exception indicates a locked/opened PPTX file."""
    if isinstance(exc, PermissionError):
        return True
    message = str(exc)
    return any(token in message for token in ("PermissionError", "Permission denied", "Errno 13"))


def classify_export_error(exc: BaseException) -> str:
    """Map an export exception to a canonical error-code string."""
    lowered = str(exc).lower()
    if looks_like_locked_pptx_error(exc):
        return "locked_output_pptx"
    if "export_timeout" in lowered or "timed out" in lowered or "timeout" in lowered:
        return "export_timeout"
    if "missing core exporter" in lowered:
        return "missing_core_exporter"
    return "export_failed"


def fallback_action_hint(error_code: str) -> str:
    """Return a user-facing recovery hint for a given error code."""
    hints = {
        "locked_output_pptx": "close_pptx_or_use_semantic_artifact_name",
        "export_timeout": "retry_with_higher_timeout_or_reduce_slide_complexity",
        "missing_core_exporter": "restore_ppt_ai_core_exporter_entry",
    }
    return hints.get(error_code, "run_doctor_then_authoring_then_finalize")


def format_pptx_write_error(target: Path, exc: BaseException) -> str:
    """Format a user-friendly error message for PPTX write failures."""
    return (
        f"Could not write PPTX export: {target}\n"
        "目标 PPTX 文件可能被 PowerPoint/WPS 占用，导致无法覆盖。\n"
        "请关闭已打开的 PPTX 后重试，或改用 --artifact-name semantic 生成新版本文件。\n"
        f"Original error: {exc}"
    )
