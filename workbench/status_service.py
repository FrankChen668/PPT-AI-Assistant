from __future__ import annotations

from typing import Any

from workbench.generation import load_generation_config
from workbench.state import compute_project_status


EXPORT_PPTX_REL_PATH = "exports/output-native.pptx"
WORKFLOW_LABELS = {
    "single_page": "\u9010\u9875\u751f\u6210 PPT",
    "prompt_deck": "\u9010\u9875\u751f\u6210 PPT",
    "document_deck": "\u9010\u9875\u751f\u6210 PPT\uff08\u6587\u6863\u8f93\u5165\uff09",
    "optimize_existing": "\u7ee7\u7eed\u5904\u7406\u5df2\u6709\u9879\u76ee",
    "repair_existing": "\u7ee7\u7eed\u5904\u7406\u5df2\u6709\u9879\u76ee",
}


def normalize_workflow_mode(value: object, deck_type: str = "multi") -> str:
    mode = str(value or "").strip()
    if mode in WORKFLOW_LABELS:
        return mode
    return "single_page" if deck_type == "single" else "prompt_deck"


def workflow_label(mode: str) -> str:
    return WORKFLOW_LABELS.get(mode, "\u9010\u9875\u751f\u6210 PPT")


def resolve_workflow_fields(status: dict[str, Any]) -> tuple[str, str]:
    workflow_mode = normalize_workflow_mode(status.get("workflow_mode"), str(status.get("deck_type") or "multi"))
    workflow_label_value = str(status.get("workflow_label") or workflow_label(workflow_mode))
    return workflow_mode, workflow_label_value


def generation_metadata_for_status(status: dict[str, Any]) -> dict[str, Any]:
    config_error = ""
    try:
        configured = load_generation_config().public_metadata()
        provider_config_valid = True
    except ValueError as exc:
        config_error = str(exc)
        configured = {
            "provider": "",
            "model": "",
            "api_key_configured": False,
        }
        provider_config_valid = False
    recorded = status.get("generation") if isinstance(status.get("generation"), dict) else {}
    metadata = dict(configured)
    recorded_provider = str(recorded.get("provider") or "").strip()
    recorded_model = str(recorded.get("model") or "").strip()
    if recorded_provider:
        metadata["provider"] = recorded_provider
    if recorded_model:
        metadata["model"] = recorded_model
    metadata["provider_config_valid"] = provider_config_valid
    if config_error:
        metadata["config_error"] = config_error
    trace = status.get("generation_fallback_trace") if isinstance(status.get("generation_fallback_trace"), list) else []
    last_attempt = next(
        (
            item
            for item in reversed(trace)
            if isinstance(item, dict)
            and item.get("provider")
            and item.get("event")
            in {
                "request",
                "success",
                "quota_or_rate_limit",
                "provider_permission_denied",
                "fallback_next_provider",
                "fallback_exhausted",
            }
        ),
        {},
    )
    if last_attempt:
        metadata["provider"] = str(last_attempt.get("provider") or metadata.get("provider") or "")
        if last_attempt.get("model"):
            metadata["model"] = str(last_attempt.get("model") or "")
        metadata["last_attempted_provider"] = str(last_attempt.get("provider") or "")
        metadata["last_attempted_model"] = str(last_attempt.get("model") or metadata.get("model") or "")
        metadata["last_attempt_reason"] = str(last_attempt.get("reason") or "")
        metadata["last_attempt_event"] = str(last_attempt.get("event") or "")
    metadata["configured_provider"] = str(configured.get("provider") or "")
    metadata["configured_model"] = str(configured.get("model") or "")
    return metadata


