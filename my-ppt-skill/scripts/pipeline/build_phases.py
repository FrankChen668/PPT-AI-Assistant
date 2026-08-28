from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


def handle_authoring_phase(
    *,
    phase: str,
    project_dir: Path,
    timestamp: str,
    mode: str,
    artifact_name: str,
    skip_render: bool,
    strict: bool,
    snapshots: bool,
    enable_layout_lint: bool,
    layout_lint_strict: bool,
    layout_quality_profile: str,
    enforce_blueprint_sync: bool,
    safe_area_profile: str,
    profile: str,
    quality_mode: str,
    svg_only_export: bool,
    safe_edge_whitelist_set: set[str],
    incremental: bool,
    source_hashes: dict[str, Any],
    normalized_changed_slides: list[int],
    started_at: datetime,
    started_perf: float,
    context_profile: dict[str, Any],
    fallback_policy_version: str,
    token_budget_assessment: dict[str, Any],
    page_summary_assessment: dict[str, Any],
    template_lookup_assessment: dict[str, Any],
    checkpoint_assessment: dict[str, Any],
    layout_exploration_assessment: dict[str, Any],
    stage_timing: dict[str, float],
    preflight_report: Any,
    layout_lint_report: Any,
    append_manifest: Callable[[Path, dict[str, Any]], None],
    write_incremental_cache: Callable[[Path, dict[str, Any]], None],
    blueprint_slide_count: Callable[[Path], int],
    extract_quality_tiers: Callable[..., dict[str, int]],
    project_relative_path: Callable[[Path, Path], str],
    normalize_stage_metrics: Callable[..., dict[str, Any]],
) -> bool:
    if phase != "authoring":
        return False

    elapsed = round(perf_counter() - started_perf, 4)
    stage_metrics = normalize_stage_metrics(
        phase=phase,
        stage_timing=stage_timing,
        build_duration_sec=elapsed,
    )
    authoring_manifest_record: dict[str, Any] = {
        "project_name": project_dir.name,
        "timestamp": timestamp,
        "phase": phase,
        "mode": mode,
        "artifact_name_mode": artifact_name,
        "output_files": [],
        "slide_count": blueprint_slide_count(project_dir),
        "skip_render": skip_render,
        "strict": strict,
        "snapshots": snapshots,
        "layout_lint_enabled": enable_layout_lint,
        "layout_lint_strict": layout_lint_strict,
        "layout_quality_profile": layout_quality_profile,
        "enforce_blueprint_sync": enforce_blueprint_sync,
        "safe_area_profile": safe_area_profile,
        "profile": profile,
        "quality_mode": quality_mode,
        "svg_only_export": svg_only_export,
        "safe_edge_whitelist": sorted(safe_edge_whitelist_set),
        "incremental_mode": incremental,
        "incremental_cache_hit": False,
        "source_hashes": source_hashes,
        "changed_slides": normalized_changed_slides,
        "build_started_at": started_at.isoformat(timespec="seconds"),
        "build_finished_at": datetime.now().isoformat(timespec="seconds"),
        "build_duration_sec": elapsed,
        "context_file_count": context_profile["context_file_count"],
        "context_bytes_estimate": context_profile["context_bytes_estimate"],
        "context_files": context_profile["context_files"],
        "fallback_policy_version": fallback_policy_version,
        "fallback_event_count": 0,
        "fallback_events": [],
        "failure_error_code": "none",
        "failure_action_hint": "none",
    }
    authoring_manifest_record.update(token_budget_assessment)
    authoring_manifest_record.update(page_summary_assessment)
    authoring_manifest_record.update(template_lookup_assessment)
    authoring_manifest_record.update(checkpoint_assessment)
    authoring_manifest_record.update(layout_exploration_assessment)
    authoring_manifest_record.update(stage_timing)
    authoring_manifest_record.update(stage_metrics)
    if preflight_report is not None:
        authoring_manifest_record["preflight_errors"] = preflight_report.errors
        authoring_manifest_record["preflight_warnings"] = preflight_report.warnings
        authoring_manifest_record["preflight_report"] = project_relative_path(project_dir, preflight_report.report_md)
    if layout_lint_report is not None:
        authoring_manifest_record["layout_lint_errors"] = layout_lint_report.errors
        authoring_manifest_record["layout_lint_warnings"] = layout_lint_report.warnings
        authoring_manifest_record["layout_lint_advisories"] = layout_lint_report.advisories
        authoring_manifest_record["layout_quality_warning_count"] = int(
            layout_lint_report.metrics.get("quality_warning_count", 0)
        )
        authoring_manifest_record["layout_quality_error_count"] = int(
            layout_lint_report.metrics.get("quality_error_count", 0)
        )
        authoring_manifest_record["layout_quality_advisory_count"] = int(
            layout_lint_report.metrics.get("quality_advisory_count", 0)
        )
        authoring_manifest_record["overflow_risk_high_count"] = int(
            layout_lint_report.metrics.get("overflow_risk_high_count", 0)
        )
        authoring_manifest_record["overflow_risk_medium_count"] = int(
            layout_lint_report.metrics.get("overflow_risk_medium_count", 0)
        )
        authoring_manifest_record["overflow_risk_low_count"] = int(
            layout_lint_report.metrics.get("overflow_risk_low_count", 0)
        )
        authoring_manifest_record["overflow_risk_blocking_count"] = (
            authoring_manifest_record["overflow_risk_high_count"] if quality_mode in {"release-safe", "premium"} else 0
        )
        authoring_manifest_record["layout_lint_quality_tiers"] = extract_quality_tiers(
            layout_lint_report.metrics,
            fallback_errors=layout_lint_report.errors,
            fallback_warnings=layout_lint_report.warnings,
        )
        authoring_manifest_record["quality_tiers"] = authoring_manifest_record["layout_lint_quality_tiers"]
    append_manifest(project_dir, authoring_manifest_record)
    if incremental:
        write_incremental_cache(
            project_dir,
            {
                "phase": phase,
                "source_hashes": source_hashes,
                "output_files": [],
                "qa_ok": True,
            },
        )
    print(f"Wrote {project_dir / 'exports' / 'manifest.json'}")
    print("Authoring phase completed: preflight/layout-lint finished, export skipped.")
    return True


