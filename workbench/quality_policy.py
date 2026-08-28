from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


HARD_BLOCKER_CODES = {
    "invalid-svg",
    "invalid-pptx",
    "missing-svg",
    "missing-pptx",
    "empty-slide",
    "text-outside-canvas",
    "overflow-risk-high",
    "svg-contrast-illegible",
    "critical-content-missing",
    "native-content-loss",
    "native-conversion-failed",
    "planning-missing-conclusion",
    "planning-empty-page",
    "planning-title-content-unrelated",
    "planning-invalid-comparison",
    "planning-invalid-process",
    "planning-invalid-roadmap",
    "planning-invalid-architecture",
    "planning-content-overload",
    "planning-slide-count-mismatch",
}

HARD_BLOCKER_PREFIXES = (
    "svg-parse",
    "invalid-svg",
    "invalid-pptx",
    "export-failed",
    "encoding-",
    "contract-svg-",
    "native-content-loss-",
    "native-conversion-failed-",
)

# These findings represent obvious visual quality failures in workbench mode.
VISUAL_BLOCKER_CODES = {
    "visual-hierarchy-flat",
    "visual-baseline-below-b",
    "visual-text-fragmented",
    "visual-alignment-chaos",
    "layout-quality-section-balance-cards",
    "layout-quality-section-balance-vertical",
}

VISUAL_BLOCKER_PREFIXES = (
    "visual-fail-",
    "layout-quality-fail-",
)

NOTE_CODES = {
    "text-near-safe-edge-whitelist",
    "overflow-risk-medium",
    "overflow-risk-low",
}

NOTE_PREFIXES = (
    "slide-budget-",
    "token-budget-",
    "style-",
)

TEXT_LAYOUT_FINDING_CODES = {
    "overflow-risk-low",
    "overflow-risk-medium",
    "overflow-risk-high",
    "text-outside-canvas",
    "text-overflow",
    "text-overlap",
    "text-overlap-risk",
}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _findings_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    items = report.get("findings")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _findings_from_native_conversion_report(project_dir: Path) -> list[dict[str, Any]]:
    report = _read_json(project_dir / "exports" / "native-conversion-report.json")
    findings: list[dict[str, Any]] = []
    for key in ("hard_blockers", "quality_notes"):
        items = report.get(key)
        if isinstance(items, list):
            findings.extend(item for item in items if isinstance(item, dict))
    return findings