def build_missing_project_status() -> dict[str, Any]:
    return {
        "task_id": "",
        "task_title": "",
        "project_status": "missing",
        "route_id": "",
        "route_label": "",
        "route_policy": {"allowed_actions": [], "forbidden_actions": []},
        "route_template_mode": "free",
        "route_template_required": False,
        "workflow_mode": "prompt_deck",
        "workflow_label": "\u9010\u9875\u751f\u6210 PPT",
        "recommended_next_action": {
            "key": "create_task",
            "label": "\u5f00\u59cb\u9010\u9875\u751f\u6210",
            "detail": "\u5148\u63cf\u8ff0\u7b2c 1 \u9875\u5185\u5bb9\uff0c\u518d\u5f00\u59cb\u9010\u9875\u751f\u6210\u3002",
        },
        "slide_count": 0,
        "slides": [],
        "slide_reviews": [],
        "export": {
            "status": "not_ready",
            "ready": False,
            "pptx_path": "",
            "last_returncode": None,
            "last_error": "",
        },
        "export_readiness": {
            "ready": False,
            "status": "not_ready",
            "reasons": ["project missing"],
            "missing_slides": [],
            "qa_failed_slides": [],
        },
        "last_finalize_mode": "unknown",
        "last_finalize_fresh_qa": "unknown",
        "last_finalize_cache_hit": "unknown",
        "last_qa_report_path": "",
        "last_contact_sheet_path": "",
        "qa_scope": "unknown",
        "checked_slide": None,
        "manual_review_required": None,
        "delivery_blocked": None,
        "artifact_buildable": False,
        "artifact_created": False,
        "hard_blockers": ["project-missing"],
        "quality_notes": [],
        "delivery_status": "not_downloadable",
        "delivery_approved": False,
        "delivery_contract": {},
        "planning": {
            "status": "not_checked",
            "slide_count": 0,
            "slide_type_distribution": {},
            "visual_archetype_distribution": {},
            "planning_error_count": 0,
            "planning_note_count": 0,
            "content_overload_slide_count": 0,
            "repeated_title_count": 0,
            "repeated_conclusion_count": 0,
            "manual_review_required": False,
            "report": "",
        },
        "visual_delivery_ready": False,
    }


def apply_export_readiness_state(
    status: dict[str, Any],
    readiness: dict[str, Any],
    *,
    stale_export_relpath: str,
    current_export_relpath: str,
) -> dict[str, Any]:
    export_state = status.setdefault("export", {})
    stale_export_exists = bool(stale_export_relpath)
    current_export_exists = bool(current_export_relpath)
    stale_budget_failure = (
        export_state.get("status") == "failed"
        and readiness.get("ready")
        and "Budget policy check failed" in str(export_state.get("last_error") or "")
    )
    if stale_budget_failure:
        export_state["status"] = readiness["status"]
        export_state["last_error"] = ""
    if export_state.get("status") in {"not_ready", "ready"}:
        export_state["status"] = readiness["status"]
    export_state["ready"] = readiness["ready"]
    export_state.setdefault("pptx_path", "")
    export_state.setdefault("last_returncode", None)
    export_state.setdefault("last_error", "")

    if stale_export_exists and not current_export_exists:
        export_state["stale_pptx_path"] = stale_export_relpath
        export_state["pptx_path"] = stale_export_relpath
        if export_state.get("status") in {"not_ready", "ready"}:
            export_state["status"] = "exported"
        status["project_status"] = compute_project_status(status, readiness)
    elif current_export_exists:
        export_state.pop("stale_pptx_path", None)
        export_state["pptx_path"] = current_export_relpath
        if export_state.get("status") in {"not_ready", "ready"}:
            export_state["status"] = "exported"
        status["project_status"] = compute_project_status(status, readiness)

    if current_export_exists and not export_state.get("pptx_path"):
        export_state["pptx_path"] = current_export_relpath
        if export_state.get("status") in {"not_ready", "ready"}:
            export_state["status"] = "exported"
        status["project_status"] = compute_project_status(status, readiness)
    if stale_budget_failure:
        status["project_status"] = compute_project_status(status, readiness)
    return export_state


