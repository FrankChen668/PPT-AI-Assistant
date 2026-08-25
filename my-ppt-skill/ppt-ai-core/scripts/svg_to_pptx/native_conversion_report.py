"""Structured native SVG-to-PPTX conversion integrity reports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = 1
REPORT_FILENAME = "native-conversion-report.json"


def conversion_issue(
    *,
    slide_id: str,
    tag: str,
    element_id: str | None,
    error_type: str,
    message: str,
    hard_blocker: bool,
    code: str,
) -> dict[str, Any]:
    """Create one stable, JSON-safe conversion issue."""
    return {
        "slide_id": slide_id,
        "tag": tag,
        "element_id": element_id,
        "error_type": error_type,
        "message": " ".join(str(message).split())[:300],
        "hard_blocker": bool(hard_blocker),
        "code": code,
    }


def empty_slide_stats(slide_id: str, source_svg: str) -> dict[str, Any]:
    return {
        "slide_id": slide_id,
        "source_svg": source_svg,
        "visible_elements": 0,
        "converted_elements": 0,
        "conversion_errors": 0,
        "unsupported_elements": 0,
        "unsupported_tags": [],
        "source_text_nodes": 0,
        "converted_text_nodes": 0,
        "images_succeeded": 0,
        "images_failed": 0,
        "blank_slide": False,
        "critical_elements": 0,
        "converted_critical_elements": 0,
        "critical_text_nodes": 0,
        "converted_critical_text_nodes": 0,
        "critical_images": 0,
        "converted_critical_images": 0,
        "markers_converted": 0,
        "unsupported_markers": 0,
        "marker_events": [],
        "issues": [],
    }


def _append_once(issues: list[dict[str, Any]], issue: dict[str, Any]) -> None:
    signature = (
        issue.get("slide_id"),
        issue.get("element_id"),
        issue.get("error_type"),
        issue.get("code"),
    )
    if any(
        (
            existing.get("slide_id"),
            existing.get("element_id"),
            existing.get("error_type"),
            existing.get("code"),
        )
        == signature
        for existing in issues
    ):
        return
    issues.append(issue)


def finalize_slide_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Classify loss after all elements on one page have been attempted."""
    issues = stats.setdefault("issues", [])
    slide_id = str(stats.get("slide_id") or "")
    visible = int(stats.get("visible_elements") or 0)
    converted = int(stats.get("converted_elements") or 0)
    source_text = int(stats.get("source_text_nodes") or 0)
    converted_text = int(stats.get("converted_text_nodes") or 0)
    critical_text = int(stats.get("critical_text_nodes") or 0)
    converted_critical_text = int(stats.get("converted_critical_text_nodes") or 0)
    critical_elements = int(stats.get("critical_elements") or 0)
    converted_critical_elements = int(stats.get("converted_critical_elements") or 0)
    critical_images = int(stats.get("critical_images") or 0)
    converted_critical_images = int(stats.get("converted_critical_images") or 0)

    stats["unsupported_tags"] = sorted({str(tag) for tag in stats.get("unsupported_tags", []) if tag})
    stats["blank_slide"] = visible > 0 and converted == 0
    if stats["blank_slide"]:
        _append_once(
            issues,
            conversion_issue(
                slide_id=slide_id,
                tag="svg",
                element_id=None,
                error_type="empty-slide",
                message="Source SVG has visible content but the native PPTX page has no visible objects.",
                hard_blocker=True,
                code="empty-slide",
            ),
        )

    missing_elements = max(visible - converted, 0)
    if not stats["blank_slide"] and missing_elements >= 2 and missing_elements / visible >= 0.5:
        _append_once(
            issues,
            conversion_issue(
                slide_id=slide_id,
                tag="svg",
                element_id=None,
                error_type="large-content-loss",
                message=f"Native PPTX retained {converted} of {visible} visible SVG elements.",
                hard_blocker=True,
                code="native-content-loss",
            ),
        )

    missing_text = max(source_text - converted_text, 0)
    large_text_loss = source_text > 0 and (converted_text == 0 or missing_text / source_text >= 0.5)
    critical_text_loss = critical_text > converted_critical_text
    if large_text_loss or critical_text_loss:
        _append_once(
            issues,
            conversion_issue(
                slide_id=slide_id,
                tag="text",
                element_id=None,
                error_type="critical-text-loss" if critical_text_loss else "text-loss",
                message=(
                    f"Native PPTX retained {converted_text} of {source_text} SVG text nodes"
                    + (" and lost explicitly critical text." if critical_text_loss else ".")
                ),
                hard_blocker=True,
                code="native-content-loss",
            ),
        )

    critical_element_loss = critical_elements > converted_critical_elements
    critical_image_loss = critical_images > converted_critical_images
    if critical_element_loss or critical_image_loss:
        _append_once(
            issues,
            conversion_issue(
                slide_id=slide_id,
                tag="image" if critical_image_loss else "svg",
                element_id=None,
                error_type="critical-image-loss" if critical_image_loss else "critical-content-loss",
                message=(
                    f"Native PPTX retained {converted_critical_elements} of {critical_elements} critical elements; "
                    f"critical images {converted_critical_images} of {critical_images}."
                ),
                hard_blocker=True,
                code="native-content-loss",
            ),
        )
    return stats


