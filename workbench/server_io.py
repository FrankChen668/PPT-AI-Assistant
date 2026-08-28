from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IoWarning:
    code: str
    message: str
    context: dict[str, Any]


def _to_relative_path(target: Path, absolute_or_relative: Path) -> str:
    candidate = absolute_or_relative
    if candidate.is_absolute():
        try:
            return str(candidate.relative_to(target)).replace("\\", "/")
        except ValueError:
            return str(candidate).replace("\\", "/")
    return str(candidate).replace("\\", "/")


def _read_json(path: Path) -> tuple[Any | None, IoWarning | None]:
    if not path.exists():
        return None, IoWarning(
            "missing-file",
            f"Expected JSON file not found: {path.name}",
            {"path": str(path)},
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, IoWarning(
            "invalid-json",
            f"Could not parse JSON: {exc}",
            {"path": str(path)},
        )
    except OSError as exc:
        return None, IoWarning(
            "read-failed",
            f"Could not read file: {exc}",
            {"path": str(path)},
        )
    return payload, None


def _warning_to_dict(warning: IoWarning) -> dict[str, Any]:
    return {"code": warning.code, "message": warning.message, "context": warning.context}


def read_json_object(path: Path, *, encoding: str = "utf-8-sig") -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path.exists():
        warning = IoWarning(
            "missing-file",
            f"Expected JSON file not found: {path.name}",
            {"path": str(path)},
        )
        return None, _warning_to_dict(warning)
    try:
        payload = json.loads(path.read_text(encoding=encoding))
    except json.JSONDecodeError as exc:
        warning = IoWarning(
            "invalid-json",
            f"Could not parse JSON: {exc}",
            {"path": str(path)},
        )
        return None, _warning_to_dict(warning)
    except OSError as exc:
        warning = IoWarning(
            "read-failed",
            f"Could not read file: {exc}",
            {"path": str(path)},
        )
        return None, _warning_to_dict(warning)
    if not isinstance(payload, dict):
        warning = IoWarning(
            "schema-mismatch",
            "JSON root must be an object.",
            {"path": str(path)},
        )
        return None, _warning_to_dict(warning)
    return payload, None


def _read_manifest_records(target: Path) -> tuple[list[Any], str, list[dict[str, Any]]]:
    manifest = target / "exports" / "manifest.json"
    if not manifest.exists():
        return [], "", []
    payload, warning = _read_json(manifest)
    warnings: list[dict[str, Any]] = []
    if warning:
        warnings.append({"code": warning.code, "message": warning.message, "context": warning.context})
        return [], "exports/manifest.json", warnings
    if not isinstance(payload, dict):
        warnings.append(
            {
                "code": "schema-mismatch",
                "message": "manifest.json root must be a JSON object.",
                "context": {"path": "exports/manifest.json"},
            }
        )
        return [], "exports/manifest.json", warnings
    records = payload.get("records")
    if not isinstance(records, list):
        warnings.append(
            {
                "code": "schema-mismatch",
                "message": "manifest.json must contain records list.",
                "context": {"path": "exports/manifest.json"},
            }
        )
        return [], "exports/manifest.json", warnings
    if not records:
        warnings.append(
            {
                "code": "empty-records",
                "message": "manifest.json records list is empty.",
                "context": {"path": "exports/manifest.json"},
            }
        )
        return [], "exports/manifest.json", warnings
    return records, "exports/manifest.json", warnings


def read_latest_manifest_record(target: Path) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    records, manifest_path, warnings = _read_manifest_records(target)
    if not records:
        return {}, manifest_path, warnings
    record = records[-1]
    if not isinstance(record, dict):
        warnings.append(
            {
                "code": "schema-mismatch",
                "message": "manifest.json last record must be an object.",
                "context": {"path": "exports/manifest.json"},
            }
        )
        return {}, manifest_path, warnings
    return record, manifest_path, warnings


def read_latest_finalize_manifest_record(target: Path) -> tuple[dict[str, Any], str, list[dict[str, Any]]]:
    """Return the newest finalize record, treating phase-less legacy records as finalize."""
    records, manifest_path, warnings = _read_manifest_records(target)
    for record in reversed(records):
        if not isinstance(record, dict):
            continue
        phase = str(record.get("phase") or "")
        if phase in {"", "finalize"}:
            return record, manifest_path, warnings
    return {}, manifest_path, warnings


def read_qa_report_summary(target: Path) -> dict[str, Any]:
    report_json = target / "qa" / "report.json"
    report_md = target / "qa" / "report.md"
    summary: dict[str, Any] = {
        "last_qa_report_path": "qa/report.json" if report_json.exists() else ("qa/report.md" if report_md.exists() else ""),
        "last_contact_sheet_path": "",
        "manual_review_required": None,
        "delivery_blocked": None,
        "visual_score": "not_scored",
        "visual_score_status": "missing",
        "visual_score_reason": "qa/report.json is missing.",
        "qa_scope": "unknown",
        "checked_slide": None,
        "io_warnings": [],
    }
    if not report_json.exists():
        contact_sheet = target / "qa" / "contact-sheet.png"
        if contact_sheet.exists():
            summary["last_contact_sheet_path"] = "qa/contact-sheet.png"
        return summary

    payload, warning = _read_json(report_json)
    if warning:
        summary["io_warnings"].append(
            {"code": warning.code, "message": warning.message, "context": {"path": "qa/report.json"}}
        )
        return summary
    if not isinstance(payload, dict):
        summary["io_warnings"].append(
            {
                "code": "schema-mismatch",
                "message": "qa/report.json root must be a JSON object.",
                "context": {"path": "qa/report.json"},
            }
        )
        return summary
    summary["visual_score_reason"] = "qa/report.json does not include visual_score."

    layered = payload.get("layered_verdict")
    if isinstance(layered, dict):
        manual_review = layered.get("manual_review_required")
        delivery_blocked = layered.get("delivery_blocked")
        if isinstance(manual_review, bool):
            summary["manual_review_required"] = manual_review
        if isinstance(delivery_blocked, bool):
            summary["delivery_blocked"] = delivery_blocked
    if summary["manual_review_required"] is None and isinstance(payload.get("manual_review_required"), bool):
        summary["manual_review_required"] = bool(payload.get("manual_review_required"))

    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        checked_slide = metrics.get("checked_slide")
        if checked_slide == "all":
            summary["qa_scope"] = "deck"
            summary["checked_slide"] = "all"
        elif isinstance(checked_slide, int) and checked_slide > 0:
            summary["qa_scope"] = "slide"
            summary["checked_slide"] = checked_slide
        elif isinstance(checked_slide, str) and checked_slide.strip().isdigit() and int(checked_slide.strip()) > 0:
            summary["qa_scope"] = "slide"
            summary["checked_slide"] = int(checked_slide.strip())
        raw_visual_score = payload.get("visual_score")
        if not isinstance(raw_visual_score, (int, float)):
            raw_visual_score = metrics.get("visual_score")
        if isinstance(raw_visual_score, (int, float)):
            summary["visual_score"] = round(float(raw_visual_score), 2)
            summary["visual_score_status"] = "scored"
            summary["visual_score_reason"] = ""
        contact = metrics.get("contact_sheet")
        if isinstance(contact, str) and contact.strip():
            contact_path = Path(contact.strip())
            summary["last_contact_sheet_path"] = _to_relative_path(target, contact_path)
    else:
        summary["io_warnings"].append(
            {
                "code": "schema-mismatch",
                "message": "qa/report.json metrics field is missing or not an object.",
                "context": {"path": "qa/report.json"},
            }
        )

    if not summary["last_contact_sheet_path"]:
        fallback = target / "qa" / "contact-sheet.png"
        if fallback.exists():
            summary["last_contact_sheet_path"] = "qa/contact-sheet.png"
    return summary
