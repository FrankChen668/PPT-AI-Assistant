from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime
from pathlib import Path


STATUS_FILE = "workbench_status.json"
SVG_OUTPUT_DIR = "svg_output"
REVISIONS_DIR = "revisions"

SLIDE_STATUSES = {
    "not_attempted",
    "queued",
    "running",
    "waiting_codex",
    "generating",
    "succeeded",
    "svg_ready",
    "failed",
    "blocked",
    "skipped",
    "waiting_cancelled",
    "qa_running",
    "qa_passed",
    "qa_failed",
    "regenerate_requested",
    "restored",
}

EXPORT_STATUSES = {"not_ready", "ready", "running", "exported", "review_required", "failed"}
PROJECT_STATUSES = {
    "missing",
    "project_created",
    "waiting_codex",
    "generating",
    "svg_partial",
    "svg_ready",
    "qa_running",
    "qa_passed",
    "qa_failed",
    "export_ready",
    "export_running",
    "exported",
    "export_review_required",
    "export_failed",
}

_STATUS_LOCKS_GUARD = threading.Lock()
_STATUS_LOCKS: dict[str, threading.RLock] = {}


def _status_lock(project_path: Path) -> threading.RLock:
    key = str(project_path.resolve())
    with _STATUS_LOCKS_GUARD:
        lock = _STATUS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _STATUS_LOCKS[key] = lock
        return lock


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slide_svg_relpath(slide_id: int) -> str:
    return f"{SVG_OUTPUT_DIR}/slide_{slide_id:02d}.svg"


def slide_svg_path(project_path: Path, slide_id: int) -> Path:
    return project_path / SVG_OUTPUT_DIR / f"slide_{slide_id:02d}.svg"


def _parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _latest_svg_mtime(svg_path: Path, final_svg_path: Path) -> datetime | None:
    candidates = [path for path in (svg_path, final_svg_path) if path.exists()]
    if not candidates:
        return None
    return datetime.fromtimestamp(max(path.stat().st_mtime for path in candidates)).astimezone()


