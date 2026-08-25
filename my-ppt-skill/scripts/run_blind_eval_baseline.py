#!/usr/bin/env python3
"""Run blind evaluation baseline with explicit positive/negative/blind metrics."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from run_fixed_baseline import (
    _pick_summary_lines,
    _resolve_input_path,
    _resolve_output_path,
    _run_command,
    build_command,
    classify_failure,
    load_set_config,
    summarize_results,
)

PRIMARY_MODE_CHOICES = ("dev-fast", "release-safe")
MANUAL_VISUAL_REVIEW_STATUSES = {"pending", "complete", "reject"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run blind baseline set and emit JSON/Markdown summaries.",
    )
    parser.add_argument("--set", dest="set_path", default="", help="Path to blind eval set JSON.")
    parser.add_argument("--output-json", required=True, help="Result JSON output path.")
    parser.add_argument("--output-md", required=True, help="Markdown summary output path.")
    parser.add_argument("--mode", choices=("dev-fast", "release-safe", "both"), default="release-safe")
    parser.add_argument("--slide", type=int, default=1, help="Slide id for dev-fast mode (default: 1).")
    parser.add_argument(
        "--primary-mode",
        choices=PRIMARY_MODE_CHOICES,
        default="release-safe",
        help="Primary mode used for delivery/guardrail/blind metrics (default: release-safe).",
    )
    parser.add_argument(
        "--enforce-blind-ready",
        action="store_true",
        help="Return non-zero when blind_ready_gate is not pass.",
    )
    parser.add_argument(
        "--enforce-p0-risk-zero",
        action="store_true",
        help="Return non-zero when any P0 risk signal count is non-zero.",
    )
    parser.add_argument(
        "--enforce-manual-review-contract",
        action="store_true",
        help="Return non-zero when blind holdout manual review metadata contract is invalid.",
    )
    return parser.parse_args(argv)


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def _mode_sequence(mode: str) -> list[str]:
    if mode == "both":
        return ["dev-fast", "release-safe"]
    return [mode]


def _build_project_meta(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    projects = config.get("projects")
    if not isinstance(projects, list):
        return {}
    meta: dict[str, dict[str, Any]] = {}
    for item in projects:
        if not isinstance(item, dict):
            continue
        name = str(item.get("project") or "").strip()
        if not name:
            continue
        manual = item.get("manual_visual_review")
        manual_map = manual if isinstance(manual, dict) else {}
        meta[name] = {
            "manual_visual_review": manual_map,
            "sample_note": str(item.get("sample_note") or ""),
        }
    return meta


def validate_manual_review_contract(config: dict[str, Any]) -> list[str]:
    projects = config.get("projects")
    if not isinstance(projects, list):
        return []
    violations: list[str] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        role = str(item.get("baseline_role") or "").strip()
        if role != "blind_holdout":
            continue
        project_name = str(item.get("project") or "").strip() or "(unknown-project)"
        manual = item.get("manual_visual_review")
        if not isinstance(manual, dict):
            violations.append(f"{project_name}: missing manual_visual_review object")
            continue
        status = str(manual.get("status") or "").strip().lower()
        if status not in MANUAL_VISUAL_REVIEW_STATUSES:
            violations.append(
                f"{project_name}: invalid manual_visual_review.status='{status or '(empty)'}'"
            )
            continue
        if status in {"complete", "reject"}:
            reviewer = str(manual.get("reviewer") or "").strip()
            if not reviewer:
                violations.append(f"{project_name}: reviewer required when status={status}")
    return violations


def _holdout_required_artifacts(project_name: str, *, skill_dir: Path) -> tuple[list[str], list[str]]:
    base = skill_dir / "projects" / project_name
    required = [
        "style_route.json",
        "art_direction.md",
        "reference_pack.json",
        "slide_visual_plan.json",
        "svg_output/slide_01.svg",
    ]
    missing = [item for item in required if not (base / item).exists()]
    return required, missing


def run_blind_eval_set(
    config: dict[str, Any],
    *,
    mode: str,
    slide: int,
    skill_dir: Path,
) -> list[dict[str, Any]]:
    py = sys.executable
    modes = _mode_sequence(mode)
    projects = config.get("projects")
    if not isinstance(projects, list):
        return []

    results: list[dict[str, Any]] = []
    for project_entry in projects:
        if not isinstance(project_entry, dict):
            continue
        project_name = str(project_entry.get("project") or "").strip()
        if not project_name:
            continue

        role = str(project_entry.get("baseline_role") or "unknown").strip()
        expected_map = project_entry.get("expected")
        expected_map = expected_map if isinstance(expected_map, dict) else {}
        configured_modes_raw = project_entry.get("modes")
        configured_modes = (
            {str(item).strip() for item in configured_modes_raw}
            if isinstance(configured_modes_raw, list)
            else {"dev-fast", "release-safe"}
        )

        required_artifacts, missing_artifacts = _holdout_required_artifacts(
            project_name,
            skill_dir=skill_dir,
        )

        for run_mode in modes:
            if run_mode not in configured_modes:
                continue

            if role == "blind_holdout" and missing_artifacts:
                results.append(
                    {
                        "project": project_name,
                        "mode": run_mode,
                        "baseline_role": role,
                        "expected": str(expected_map.get(run_mode) or ""),
                        "status": "blocked",
                        "exit_code": 0,
                        "duration_seconds": 0.0,
                        "command": "",
                        "stdout_summary": "",
                        "stderr_summary": "",
                        "failure_category": "",
                        "command_error": "",
                        "ran_at": datetime.now().isoformat(timespec="seconds"),
                        "admission_status": "admission_blocked",
                        "admission_missing_artifacts": missing_artifacts,
                        "admission_required_artifacts": required_artifacts,
                    }
                )
                continue

            command = build_command(py, mode=run_mode, project=project_name, slide=slide)
            run = _run_command(command, cwd=skill_dir)
            status = "pass" if run.returncode == 0 else "fail"
            failure_category = ""
            if status == "fail":
                failure_category = classify_failure(
                    run.returncode,
                    run.stdout,
                    run.stderr,
                    command_error=run.command_error,
                )
            results.append(
                {
                    "project": project_name,
                    "mode": run_mode,
                    "baseline_role": role,
                    "expected": str(expected_map.get(run_mode) or ""),
                    "status": status,
                    "exit_code": run.returncode,
                    "duration_seconds": run.duration_seconds,
                    "command": " ".join(run.command),
                    "stdout_summary": _pick_summary_lines(run.stdout),
                    "stderr_summary": _pick_summary_lines(run.stderr),
                    "failure_category": failure_category,
                    "command_error": run.command_error,
                    "ran_at": datetime.now().isoformat(timespec="seconds"),
                    "admission_status": "admitted",
                    "admission_missing_artifacts": [],
                    "admission_required_artifacts": required_artifacts if role == "blind_holdout" else [],
                }
            )
    return results


def enrich_results_with_sample_meta(
    results: list[dict[str, Any]],
    *,
    project_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in results:
        project = str(row.get("project") or "")
        role = str(row.get("baseline_role") or "")
        meta = project_meta.get(project) or {}
        manual = meta.get("manual_visual_review")
        manual_map = manual if isinstance(manual, dict) else {}
        default_status = "pending" if role == "blind_holdout" else "n/a"
        manual_status = str(manual_map.get("status") or "").strip().lower() or default_status
        manual_score = manual_map.get("score")
        manual_reviewer = str(manual_map.get("reviewer") or "").strip()
        sample_note = str(meta.get("sample_note") or "")

        merged = dict(row)
        merged["manual_visual_review_status"] = manual_status
        merged["manual_visual_score"] = manual_score
        merged["manual_visual_reviewer"] = manual_reviewer
        merged["sample_note"] = sample_note
        merged["admission_status"] = str(row.get("admission_status") or "admitted")
        merged["admission_missing_artifacts"] = row.get("admission_missing_artifacts") or []
        enriched.append(merged)
    return enriched


def summarize_blind_metrics(
    results: list[dict[str, Any]],
    *,
    primary_mode: str,
) -> dict[str, Any]:
    in_primary_mode = [row for row in results if str(row.get("mode") or "") == primary_mode]
    executed_rows = [
        row
        for row in in_primary_mode
        if str(row.get("admission_status") or "admitted") == "admitted"
    ]
    positive_rows = [
        row for row in executed_rows if str(row.get("baseline_role") or "") == "positive_baseline"
    ]
    negative_rows = [
        row
        for row in executed_rows
        if str(row.get("baseline_role") or "") == "failure_regression"
        and str(row.get("expected") or "").strip().lower() == "fail"
    ]
    blind_rows = [row for row in executed_rows if str(row.get("baseline_role") or "") == "blind_holdout"]
    blocked_blind_rows = [
        row
        for row in in_primary_mode
        if str(row.get("baseline_role") or "") == "blind_holdout"
        and str(row.get("admission_status") or "") == "admission_blocked"
    ]

    positive_passed = sum(1 for row in positive_rows if str(row.get("status") or "") == "pass")
    negative_intercepted = sum(1 for row in negative_rows if str(row.get("status") or "") == "fail")
    blind_passed = sum(1 for row in blind_rows if str(row.get("status") or "") == "pass")

    blind_pending_manual = [
        row
        for row in blind_rows
        if str(row.get("manual_visual_review_status") or "").strip().lower() != "complete"
    ]
    blind_passed_pending_manual = [
        row
        for row in blind_pending_manual
        if str(row.get("status") or "").strip().lower() == "pass"
    ]

    blind_fail_reason_breakdown: dict[str, int] = {}
    for row in blind_rows:
        if str(row.get("status") or "") != "fail":
            continue
        reason = str(row.get("failure_category") or "unknown")
        blind_fail_reason_breakdown[reason] = blind_fail_reason_breakdown.get(reason, 0) + 1

    blind_ready_gate = (
        "pass"
        if len(blind_rows) > 0 and len(blind_passed_pending_manual) == 0
        else "fail"
    )

    qa_false_negative_projects: list[str] = []
    download_gate_false_allow_projects: list[str] = []
    release_safe_gate_inconsistency_projects: list[str] = []
    for row in blind_rows:
        row_status = str(row.get("status") or "")
        if row_status != "pass":
            continue
        manual_status = str(row.get("manual_visual_review_status") or "").strip().lower()
        if manual_status == "complete":
            continue
        project_name = str(row.get("project") or "")
        qa_false_negative_projects.append(project_name)
        stdout_summary = str(row.get("stdout_summary") or "").lower()
        if "manual review required: false" in stdout_summary:
            download_gate_false_allow_projects.append(project_name)
        if str(row.get("mode") or "") == "release-safe":
            release_safe_gate_inconsistency_projects.append(project_name)

    return {
        "primary_mode": primary_mode,
        "positive_delivery_pass_rate": {
            "passed": positive_passed,
            "total": len(positive_rows),
            "pass_rate_percent": _safe_rate(positive_passed, len(positive_rows)),
            "scope": f"positive_baseline + {primary_mode}",
        },
        "negative_guardrail_interception_rate": {
            "intercepted": negative_intercepted,
            "total": len(negative_rows),
            "interception_rate_percent": _safe_rate(negative_intercepted, len(negative_rows)),
            "scope": f"failure_regression(expected=fail) + {primary_mode}",
        },
        "real_blind_pass_rate": {
            "passed": blind_passed,
            "total": len(blind_rows),
            "pass_rate_percent": _safe_rate(blind_passed, len(blind_rows)),
            "scope": f"blind_holdout + {primary_mode}",
        },
        "control_expected_fail_count": len(negative_rows),
        "control_expected_fail_detected_count": negative_intercepted,
        "blind_holdout_executed_total": len(blind_rows),
        "blind_holdout_admission_blocked_total": len(blocked_blind_rows),
        "blind_holdout_admission_blocked_projects": [
            str(row.get("project") or "") for row in blocked_blind_rows
        ],
        "blind_holdout_fail_reason_breakdown": dict(sorted(blind_fail_reason_breakdown.items())),
        "blind_ready_gate": blind_ready_gate,
        "qa_false_negative_count": len(qa_false_negative_projects),
        "qa_false_negative_projects": qa_false_negative_projects,
        "download_gate_false_allow_count": len(download_gate_false_allow_projects),
        "download_gate_false_allow_projects": download_gate_false_allow_projects,
        "release_safe_gate_inconsistency_count": len(release_safe_gate_inconsistency_projects),
        "release_safe_gate_inconsistency_projects": release_safe_gate_inconsistency_projects,
        "manual_visual_scoring_pending": {
            "pending_total": len(blind_pending_manual),
            "pending_on_passed_blind_samples": len(blind_passed_pending_manual),
            "pending_projects": [str(row.get("project") or "") for row in blind_passed_pending_manual],
            "rule": "visual_score is not treated as manual visual approval",
        },
    }


def collect_enforcement_violations(
    blind_summary: dict[str, Any],
    *,
    enforce_blind_ready: bool,
    enforce_p0_risk_zero: bool,
) -> list[str]:
    violations: list[str] = []
    if enforce_blind_ready and str(blind_summary.get("blind_ready_gate") or "fail") != "pass":
        violations.append("blind_ready_gate != pass")

    if enforce_p0_risk_zero:
        checks = (
            ("qa_false_negative_count", int(blind_summary.get("qa_false_negative_count") or 0)),
            ("download_gate_false_allow_count", int(blind_summary.get("download_gate_false_allow_count") or 0)),
            (
                "release_safe_gate_inconsistency_count",
                int(blind_summary.get("release_safe_gate_inconsistency_count") or 0),
            ),
        )
        for name, count in checks:
            if count > 0:
                violations.append(f"{name}={count}")
    return violations


def build_markdown_summary(
    *,
    set_path: Path,
    mode: str,
    slide: int,
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    blind_summary: dict[str, Any],
    manual_review_contract_violations: list[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Blind Eval Batch Summary ({datetime.now().strftime('%Y-%m-%d')})")
    lines.append("")
    lines.append(f"- Set: `{set_path}`")
    lines.append(f"- Mode: `{mode}`")
    lines.append(f"- Dev-fast slide: `{slide}`")
    lines.append(f"- Total runs (including blocked): `{summary.get('total_runs_including_blocked', 0)}`")
    lines.append(f"- Executed runs (admitted only): `{summary.get('total_runs', 0)}`")
    lines.append(f"- Primary metric mode: `{blind_summary.get('primary_mode', 'release-safe')}`")
    lines.append("")
    lines.append("## Hard Rules")
    lines.append("")
    lines.append("- `dev-fast` is not treated as delivery proof for `release-safe`.")
    lines.append("- `visual_score` is not treated as manual aesthetic approval.")
    lines.append("- Plans/specs are not treated as implemented capability.")
    lines.append("")
    lines.append("## Core Metrics")
    lines.append("")
    lines.append("| Metric | Count | Rate | Scope |")
    lines.append("|---|---:|---:|---|")

    positive = blind_summary.get("positive_delivery_pass_rate") or {}
    lines.append(
        f"| positive delivery pass | {positive.get('passed', 0)}/{positive.get('total', 0)} | "
        f"{positive.get('pass_rate_percent', 0.0)}% | {positive.get('scope', '')} |"
    )
    negative = blind_summary.get("negative_guardrail_interception_rate") or {}
    lines.append(
        f"| negative guardrail interception | {negative.get('intercepted', 0)}/{negative.get('total', 0)} | "
        f"{negative.get('interception_rate_percent', 0.0)}% | {negative.get('scope', '')} |"
    )
    blind = blind_summary.get("real_blind_pass_rate") or {}
    lines.append(
        f"| real blind pass | {blind.get('passed', 0)}/{blind.get('total', 0)} | "
        f"{blind.get('pass_rate_percent', 0.0)}% | {blind.get('scope', '')} |"
    )
    manual = blind_summary.get("manual_visual_scoring_pending") or {}
    lines.append(
        f"| manual visual scoring pending (blind passed) | "
        f"{manual.get('pending_on_passed_blind_samples', 0)}/{blind.get('passed', 0)} | n/a | "
        "blind_holdout + manual_visual_review_status!=complete |"
    )
    lines.append(
        f"| blind holdout admission blocked | {blind_summary.get('blind_holdout_admission_blocked_total', 0)} | n/a | "
        "blind_holdout + missing required state artifacts |"
    )
    lines.append("")
    lines.append("## Control vs Holdout")
    lines.append("")
    lines.append(f"- Control expected-fail count: `{blind_summary.get('control_expected_fail_count', 0)}`")
    lines.append(
        f"- Control expected-fail detected count: `{blind_summary.get('control_expected_fail_detected_count', 0)}`"
    )
    lines.append(f"- Blind holdout executed total: `{blind_summary.get('blind_holdout_executed_total', 0)}`")
    lines.append(
        f"- Blind holdout admission blocked total: `{blind_summary.get('blind_holdout_admission_blocked_total', 0)}`"
    )
    blocked_projects = blind_summary.get("blind_holdout_admission_blocked_projects")
    if isinstance(blocked_projects, list) and blocked_projects:
        lines.append(f"- Admission blocked projects: `{', '.join(str(x) for x in blocked_projects)}`")
    else:
        lines.append("- Admission blocked projects: `(none)`")
    fail_breakdown = blind_summary.get("blind_holdout_fail_reason_breakdown")
    if isinstance(fail_breakdown, dict) and fail_breakdown:
        pairs = ", ".join(f"{key}={value}" for key, value in sorted(fail_breakdown.items()))
        lines.append(f"- Blind holdout fail reason breakdown: `{pairs}`")
    else:
        lines.append("- Blind holdout fail reason breakdown: `(none)`")
    lines.append("")
    lines.append("## Blind-Ready Gate")
    lines.append("")
    lines.append(f"- blind_ready_gate: `{blind_summary.get('blind_ready_gate', 'fail')}`")
    lines.append(
        "- Rule: pass only if blind_holdout_executed_total>0 and "
        "manual_visual_scoring_pending.pending_on_passed_blind_samples==0."
    )
    lines.append("")
    lines.append("## P0 Risk Signals")
    lines.append("")
    lines.append(
        f"- qa_false_negative_count: `{blind_summary.get('qa_false_negative_count', 0)}`; "
        f"projects: `{', '.join(blind_summary.get('qa_false_negative_projects') or []) or '(none)'}`"
    )
    lines.append(
        f"- download_gate_false_allow_count: `{blind_summary.get('download_gate_false_allow_count', 0)}`; "
        f"projects: `{', '.join(blind_summary.get('download_gate_false_allow_projects') or []) or '(none)'}`"
    )
    lines.append(
        f"- release_safe_gate_inconsistency_count: "
        f"`{blind_summary.get('release_safe_gate_inconsistency_count', 0)}`; "
        f"projects: `{', '.join(blind_summary.get('release_safe_gate_inconsistency_projects') or []) or '(none)'}`"
    )
    lines.append("")
    lines.append("## Manual Visual Pending")
    lines.append("")
    lines.append(f"- Pending blind samples (all): `{manual.get('pending_total', 0)}`")
    pending_projects = manual.get("pending_projects")
    if isinstance(pending_projects, list) and pending_projects:
        lines.append(f"- Pending project list (blind + passed): `{', '.join(str(x) for x in pending_projects)}`")
    else:
        lines.append("- Pending project list (blind + passed): `(none)`")
    lines.append("")
    lines.append("## Manual Review Contract")
    lines.append("")
    issues = manual_review_contract_violations or []
    if issues:
        lines.append(f"- status: `fail` ({len(issues)} violations)")
        for issue in issues:
            lines.append(f"- violation: `{issue}`")
    else:
        lines.append("- status: `pass`")
    lines.append("")
    lines.append("## Failure Category")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    failures = summary.get("failure_categories") or {}
    if isinstance(failures, dict) and failures:
        for key, value in failures.items():
            lines.append(f"| `{key}` | {value} |")
    else:
        lines.append("| `(none)` | 0 |")
    lines.append("")
    lines.append("## Per Project Result")
    lines.append("")
    lines.append(
        "| Project | Role | Mode | Status | Exit | Failure Category | Admission | Missing Artifacts | "
        "Manual Visual | Snippet |"
    )
    lines.append("|---|---|---|---|---:|---|---|---|---|---|")
    for row in results:
        snippet = row.get("stderr_summary") or row.get("stdout_summary") or row.get("command_error") or ""
        safe_snippet = str(snippet).replace("|", "\\|")
        manual_status = str(row.get("manual_visual_review_status") or "pending")
        admission = str(row.get("admission_status") or "admitted")
        missing = row.get("admission_missing_artifacts")
        missing_text = ",".join(str(item) for item in missing) if isinstance(missing, list) and missing else "-"
        lines.append(
            f"| `{row.get('project')}` | `{row.get('baseline_role')}` | `{row.get('mode')}` | "
            f"`{row.get('status')}` | {row.get('exit_code')} | `{row.get('failure_category') or '-'}` | "
            f"`{admission}` | `{missing_text}` | `{manual_status}` | {safe_snippet} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Blind metrics are computed only on `primary_mode` to avoid mixing `dev-fast` and delivery gates.")
    lines.append("- `manual_visual_review_status=complete` must come from human review records, not automated score.")
    lines.append("- `admission_blocked` rows are not counted as blind execution failures.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    set_path = _resolve_input_path(args.set_path)
    output_json = _resolve_output_path(args.output_json)
    output_md = _resolve_output_path(args.output_md)

    if not set_path.exists():
        print(f"error: set file not found: {set_path}")
        return 2

    config = load_set_config(set_path)
    project_meta = _build_project_meta(config)
    skill_dir = Path(__file__).resolve().parents[1]
    all_results = run_blind_eval_set(
        config,
        mode=args.mode,
        slide=max(1, int(args.slide)),
        skill_dir=skill_dir,
    )
    enriched_results = enrich_results_with_sample_meta(all_results, project_meta=project_meta)
    executed_results = [
        row for row in enriched_results if str(row.get("admission_status") or "admitted") == "admitted"
    ]
    summary = summarize_results(executed_results)
    summary["total_runs_including_blocked"] = len(enriched_results)
    summary["admission"] = {
        "blocked_total": sum(
            1 for row in enriched_results if str(row.get("admission_status") or "") == "admission_blocked"
        ),
        "blocked_projects": [
            str(row.get("project") or "")
            for row in enriched_results
            if str(row.get("admission_status") or "") == "admission_blocked"
        ],
    }
    blind_summary = summarize_blind_metrics(
        enriched_results,
        primary_mode=args.primary_mode,
    )
    manual_review_contract_violations = validate_manual_review_contract(config)

    payload = {
        "set_name": str(config.get("set_name") or ""),
        "set_path": str(set_path),
        "mode": args.mode,
        "slide": max(1, int(args.slide)),
        "primary_mode": args.primary_mode,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "results": enriched_results,
        "summary": summary,
        "blind_summary": blind_summary,
        "rules": {
            "dev_fast_not_release_safe": True,
            "visual_score_not_manual_approval": True,
            "plans_not_implementation": True,
        },
        "enforcement": {
            "enforce_blind_ready": bool(args.enforce_blind_ready),
            "enforce_p0_risk_zero": bool(args.enforce_p0_risk_zero),
            "enforce_manual_review_contract": bool(args.enforce_manual_review_contract),
        },
        "manual_review_contract": {
            "status": "pass" if not manual_review_contract_violations else "fail",
            "violations": manual_review_contract_violations,
        },
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = build_markdown_summary(
        set_path=set_path,
        mode=args.mode,
        slide=max(1, int(args.slide)),
        results=enriched_results,
        summary=summary,
        blind_summary=blind_summary,
        manual_review_contract_violations=manual_review_contract_violations,
    )
    output_md.write_text(markdown, encoding="utf-8")

    print(f"wrote json: {output_json}")
    print(f"wrote markdown: {output_md}")
    print(
        "blind metrics:",
        f"positive={blind_summary['positive_delivery_pass_rate']['pass_rate_percent']}%,",
        f"negative={blind_summary['negative_guardrail_interception_rate']['interception_rate_percent']}%,",
        f"blind={blind_summary['real_blind_pass_rate']['pass_rate_percent']}%,",
        f"blind_ready={blind_summary['blind_ready_gate']}",
    )
    violations = collect_enforcement_violations(
        blind_summary,
        enforce_blind_ready=bool(args.enforce_blind_ready),
        enforce_p0_risk_zero=bool(args.enforce_p0_risk_zero),
    )
    if violations:
        print("enforcement violations:", "; ".join(violations))
        return 1
    if args.enforce_manual_review_contract and manual_review_contract_violations:
        print("manual review contract violations:", "; ".join(manual_review_contract_violations))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