def apply_finalize_evidence_to_export_state(
    status: dict[str, Any],
    readiness: dict[str, Any],
    evidence: dict[str, Any],
    *,
    current_export_relpath: str,
) -> dict[str, Any]:
    export_state = status.setdefault("export", {})
    current_export_exists = bool(current_export_relpath)
    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}

    if (
        current_export_exists
        and user_quality.get("can_download") is True
        and evidence.get("manual_review_required") is not True
        and evidence.get("delivery_blocked") is not True
    ):
        export_state["pptx_path"] = current_export_relpath
        export_state["status"] = "exported"
        export_state["last_returncode"] = 0
        export_state["last_error"] = str(user_quality.get("summary") or "")
        status["project_status"] = compute_project_status(status, readiness)
    elif current_export_exists and (evidence.get("delivery_blocked") is True or evidence.get("manual_review_required") is True):
        export_state["pptx_path"] = current_export_relpath
        export_state["status"] = "review_required"
        export_state["last_returncode"] = 0
        export_state["last_error"] = "PPT 已生成，可下载；检查提示仅作为重新生成参考。"
        status["project_status"] = compute_project_status(status, readiness)

    if (
        current_export_exists
        and evidence.get("delivery_blocked") is False
        and evidence.get("manual_review_required") is False
        and evidence.get("last_finalize_fresh_qa") is True
    ):
        export_state["pptx_path"] = current_export_relpath
        export_state["status"] = "exported"
        export_state["last_returncode"] = 0
        export_state["last_error"] = ""
        status["project_status"] = compute_project_status(status, readiness)

    last_error_code = str(export_state.get("last_error_code") or "")
    if (
        current_export_exists
        and export_state.get("status") in {"exported", "review_required"}
        and last_error_code.startswith("single_slide_export_")
    ):
        export_state["last_error"] = ""
        export_state["last_error_code"] = ""
        export_state["last_error_context"] = {}
    return export_state