def _is_export_placeholder_svg(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        return "workbench-export-placeholder" in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def load_status(project_path: Path) -> dict:
    with _status_lock(project_path):
        path = project_path / STATUS_FILE
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8-sig"))


def save_status(project_path: Path, status: dict, *, touch: bool = True) -> dict:
    with _status_lock(project_path):
        if touch:
            status["updated_at"] = now_iso()
        path = project_path / STATUS_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return status


def merge_slide_status(
    project_path: Path,
    fallback_status: dict,
    slide_id: int,
    slide_patch: dict,
    *,
    status_patch: dict | None = None,
    event_type: str = "",
    event_message: str = "",
    touch: bool = True,
) -> dict:
    with _status_lock(project_path):
        latest_status = load_status(project_path) or fallback_status
        latest_slides = latest_status.get("slides") if isinstance(latest_status.get("slides"), list) else []
        replaced = False
        for current in latest_slides:
            if isinstance(current, dict) and int(current.get("slide_id") or 0) == int(slide_id):
                current.update(slide_patch)
                replaced = True
                break
        if not replaced:
            latest_slides.append(dict(slide_patch))
        latest_status["slides"] = latest_slides
        if status_patch:
            latest_status.update(status_patch)
        if event_type:
            add_event(latest_status, event_type, event_message)
        return save_status(project_path, latest_status, touch=touch)


def add_event(status: dict, event_type: str, message: str) -> dict:
    events = status.setdefault("events", [])
    events.append({"time": now_iso(), "type": event_type, "message": message})
    del events[:-50]
    return status


def normalize_slide_status(project_path: Path, status: dict) -> dict:
    slides = status.get("slides", [])
    for slide in slides:
        slide_id = int(slide["slide_id"])
        svg_path = slide_svg_path(project_path, slide_id)
        final_svg_path = project_path / "svg_final" / f"slide_{slide_id:02d}.svg"
        slide["svg_path"] = slide_svg_relpath(slide_id)
        physical_svg_exists = any(
            path.exists() and not _is_export_placeholder_svg(path)
            for path in (svg_path, final_svg_path)
        )
        failure_completed_at = _parse_iso(slide.get("generation_completed_at"))
        latest_svg_mtime = _latest_svg_mtime(svg_path, final_svg_path)
        svg_written_after_failure = bool(
            physical_svg_exists
            and failure_completed_at
            and latest_svg_mtime
            and latest_svg_mtime > failure_completed_at
        )
        generation_failed = (
            str(slide.get("generation_phase") or "") == "failed"
            and slide.get("qa_status") != "passed"
            and not svg_written_after_failure
        )
        slide["has_svg"] = physical_svg_exists and not generation_failed
        revision_dir = project_path / REVISIONS_DIR / f"slide_{slide_id:02d}"
        slide["revision_count"] = len(sorted(revision_dir.glob("*.svg"))) if revision_dir.exists() else 0
        current = slide.get("status")
        if slide["has_svg"] and current in {"waiting_codex", "regenerate_requested"}:
            slide["status"] = "svg_ready"
        if slide["has_svg"] and current == "generating":
            slide["status"] = "svg_ready"
            slide["generation_phase"] = "completed"
            slide["generation_completed_at"] = slide.get("generation_completed_at") or now_iso()
            slide["current_block_label"] = ""
            slide["last_error"] = ""
            slide["last_error_code"] = ""
            slide["lock_updated_at"] = now_iso()
        if slide["has_svg"] and current == "failed" and svg_written_after_failure:
            slide["status"] = "svg_ready"
            slide["generation_phase"] = "completed"
            slide["generation_completed_at"] = now_iso()
            slide["last_error"] = ""
            slide["last_error_code"] = ""
        if not slide["has_svg"] and current in {"svg_ready", "qa_passed"}:
            slide["status"] = "waiting_codex"
        if slide.get("qa_status") == "passed":
            slide["status"] = "qa_passed"
            if slide["has_svg"] and str(slide.get("generation_phase") or "") in {"", "starting", "failed", "fallback_single_pass"}:
                slide["generation_phase"] = "completed"
                slide["generation_completed_at"] = slide.get("generation_completed_at") or now_iso()
                slide["current_block_label"] = ""
                slide["last_error"] = ""
                slide["lock_updated_at"] = now_iso()
        if slide.get("qa_status") == "failed":
            slide["status"] = "qa_failed"
    return status


def compute_project_status(status: dict, readiness: dict) -> str:
    export_state = status.get("export", {})
    export_status = export_state.get("status")
    if export_status == "running":
        return "export_running"
    if export_status == "exported":
        return "exported"
    if export_status == "review_required":
        return "export_review_required"
    if export_status == "failed":
        last_error = str(export_state.get("last_error") or "")
        stale_budget_failure = readiness.get("ready") and "Budget policy check failed" in last_error
        if not stale_budget_failure:
            return "export_failed"

    slides = status.get("slides", [])
    if not slides:
        return "project_created"
    if any(str(slide.get("status") or "") == "generating" for slide in slides):
        return "generating"
    if readiness.get("ready") and export_status != "failed":
        return "export_ready"

    has_svg_count = sum(1 for slide in slides if slide.get("has_svg"))
    total = len(slides)
    if has_svg_count == 0:
        return "waiting_codex"
    if has_svg_count < total:
        return "svg_partial"

    qa_statuses = [str(slide.get("qa_status", "")) for slide in slides]
    if any(item == "running" for item in qa_statuses):
        return "qa_running"
    if any(item in {"failed", "qa_failed"} for item in qa_statuses):
        return "qa_failed"
    if all(item == "passed" for item in qa_statuses):
        return "qa_passed"
    if readiness.get("ready"):
        return "export_ready"
    return "svg_ready"


def compute_export_readiness(project_path: Path, status: dict) -> dict:
    normalized = normalize_slide_status(project_path, status)
    slides = normalized.get("slides", [])
    missing_from_status = [int(slide["slide_id"]) for slide in slides if not slide.get("has_svg")]
    expected_ids: set[int] = set()
    blueprint_invalid = False
    blueprint_path = project_path / "blueprint.json"
    if blueprint_path.exists():
        try:
            blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
            raw_slides = blueprint.get("slides") if isinstance(blueprint, dict) else None
            if not isinstance(raw_slides, list):
                blueprint_invalid = True
            else:
                expected_ids = {idx for idx, _ in enumerate(raw_slides, start=1)}
        except (json.JSONDecodeError, OSError):
            blueprint_invalid = True
    status_ids = {
        int(slide.get("slide_id") or 0)
        for slide in slides
        if isinstance(slide, dict) and int(slide.get("slide_id") or 0) > 0
    }
    missing_status_entries = sorted(item for item in expected_ids if item not in status_ids)
    missing = sorted({*missing_from_status, *missing_status_entries})
    qa_failed = [int(slide["slide_id"]) for slide in slides if slide.get("qa_status") in {"failed", "qa_failed"}]
    reasons: list[str] = []
    warnings: list[str] = []
    has_expected_deck = bool(slides or expected_ids)
    has_generated_slide = any(bool(slide.get("has_svg")) for slide in slides)
    if not has_expected_deck:
        reasons.append("project has no slides")
    elif not has_generated_slide:
        reasons.append("project has no generated slides")
    if blueprint_invalid:
        reasons.append("blueprint.json is invalid")
    if missing:
        warnings.append("missing slides will use export placeholders: " + ", ".join(str(item) for item in missing))
    if qa_failed:
        warnings.append("qa failed slides remain exportable: " + ", ".join(str(item) for item in qa_failed))
    ready = not reasons
    return {
        "artifact_buildable": ready,
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "reasons": reasons,
        "warnings": warnings,
        "missing_slides": missing,
        "placeholder_slides": missing,
        "qa_failed_slides": qa_failed,
    }


def update_export_status(project_path: Path, status: dict, export_patch: dict) -> dict:
    current = status.setdefault("export", {})
    current.update(export_patch)
    return save_status(project_path, status)


def backup_slide_revision(project_path: Path, slide_id: int, reason: str) -> str:
    source = slide_svg_path(project_path, slide_id)
    if not source.exists():
        return ""
    revision_dir = project_path / REVISIONS_DIR / f"slide_{slide_id:02d}"
    revision_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason).strip("-") or "revision"
    target = revision_dir / f"{stamp}-{safe_reason}.svg"
    shutil.copy2(source, target)
    return str(target.relative_to(project_path)).replace("\\", "/")


def list_slide_revisions(project_path: Path, slide_id: int) -> list[dict]:
    revision_dir = project_path / REVISIONS_DIR / f"slide_{slide_id:02d}"
    if not revision_dir.exists():
        return []
    items = []
    for path in sorted(revision_dir.glob("*.svg"), reverse=True):
        stat = path.stat()
        items.append(
            {
                "name": path.name,
                "path": str(path.relative_to(project_path)).replace("\\", "/"),
                "size": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            }
        )
    return items


def restore_slide_revision(project_path: Path, slide_id: int, revision_name: str) -> str:
    revision_dir = (project_path / REVISIONS_DIR / f"slide_{slide_id:02d}").resolve()
    source = (revision_dir / revision_name).resolve()
    if revision_dir not in source.parents or source.suffix.lower() != ".svg" or not source.exists():
        raise ValueError("Revision not found.")
    backup_slide_revision(project_path, slide_id, "before-restore")
    target = slide_svg_path(project_path, slide_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return str(target.relative_to(project_path)).replace("\\", "/")
