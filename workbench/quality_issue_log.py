from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_FILENAME = "quality-issues.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_text(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text if text else fallback


def _safe_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _read_report(project_dir: Path) -> dict[str, Any]:
    report_path = project_dir / "qa" / "report.json"
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _issue_from_finding(item: Any, *, fallback_slide_id: int | None = None) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    code = _safe_text(item.get("code") or item.get("id") or item.get("rule"))
    if not code:
        return None
    issue: dict[str, Any] = {
        "code": code,
        "severity": _safe_text(item.get("severity"), fallback="unknown"),
    }
    slide_id = _safe_int(item.get("slide_id")) or fallback_slide_id
    if slide_id:
        issue["slide_id"] = slide_id
    return issue


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for issue in issues:
        key = (issue.get("code"), issue.get("severity"), issue.get("slide_id"), issue.get("source"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _report_findings(project_dir: Path, *, slide_id: int | None = None) -> list[dict[str, Any]]:
    report = _read_report(project_dir)
    raw_findings = report.get("findings")
    if not isinstance(raw_findings, list):
        return []
    issues: list[dict[str, Any]] = []
    for item in raw_findings:
        issue = _issue_from_finding(item, fallback_slide_id=slide_id)
        if issue is None:
            continue
        if slide_id and issue.get("slide_id") not in {None, slide_id}:
            continue
        issue["source"] = "qa_report"
        issues.append(issue)
    return _dedupe_issues(issues)


def _code_issues(codes: Any, *, source: str, slide_id: int | None = None) -> list[dict[str, Any]]:
    if not isinstance(codes, list):
        return []
    issues: list[dict[str, Any]] = []
    for code in codes:
        text = _safe_text(code)
        if not text:
            continue
        issue: dict[str, Any] = {"code": text, "severity": "blocker", "source": source}
        if slide_id:
            issue["slide_id"] = slide_id
        issues.append(issue)
    return _dedupe_issues(issues)


def _layout_issues(findings: Any, *, slide_id: int | None = None) -> list[dict[str, Any]]:
    if not isinstance(findings, list):
        return []
    issues: list[dict[str, Any]] = []
    for item in findings:
        issue = _issue_from_finding(item, fallback_slide_id=slide_id)
        if issue is None:
            issue = {"code": "layout_regeneration_needed", "severity": "blocker"}
            if slide_id:
                issue["slide_id"] = slide_id
        issue["source"] = "layout_gate"
        issues.append(issue)
    return _dedupe_issues(issues)


def build_slide_qa_issue_record(
    project_dir: Path,
    *,
    project_name: str,
    slide_id: int,
    qa_ok: bool,
    reason_code: str,
    quality: dict[str, Any],
    quality_blockers: list[str],
    layout_blockers: list[Any],
) -> dict[str, Any]:
    issues = _report_findings(project_dir, slide_id=slide_id)
    issues.extend(_code_issues(quality_blockers, source="quality_gate", slide_id=slide_id))
    issues.extend(_layout_issues(layout_blockers, slide_id=slide_id))
    issues = _dedupe_issues(issues)
    return {
        "version": 1,
        "source": "slide_qa",
        "project": project_name,
        "slide_id": slide_id,
        "qa_ok": bool(qa_ok),
        "reason_code": _safe_text(reason_code),
        "quality_status": _safe_text(quality.get("status") or quality.get("user_quality_status")),
        "manual_review_required": bool(quality.get("manual_review_required")),
        "delivery_blocked": bool(quality.get("delivery_blocked")),
        "issue_count": len(issues),
        "issues": issues[:50],
    }


def build_deck_finalize_issue_record(
    project_dir: Path,
    *,
    project_name: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    user_quality = data.get("user_quality") if isinstance(data.get("user_quality"), dict) else {}
    issues = _report_findings(project_dir)
    issues.extend(_code_issues(user_quality.get("hard_blocker_codes"), source="quality_gate"))
    issues.extend(_layout_issues(data.get("preflight_blockers")))
    issues = _dedupe_issues(issues)
    return {
        "version": 1,
        "source": "deck_finalize",
        "project": project_name,
        "finalize_status": _safe_text(data.get("finalize_status")),
        "reason_code": "export_failed" if data.get("finalize_status") == "failed" else "",
        "returncode": data.get("returncode"),
        "manual_review_required": bool(data.get("manual_review_required")),
        "delivery_blocked": bool(data.get("delivery_blocked")),
        "expected_slide_count": data.get("expected_slide_count"),
        "exported_slide_count": data.get("exported_slide_count"),
        "issue_count": len(issues),
        "issues": issues[:100],
    }


def append_quality_issue_record(project_dir: Path, record: dict[str, Any], *, now: str | None = None) -> bool:
    issue_count = int(record.get("issue_count") or 0)
    has_problem_status = bool(
        record.get("delivery_blocked")
        or record.get("manual_review_required")
        or record.get("finalize_status") == "failed"
        or record.get("qa_ok") is False
    )
    if issue_count <= 0 and not has_problem_status:
        return False
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    output = qa_dir / LOG_FILENAME
    payload = {"recorded_at": now or _utc_now(), **record}
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return True