def _planning_quality(project_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    report = _read_json(project_dir / "qa" / "planning-report.json")
    findings: list[dict[str, Any]] = []
    for key in ("hard_blockers", "quality_notes"):
        items = report.get(key)
        if isinstance(items, list):
            findings.extend(item for item in items if isinstance(item, dict))
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    planning = {
        "status": str(report.get("planning_status") or "not_checked"),
        "slide_count": int(summary.get("slide_count") or 0),
        "planned_slide_count": int(summary.get("planned_slide_count") or 0),
        "slide_type_distribution": dict(summary.get("slide_type_distribution") or {}),
        "visual_archetype_distribution": dict(summary.get("visual_archetype_distribution") or {}),
        "planning_error_count": int(summary.get("planning_error_count") or 0),
        "planning_warning_count": int(summary.get("planning_warning_count") or 0),
        "planning_note_count": int(summary.get("planning_note_count") or 0),
        "content_overload_slide_count": int(summary.get("content_overload_slide_count") or 0),
        "repeated_title_count": int(summary.get("repeated_title_count") or 0),
        "repeated_conclusion_count": int(summary.get("repeated_conclusion_count") or 0),
        "manual_review_required": report.get("manual_review_required") is True,
        "delivery_approved": report.get("delivery_approved") is True if report else None,
        "report": "qa/planning-report.json" if report else "",
    }
    return findings, planning


def _count_low_opacity(svg_text: str) -> int:
    count = 0
    for match in re.finditer(r"\b(?:opacity|fill-opacity|stroke-opacity)\s*=\s*['\"]([0-9]*\.?[0-9]+)['\"]", svg_text):
        try:
            value = float(match.group(1))
        except Exception:
            continue
        if value < 0.65:
            count += 1
    return count


def _collect_visual_effect_advisories(project_dir: Path) -> list[dict[str, Any]]:
    status = _read_json(project_dir / "workbench_status.json")
    slides = status.get("slides")
    if not isinstance(slides, list):
        return []

    advisories: list[dict[str, Any]] = []
    monitored_types = {"content", "toc", "outline"}
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        page_type = str(slide.get("page_type") or "content").strip().lower()
        if page_type not in monitored_types:
            continue

        slide_id = int(slide.get("slide_id") or 0)
        svg_rel = str(slide.get("svg_path") or f"svg_output/slide_{slide_id:02d}.svg")
        svg_path = project_dir / svg_rel
        if not svg_path.exists():
            continue

        svg = svg_path.read_text(encoding="utf-8", errors="replace")
        gradient_count = svg.lower().count("<lineargradient") + svg.lower().count("<radialgradient")
        filter_count = svg.lower().count("<filter")
        low_opacity_count = _count_low_opacity(svg)

        # Content-like pages should emphasize readability over effect stacking.
        effect_score = (gradient_count * 2) + (filter_count * 2) + low_opacity_count
        if effect_score < 8:
            continue

        advisories.append(
            {
                "severity": "advisory",
                "code": "visual-effects-heavy-content",
                "message": "Visual effects are dense for a content-style page; consider reducing effect stacking.",
                "context": {
                    "slide_id": slide_id,
                    "page_type": page_type,
                    "gradient_count": gradient_count,
                    "filter_count": filter_count,
                    "low_opacity_count": low_opacity_count,
                    "effect_score": effect_score,
                },
            }
        )
    return advisories


def is_hard_blocker_code(code: str) -> bool:
    normalized = str(code or "").strip()
    if normalized in HARD_BLOCKER_CODES:
        return True
    return any(normalized.startswith(prefix) for prefix in HARD_BLOCKER_PREFIXES)


def is_note_code(code: str) -> bool:
    normalized = str(code or "").strip()
    if normalized in NOTE_CODES:
        return True
    return any(normalized.startswith(prefix) for prefix in NOTE_PREFIXES)


def is_visual_blocker_code(code: str) -> bool:
    normalized = str(code or "").strip()
    if normalized in VISUAL_BLOCKER_CODES:
        return True
    return any(normalized.startswith(prefix) for prefix in VISUAL_BLOCKER_PREFIXES)


def _finding_context_requires_blocking(item: dict[str, Any]) -> bool:
    context = item.get("context") if isinstance(item.get("context"), dict) else {}
    if item.get("is_blocking") is True or context.get("is_blocking") is True:
        return True
    if item.get("critical") is True or context.get("critical") is True:
        return True

    risk_level = str(context.get("risk_level") or item.get("risk_level") or "").strip().lower()
    if risk_level in {"high", "severe", "critical"}:
        return True

    role_values: list[object] = []
    for key in ("content_role", "affected_role", "text_role", "left_role", "right_role", "affected_roles"):
        value = context.get(key, item.get(key))
        if isinstance(value, list):
            role_values.extend(value)
        elif value is not None:
            role_values.append(value)
    important_roles = {"title", "headline", "core", "conclusion", "key_conclusion", "takeaway", "critical"}
    return any(str(value).strip().lower() in important_roles for value in role_values)


def classify_quality_finding(item: dict[str, Any]) -> str:
    code = str(item.get("code") or "").strip()
    severity = str(item.get("severity") or "").strip().lower()
    if item.get("hard_blocker") is True or item.get("is_blocking") is True:
        return "hard_blocker"
    if code in {"overflow-risk-low", "overflow-risk-medium"}:
        return "quality_note"
    if code in {"text-overlap", "text-overlap-risk", "text-overflow"}:
        if severity in {"error", "critical", "fatal"} or _finding_context_requires_blocking(item):
            return "hard_blocker"
        return "quality_note"
    if is_hard_blocker_code(code):
        return "hard_blocker"
    return "quality_note"


def finding_requires_regeneration(item: dict[str, Any]) -> bool:
    code = str(item.get("code") or "").strip()
    return code in TEXT_LAYOUT_FINDING_CODES and classify_quality_finding(item) == "hard_blocker"


def _classify_findings(findings: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hard: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for item in findings:
        if classify_quality_finding(item) == "hard_blocker":
            hard.append(item)
        else:
            notes.append(item)
    return hard, notes


def evaluate_user_quality(project_dir: Path, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = evidence or {}
    report = _read_json(project_dir / "qa" / "report.json")
    findings = [] if evidence.get("qa_scope") == "slide" else _findings_from_report(report)
    findings.extend(_findings_from_native_conversion_report(project_dir))
    planning_findings, planning = _planning_quality(project_dir)
    if evidence.get("qa_scope") != "slide":
        findings.extend(planning_findings)
    hard, notes = _classify_findings(findings)
    notes.extend(_collect_visual_effect_advisories(project_dir))
    delivery_evidence_missing = bool(
        evidence.get("export_is_current") is False
        and evidence.get("last_finalize_fresh_qa") is not True
        and evidence.get("manual_review_required") is None
        and evidence.get("delivery_blocked") is None
    )

    if delivery_evidence_missing:
        hard.append(
            {
                "severity": "error",
                "code": "delivery-not-ready",
                "message": "PPT delivery artifact is not ready.",
            }
        )
        status = "blocked"
    elif hard:
        status = "blocked"
    elif notes:
        status = "usable_with_notes"
    else:
        status = "approved"

    can_download = status in {"approved", "usable_with_notes"}
    can_preview = status in {"approved", "usable_with_notes"}
    should_auto_repair = status == "blocked"
    summary = "可下载"
    if status == "approved" and notes:
        summary = "可下载，有优化建议"
    elif status == "usable_with_notes":
        summary = "可下载，但有优化建议"
    elif status == "blocked":
        summary = "存在阻断问题，需要继续自动优化"

    should_auto_repair = status == "blocked" and not delivery_evidence_missing
    if status == "approved":
        summary = "可下载，但有优化建议" if notes else "可下载"
    elif status == "usable_with_notes":
        summary = "已生成预览文件，但仍需视觉复核，暂时不能作为最终交付。"
    elif delivery_evidence_missing:
        summary = "还没有生成可交付 PPT。请先完成页面生成和 PPT 文件生成。"
    else:
        summary = "存在阻断问题，需要继续修复后再交付。"

    return {
        "user_quality_status": status,
        "can_download": can_download,
        "can_preview": can_preview,
        "should_auto_repair": should_auto_repair,
        "summary": summary,
        "visual_score": evidence.get("visual_score", "not_scored"),
        "visual_score_status": evidence.get("visual_score_status", "missing"),
        "visual_score_reason": evidence.get("visual_score_reason", ""),
        "hard_blocker_count": len(hard),
        "note_count": len(notes),
        "hard_blocker_codes": [str(item.get("code") or "") for item in hard],
        "note_codes": [str(item.get("code") or "") for item in notes],
        "hard_blockers": hard,
        "quality_notes": notes,
        "planning": planning,
    }