def build_native_conversion_report(
    slides: list[dict[str, Any]],
    *,
    source_slide_count: int,
    pptx_slide_count: int,
) -> dict[str, Any]:
    finalized = [finalize_slide_stats(dict(slide)) for slide in slides]
    deck_issues = [issue for slide in finalized for issue in slide.get("issues", []) if isinstance(issue, dict)]
    page_count_match = int(source_slide_count) == int(pptx_slide_count)
    if not page_count_match:
        deck_issues.append(
            conversion_issue(
                slide_id="deck",
                tag="pptx",
                element_id=None,
                error_type="page-count-mismatch",
                message=f"SVG page count is {source_slide_count}, but PPTX page count is {pptx_slide_count}.",
                hard_blocker=True,
                code="native-conversion-failed",
            )
        )

    hard_blockers = [issue for issue in deck_issues if issue.get("hard_blocker") is True]
    quality_notes = [issue for issue in deck_issues if issue.get("hard_blocker") is not True]
    if hard_blockers:
        delivery_status = "blocked"
    elif quality_notes:
        delivery_status = "downloadable_with_notes"
    else:
        delivery_status = "approved"

    totals = {
        field: sum(int(slide.get(field) or 0) for slide in finalized)
        for field in (
            "visible_elements",
            "converted_elements",
            "conversion_errors",
            "unsupported_elements",
            "source_text_nodes",
            "converted_text_nodes",
            "images_succeeded",
            "images_failed",
            "critical_elements",
            "converted_critical_elements",
            "critical_text_nodes",
            "converted_critical_text_nodes",
            "critical_images",
            "converted_critical_images",
            "markers_converted",
            "unsupported_markers",
        )
    }
    summary = {
        "source_slide_count": int(source_slide_count),
        "pptx_slide_count": int(pptx_slide_count),
        "page_count_match": page_count_match,
        **totals,
        "unsupported_tags": sorted(
            {str(tag) for slide in finalized for tag in slide.get("unsupported_tags", []) if tag}
        ),
        "blank_slides": sum(1 for slide in finalized if slide.get("blank_slide") is True),
        "hard_blocker_count": len(hard_blockers),
        "quality_note_count": len(quality_notes),
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "delivery_status": delivery_status,
        "delivery_approved": not hard_blockers,
        "manual_review_required": bool(quality_notes),
        "summary": summary,
        "slides": finalized,
        "hard_blockers": hard_blockers,
        "quality_notes": quality_notes,
    }


def write_native_conversion_report(path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def read_native_conversion_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
        raise ValueError(f"Invalid native conversion report: {path}")
    return payload