def _positive_int_list(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        raw = item.get("slide_id") if isinstance(item, dict) else item
        try:
            slide_id = int(raw)
        except (TypeError, ValueError):
            continue
        if slide_id > 0 and slide_id not in result:
            result.append(slide_id)
    return sorted(result)


def _slide_ids_with_status(slides: object, statuses: set[str]) -> list[int]:
    if not isinstance(slides, list):
        return []
    result: list[int] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        if str(slide.get("status") or "") not in statuses:
            continue
        try:
            slide_id = int(slide.get("slide_id") or 0)
        except (TypeError, ValueError):
            continue
        if slide_id > 0 and slide_id not in result:
            result.append(slide_id)
    return sorted(result)


def _qa_summary(slides: object) -> dict[str, int]:
    summary = {"passed": 0, "failed": 0, "not_run": 0, "blocked": 0}
    if not isinstance(slides, list):
        return summary
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        qa_status = str(slide.get("qa_status") or "").strip() or "not_run"
        if qa_status == "passed":
            summary["passed"] += 1
        elif qa_status == "failed":
            summary["failed"] += 1
        elif qa_status == "blocked" or str(slide.get("status") or "") == "blocked":
            summary["blocked"] += 1
        else:
            summary["not_run"] += 1
    return summary


def build_delivery_contract_state(status: dict[str, Any], readiness: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    export_state = status.get("export") if isinstance(status.get("export"), dict) else {}
    context = export_state.get("last_error_context") if isinstance(export_state.get("last_error_context"), dict) else {}
    export_status = str(export_state.get("status") or "")
    scoped_slide_qa = evidence.get("qa_scope") == "slide"
    legacy_has_pptx = (
        bool(export_state.get("pptx_path"))
        and export_status in {"exported", "review_required"}
        and evidence.get("export_is_current") is not False
    )
    artifact_created_raw = evidence.get("artifact_created")
    artifact_created = bool(artifact_created_raw) if isinstance(artifact_created_raw, bool) else legacy_has_pptx
    if evidence.get("export_is_current") is False or evidence.get("pptx_openable") is False:
        artifact_created = False

    placeholder_slides = sorted(
        set(_positive_int_list(context.get("placeholder_slides")))
        | set(_positive_int_list(readiness.get("placeholder_slides")))
        | set(_positive_int_list(readiness.get("missing_slides")))
    )
    failed_statuses = {"failed"} if scoped_slide_qa else {"failed", "qa_failed", "needs_regeneration"}
    failed_slides = _slide_ids_with_status(slides, failed_statuses)
    blocked_slides = _slide_ids_with_status(slides, {"blocked", "waiting_cancelled", "skipped"})
    not_attempted_slides = _slide_ids_with_status(slides, {"not_started", "pending", "waiting"})
    qa = _qa_summary(slides)
    page_count_expected = int(status.get("slide_count") or len(slides) or 0)
    real_svg_count = sum(1 for slide in slides if isinstance(slide, dict) and slide.get("has_svg") is True)
    artifact_buildable = bool(readiness.get("artifact_buildable", readiness.get("ready")))
    page_count_exported = int(evidence.get("page_count_exported") or (page_count_expected if artifact_created else 0))
    raw_user_quality = evidence.get("user_quality")
    user_quality: dict[str, Any] = raw_user_quality if isinstance(raw_user_quality, dict) else {}
    hard_blockers = [str(code) for code in user_quality.get("hard_blocker_codes") or [] if str(code).strip()]
    quality_notes = [str(code) for code in user_quality.get("note_codes") or [] if str(code).strip()]

    def add_once(items: list[str], value: str) -> None:
        if value and value not in items:
            items.append(value)

    if page_count_expected <= 0:
        add_once(hard_blockers, "project-has-no-pages")
    if real_svg_count <= 0:
        add_once(hard_blockers, "project-has-no-real-svg")
    if missing_slides := sorted(set(_positive_int_list(readiness.get("missing_slides"))) | set(placeholder_slides)):
        add_once(hard_blockers, "missing-slides")
    if placeholder_slides:
        add_once(hard_blockers, "placeholder-slides")
    if failed_slides:
        add_once(hard_blockers, "failed-slides")
    if blocked_slides:
        add_once(hard_blockers, "blocked-slides")
    if not_attempted_slides:
        add_once(hard_blockers, "not-attempted-slides")
    if export_status == "failed":
        add_once(hard_blockers, "export-failed")
    if evidence.get("export_is_current") is False:
        add_once(hard_blockers, "export-stale")
    if evidence.get("pptx_openable") is False:
        add_once(hard_blockers, "invalid-pptx")
    if artifact_created and page_count_exported != page_count_expected:
        add_once(hard_blockers, "page-count-mismatch")
    if not artifact_created and export_status != "failed" and evidence.get("export_is_current") is not False:
        add_once(hard_blockers, "missing-pptx")
    if not scoped_slide_qa and (qa["failed"] or qa["blocked"]) and not user_quality.get("hard_blocker_codes"):
        add_once(quality_notes, "qa-review-required")
    if evidence.get("manual_review_required") is True:
        add_once(quality_notes, "manual-review-required")

    if not artifact_buildable and (not artifact_created or page_count_expected <= 0 or real_svg_count <= 0):
        delivery_status = "not_buildable"
    elif not artifact_created:
        delivery_status = "not_downloadable"
    elif hard_blockers:
        delivery_status = "blocked"
    elif quality_notes:
        delivery_status = "downloadable_with_notes"
    else:
        delivery_status = "quality_passed"

    delivery_approved = delivery_status in {"downloadable_with_notes", "quality_passed"}
    manual_review_required = bool(quality_notes)

    return {
        "artifact_buildable": artifact_buildable,
        "artifact_created": artifact_created,
        "page_count_expected": page_count_expected,
        "page_count_exported": page_count_exported,
        "real_svg_count": real_svg_count,
        "placeholder_count": len(placeholder_slides),
        "placeholder_slides": placeholder_slides,
        "failed_slides": failed_slides,
        "blocked_slides": blocked_slides,
        "not_attempted_slides": not_attempted_slides,
        "qa_summary": qa,
        "export_status": export_status or "not_started",
        "hard_blockers": hard_blockers,
        "quality_notes": quality_notes,
        "delivery_status": delivery_status,
        "delivery_approved": delivery_approved,
        "front_back_state_consistent": not bool(placeholder_slides or missing_slides),
        "manual_review_required": manual_review_required,
        "delivery_blocked": not delivery_approved,
    }


def apply_delivery_contract_state(
    status: dict[str, Any],
    readiness: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    contract = build_delivery_contract_state(status, readiness, evidence)
    status["delivery_status"] = contract["delivery_status"]
    status["delivery_approved"] = contract["delivery_approved"]
    status["delivery_contract"] = contract
    status["artifact_buildable"] = contract["artifact_buildable"]
    status["artifact_created"] = contract["artifact_created"]
    status["hard_blockers"] = contract["hard_blockers"]
    status["quality_notes"] = contract["quality_notes"]
    status["manual_review_required"] = contract["manual_review_required"]
    status["delivery_blocked"] = contract["delivery_blocked"]
    return contract