def handle_finalize_skip_qa_phase(
    *,
    phase: str,
    skip_qa: bool,
    artifact_created: bool,
    project_dir: Path,
    stage_timing: dict[str, float],
    started_perf: float,
    output_file_entries: list[str],
    incremental: bool,
    source_hashes: dict[str, Any],
    failure_error_code: str,
    failure_action_hint: str,
    update_manifest_last_record: Callable[[Path, dict[str, Any]], None],
    print_delivery_status: Callable[..., None],
    write_incremental_cache: Callable[[Path, dict[str, Any]], None],
    normalize_stage_metrics: Callable[..., dict[str, Any]],
    infer_stage_failure: Callable[..., dict[str, Any]],
    delivery_status_tuple: Callable[..., tuple[bool, str, list[str]]],
    fallback_action_hint: Callable[[str], str],
) -> bool:
    if phase == "authoring" or not skip_qa:
        return False

    delivery_approved, delivery_status, delivery_failure_reasons = delivery_status_tuple(
        artifact_created=artifact_created,
        qa_report=None,
    )
    skip_qa_elapsed = round(perf_counter() - started_perf, 4)
    skip_qa_stage_metrics = normalize_stage_metrics(
        phase=phase,
        stage_timing=stage_timing,
        build_duration_sec=skip_qa_elapsed,
    )
    skip_qa_failure = infer_stage_failure(
        delivery_approved=delivery_approved,
        delivery_status=delivery_status,
        delivery_failure_reasons=delivery_failure_reasons,
    )
    update_manifest_last_record(
        project_dir,
        {
            "artifact_created": artifact_created,
            "delivery_approved": delivery_approved,
            "delivery_status": delivery_status,
            "delivery_failure_reasons": delivery_failure_reasons,
            "build_finished_at": datetime.now().isoformat(timespec="seconds"),
            "build_duration_sec": skip_qa_elapsed,
            **skip_qa_stage_metrics,
            **skip_qa_failure,
            "failure_error_code": failure_error_code
            if failure_error_code != "none"
            else skip_qa_failure.get("stage_failure_code", "none"),
            "failure_action_hint": failure_action_hint
            if failure_action_hint != "none"
            else fallback_action_hint(skip_qa_failure.get("stage_failure_code", "none")),
        },
    )
    print_delivery_status(
        artifact_created=artifact_created,
        delivery_approved=delivery_approved,
        delivery_status=delivery_status,
        delivery_failure_reasons=delivery_failure_reasons,
        qa_report_path=str(project_dir / "qa" / "report.md"),
    )
    if incremental:
        write_incremental_cache(
            project_dir,
            {
                "phase": phase,
                "source_hashes": source_hashes,
                "output_files": output_file_entries,
                "qa_ok": True,
            },
        )
    return True
