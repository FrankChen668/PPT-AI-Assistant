from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from workbench.quality_policy import evaluate_user_quality
from workbench.server_io import (
    read_latest_finalize_manifest_record,
    read_qa_report_summary,
)


ExportedPptxResolver = Callable[[Path], Path | None]


def _latest_slide_source_mtime(target: Path) -> float:
    latest = 0.0
    for folder in ("svg_output", "svg_final"):
        source_dir = target / folder
        if not source_dir.exists():
            continue
        for svg in source_dir.glob("slide_*.svg"):
            try:
                latest = max(latest, svg.stat().st_mtime)
            except OSError:
                continue
    return latest


def _candidate_export_paths(target: Path, record: dict[str, Any]) -> list[Path]:
    candidates: list[Path] = []
    output_files = record.get("output_files")
    if isinstance(output_files, list):
        for rel in output_files:
            if not isinstance(rel, str) or not rel.lower().endswith(".pptx"):
                continue
            candidate = (target / rel.replace("\\", "/")).resolve()
            if candidate.exists() and candidate.is_file() and candidate not in candidates:
                candidates.append(candidate)
    stable = (target / "exports" / "output-native.pptx").resolve()
    if stable.exists() and stable.is_file() and stable not in candidates:
        candidates.append(stable)
    return candidates


def resolve_latest_exported_pptx(target: Path, *, require_current: bool = False) -> Path | None:
    record, _, _warnings = read_latest_finalize_manifest_record(target)
    candidates = _candidate_export_paths(target, record)
    if not candidates:
        return None

    latest_source_mtime = _latest_slide_source_mtime(target)
    filtered: list[Path] = []
    for candidate in candidates:
        try:
            if not require_current or candidate.stat().st_mtime >= latest_source_mtime:
                filtered.append(candidate)
        except OSError:
            continue
    if require_current:
        candidates = filtered
    elif filtered:
        candidates = filtered
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def export_relpath(target: Path, pptx_path: Path) -> str:
    try:
        return str(pptx_path.relative_to(target)).replace("\\", "/")
    except ValueError:
        return str(pptx_path).replace("\\", "/")


def _manifest_delivery_evidence(record: dict[str, Any]) -> tuple[bool | None, bool | None]:
    if record.get("delivery_approved") is True:
        return False, False
    delivery_status = str(record.get("delivery_status") or "")
    if delivery_status == "artifact_created_but_visual_review_required":
        return True, False
    if delivery_status:
        return False, True
    return None, None


def compute_finalize_evidence(target: Path, *, exported_pptx_resolver: ExportedPptxResolver) -> dict[str, Any]:
    record, manifest_path, manifest_warnings = read_latest_finalize_manifest_record(target)
    qa_summary = read_qa_report_summary(target)
    export_is_current = exported_pptx_resolver(target) is not None
    quality_mode = str(record.get("quality_mode") or "").strip().lower()
    qa_clean_finalize = (
        str(record.get("phase") or "") == "finalize"
        and record.get("artifact_created") is True
        and int(record.get("qa_errors") or 0) == 0
        and int(record.get("qa_warnings") or 0) == 0
    )
    if quality_mode in {"release-safe", "premium"}:
        last_finalize_mode = quality_mode
    elif (
        record.get("delivery_approved") is True
        or str(record.get("delivery_status") or "") == "approved"
        or qa_clean_finalize
    ):
        last_finalize_mode = "finalize"
    else:
        last_finalize_mode = "unknown"
    cache_hit_raw = record.get("incremental_cache_hit")
    if isinstance(cache_hit_raw, bool):
        last_finalize_cache_hit: bool | str = cache_hit_raw
    else:
        last_finalize_cache_hit = "unknown"
    if last_finalize_mode == "unknown":
        last_finalize_fresh_qa: bool | str = "unknown"
    elif isinstance(last_finalize_cache_hit, bool):
        last_finalize_fresh_qa = not last_finalize_cache_hit
    else:
        incremental_mode = record.get("incremental_mode")
        last_finalize_fresh_qa = False if incremental_mode is True else ("unknown" if incremental_mode is None else True)
    if (
        last_finalize_mode == "unknown"
        and export_is_current
        and qa_summary["manual_review_required"] is False
        and qa_summary["delivery_blocked"] is False
    ):
        last_finalize_mode = "finalize"
        last_finalize_cache_hit = False
        last_finalize_fresh_qa = True
    qa_scope = str(qa_summary.get("qa_scope") or "unknown")
    checked_slide = qa_summary.get("checked_slide")
    if qa_scope == "slide":
        manual_review_required, delivery_blocked = _manifest_delivery_evidence(record)
    else:
        manual_review_required = qa_summary["manual_review_required"]
        delivery_blocked = qa_summary["delivery_blocked"]
    evidence = {
        "last_finalize_mode": last_finalize_mode,
        "last_finalize_fresh_qa": last_finalize_fresh_qa,
        "last_finalize_cache_hit": last_finalize_cache_hit,
        "last_manifest_path": manifest_path,
        "last_qa_report_path": qa_summary["last_qa_report_path"],
        "last_contact_sheet_path": qa_summary["last_contact_sheet_path"],
        "qa_scope": qa_scope,
        "checked_slide": checked_slide,
        "manual_review_required": manual_review_required,
        "delivery_blocked": delivery_blocked,
        "visual_score": qa_summary.get("visual_score", "not_scored"),
        "visual_score_status": qa_summary.get("visual_score_status", "missing"),
        "visual_score_reason": qa_summary.get("visual_score_reason", ""),
        "export_is_current": export_is_current,
        "evidence_warnings": manifest_warnings + list(qa_summary.get("io_warnings") or []),
    }
    evidence["user_quality"] = evaluate_user_quality(target, evidence)
    return evidence
