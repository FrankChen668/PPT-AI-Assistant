#!/usr/bin/env python3
"""QA reporting and repair output writers.

This module is intentionally independent from qa_project.py orchestration.
Public entrypoints in qa_project.py should delegate report/repair artifact
generation here so QA CLI behavior stays stable while internals deepen.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from quality.report_io import write_report_json, write_report_markdown

BUDGET_NON_BLOCKING_WARNING_CODES = {
    "slide-budget-high",
    "slide-budget-medium",
}
DESIGN_TOKEN_NON_BLOCKING_WARNING_CODES = {
    "theme-readability-low-contrast",
    "theme-readability-token-missing",
    "design-token-missing",
    "design-token-unparseable",
}
ASSET_NON_BLOCKING_WARNING_CODES = {
    "icon-ref-missing",
    "chart-color-outside-palette",
    "data-palette-missing",
}
RELEASE_SAFE_NON_BLOCKING_WARNING_CODES = {
    "style-hard-token-color-limit",
    "style-hard-token-consecutive-homogeneous",
    "style-hard-token-conclusion-hierarchy-weak",
    "visual-contract-missing",
    "visual-contract-incomplete",
    "visual-contract-invalid-read-path",
    "visual-contract-invalid-density-budget",
    "visual-contract-invalid-anti-patterns",
    "visual-contract-scene-mismatch",
}
SINGLE_SLIDE_MAX_RETRY_ATTEMPTS = 2
DECK_LEVEL_MAX_RETRY_ATTEMPTS = 1


def _asdict_finding(item: Any) -> dict[str, Any]:
    if is_dataclass(item) and not isinstance(item, type):
        return asdict(item)
    if isinstance(item, dict):
        return dict(item)
    return {
        "severity": str(getattr(item, "severity", "")),
        "code": str(getattr(item, "code", "")),
        "path": str(getattr(item, "path", "")),
        "message": str(getattr(item, "message", "")),
    }


def _normalize_quality_mode(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in {"dev-fast", "release-safe", "premium"}:
        return candidate
    return "dev-fast"


def _is_warning_non_blocking(code: str, quality_mode: str) -> bool:
    mode = _normalize_quality_mode(quality_mode)
    if code in BUDGET_NON_BLOCKING_WARNING_CODES:
        return True
    if code in DESIGN_TOKEN_NON_BLOCKING_WARNING_CODES:
        return True
    if code in ASSET_NON_BLOCKING_WARNING_CODES:
        return True
    if mode == "release-safe" and code in RELEASE_SAFE_NON_BLOCKING_WARNING_CODES:
        return True
    return False


def _is_visual_delivery_code(code: str) -> bool:
    return code.startswith("visual-") or code.startswith("style-") or code.startswith("prompt-pattern-")


def _is_delivery_blocking_finding(finding: Any, quality_mode: str, strict_effective: bool) -> bool:
    severity = str(getattr(finding, "severity", ""))
    code = str(getattr(finding, "code", ""))
    if severity == "error":
        return True
    if not strict_effective:
        return False
    if severity != "warning":
        return False
    return not _is_warning_non_blocking(code, quality_mode)


def _project_cli_path(project_path: str) -> str:
    project_path_obj = Path(project_path)
    if project_path_obj.is_absolute():
        project_name = project_path_obj.name
        return f"projects/{project_name}"
    normalized = project_path_obj.as_posix().strip("./")
    if normalized.startswith("projects/"):
        return normalized
    return f"projects/{normalized}"


def _infer_slide_id_from_finding(finding: Any) -> int | None:
    path_text = str(getattr(finding, "path", "")).replace("\\", "/")
    match = re.search(r"slide_(\d+)\.svg", path_text)
    if match:
        return int(match.group(1))
    message = str(getattr(finding, "message", ""))
    match = re.search(r"\bslide\s+(\d+)\b", message, flags=re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _repair_category_for_code(code: str) -> str:
    if code.startswith("visual-"):
        return "visual_layout"
    if code.startswith("style-"):
        return "visual_style"
    if code.startswith("reference-pack-"):
        return "reference_contract"
    if code.startswith("svg-"):
        return "svg_compliance"
    if code.startswith("pptx-"):
        return "export_output"
    if code.startswith("blueprint-"):
        return "blueprint_contract"
    if code.startswith("template-"):
        return "template_contract"
    return "qa_general"


def _source_check_for_code(code: str) -> str:
    if code.startswith(("visual-", "style-", "prompt-pattern-")):
        return "visual_qa"
    if code.startswith("reference-pack-"):
        return "reference_first_gate"
    if code.startswith(("overflow-risk-", "slide-budget-")):
        return "slide_budget"
    if code.startswith("design-token-"):
        return "design_token_guard"
    if code.startswith(("icon-ref-", "chart-color-", "data-palette-")):
        return "asset_palette_guard"
    if code.startswith("banned-term-"):
        return "banned_terms_guard"
    if code.startswith(("layout-", "svg-", "missing-svg-", "invalid-viewbox", "unsupported-node")):
        return "svg_contract_check"
    if code.startswith("blueprint-"):
        return "blueprint_contract_check"
    return "qa_core"


def _verification_command_for_repair(
    *,
    project_cli_path: str,
    slide_id: int | None,
    quality_mode: str,
    profile: str,
    enable_visual_qa: bool,
) -> str:
    if slide_id is not None:
        cmd = f"python scripts/qa_project.py {project_cli_path} --snapshots --slide {slide_id}"
    else:
        cmd = f"python scripts/qa_project.py {project_cli_path} --snapshots"
    if quality_mode != "dev-fast":
        cmd += f" --quality-mode {quality_mode}"
    if profile and profile != "presentation":
        cmd += f" --profile {profile}"
    if enable_visual_qa:
        cmd += " --enable-visual-qa"
    return cmd


def _repair_scope(slide_id: int | None) -> str:
    return "single_slide" if slide_id is not None else "deck_level"


def _target_svg_for_slide(slide_id: int | None) -> str | None:
    if slide_id is None:
        return None
    return f"svg_output/slide_{slide_id:02d}.svg"


def _repair_relevant_files(project_cli_path: str, slide_id: int | None) -> list[str]:
    files = [
        f"{project_cli_path}/design_spec.md",
        f"{project_cli_path}/blueprint.json",
        f"{project_cli_path}/art_direction.md",
        f"{project_cli_path}/slide_visual_plan.json",
    ]
    if slide_id is not None:
        files.append(f"{project_cli_path}/svg_output/slide_{slide_id:02d}.svg")
        files.append(f"{project_cli_path}/qa/snapshots/slide_{slide_id:02d}.png")
    else:
        files.append(f"{project_cli_path}/qa/report.json")
        files.append(f"{project_cli_path}/qa/repair_plan.json")
    return files


def _is_svg_contrast_finding(code: str, message: str) -> bool:
    if code == "svg-contrast-illegible":
        return True
    if code != "svg-quality":
        return False
    lowered = message.strip().lower()
    return "contrast low" in lowered or "contrast too low" in lowered


def _local_contrast_repair_action() -> str:
    return (
        "这是局部文字-背景对比度问题。只改目标页的文字或局部背景组合：先查看告警 y 坐标附近的 "
        "文字 fill 与其最后绘制的覆盖背景；深色面板改用浅色文字，浅色或强调底改用足够深的文字。"
        "保持原文、结构和几何不变；禁止通过降低/关闭 QA 解决。"
    )


def _local_text_overlap_repair_action() -> str:
    return (
        "这是目标页内的文字框重叠问题。只改目标页：先根据告警坐标定位碰撞的两段文字及其容器。"
        "若确认是主标题与相邻内容卡，先划分互不侵入的标题区和内容区，确认二者不共享边界；"
        "优先按语义换行或缩短标题；若仍冲突，调整相邻内容卡的位置或尺寸以保留清楚间隔。"
        "若是其他文字框组合，保持语义层级并仅调整实际发生碰撞的一方，不把它误当作标题-内容卡问题。"
        "保持主结论和页面层级；"
        "不得通过缩小关键标题、降低/关闭 QA 解决。"
    )


def _executor_prompt_hint(issue_code: str, message: str, recommended_action: str, slide_id: int | None) -> str:
    slide_hint = f"slide {slide_id}" if slide_id is not None else "deck-level issue"
    return (
        f"Fix {slide_hint}: [{issue_code}] {message}\n"
        f"Apply: {recommended_action}\n"
        "Only edit target slide SVG when repair_scope=single_slide."
    )


def _forbidden_shortcuts() -> list[str]:
    return [
        "do_not_run_render_svg_over_ai_authored_svg",
        "do_not_use_pptxgenjs_or_temp_python_pptx_exporter",
        "do_not_bypass_build_project_finalize_skip_render",
    ]


def _visual_review_gate_recommended_action() -> str:
    return (
        "Deck-level visual gate is not ready. Stop single-slide repair loop for now; "
        "first align deck-level artifacts and visual plan consistency, then rerun full QA. "
        "If blockers become single-slide actionable, continue with generate_repair_prompt --slide <id>."
    )


def _repair_reject_code(issue_code: str, repair_scope: str) -> str:
    code = str(issue_code or "").strip()
    scope = str(repair_scope or "").strip().lower()
    if scope == "deck_level":
        return "deck_level_recovery_required"
    if code.startswith(("visual-", "style-", "prompt-pattern-")):
        return "single_slide_visual_repair_required"
    if code.startswith(("slide-budget-", "overflow-risk-")):
        return "single_slide_budget_repair_required"
    return "single_slide_contract_repair_required"


def _retry_budget(repair_scope: str) -> dict[str, Any]:
    scope = str(repair_scope or "").strip().lower()
    if scope == "deck_level":
        return {
            "max_attempts": DECK_LEVEL_MAX_RETRY_ATTEMPTS,
            "attempted": 0,
            "escalation": "owner_review_required",
        }
    return {
        "max_attempts": SINGLE_SLIDE_MAX_RETRY_ATTEMPTS,
        "attempted": 0,
        "escalation": "upgrade_to_deck_level_replan",
    }


def _visual_review_gate_item(
    *,
    project_cli: str,
    quality_mode: str,
    profile: str,
    enable_visual_qa: bool,
    readiness_status: str,
    visual_delivery_ready: bool,
    manual_review_required: bool,
) -> dict[str, Any]:
    message = (
        "Visual delivery gate requires follow-up: "
        f"readiness_status={readiness_status}, "
        f"visual_delivery_ready={str(visual_delivery_ready).lower()}, "
        f"manual_review_required={str(manual_review_required).lower()}."
    )
    action = _visual_review_gate_recommended_action()
    return {
        "slide_id": None,
        "deck_level": True,
        "repair_scope": "deck_level",
        "reject_code": "deck_level_recovery_required",
        "retry_budget": _retry_budget("deck_level"),
        "category": "visual_delivery_gate",
        "issue_code": "visual-delivery-review-required",
        "source_check": "delivery_gate",
        "message": message,
        "recommended_action": action,
        "verification_command": _verification_command_for_repair(
            project_cli_path=project_cli,
            slide_id=None,
            quality_mode=quality_mode,
            profile=profile,
            enable_visual_qa=enable_visual_qa,
        ),
        "target_svg": None,
        "relevant_files": _repair_relevant_files(project_cli, None),
        "executor_prompt_hint": _executor_prompt_hint(
            "visual-delivery-review-required",
            message,
            action,
            None,
        ),
        "forbidden_shortcuts": _forbidden_shortcuts(),
        "severity": "warning",
        "is_blocking": True,
        "deterministic_repair_safe": False,
    }


def _recommended_action_for_blocker(finding: Any, slide_id: int | None) -> str:
    code = str(getattr(finding, "code", ""))
    message = str(getattr(finding, "message", ""))
    if _is_svg_contrast_finding(code, message):
        return _local_contrast_repair_action()
    if code == "text-overlap-risk":
        return _local_text_overlap_repair_action()
    if code == "reference-pack-empty":
        return (
            "Run `python scripts/select_reference_templates.py projects/<project_name>` "
            "or record selected template/reference files "
            "in reference_pack.json before State 3. If free-design is intentional, set free_design_override_reason."
        )
    if code == "reference-pack-free-design-reason-missing":
        return (
            "Add free_design_override_reason to reference_pack.json explaining why "
            "template/history references were not used."
        )
    if code in {
        "template-binding-reference-pack-mismatch",
        "template-binding-slide-visual-plan-mismatch",
    }:
        return (
            "Align reference_pack/slide_visual_plan with template_binding.json. "
            "If this is intentional free-design, document override_reason explicitly and rerun generate_art_direction."
        )
    if code in {"missing-reference-pack-for-binding", "missing-slide-visual-plan-for-binding"}:
        return (
            "Create or restore reference_pack.json and slide_visual_plan.json for State 2.5, "
            "or document intentional template override reason before rerunning QA."
        )
    if code in {
        "invalid-template-binding-json",
        "invalid-reference-pack-json",
        "invalid-slide-visual-plan-json",
        "template-binding-missing-layout-id",
    }:
        return (
            "Fix template_binding/reference_pack/slide_visual_plan JSON validity and schema fields, "
            "then rerun generate_art_direction and QA."
        )
    if code == "missing-svg-dir":
        return (
            "Complete State 3 authoring first: create or restore `svg_output/slide_XX.svg` files "
            "for the deck, then rerun QA."
        )
    if code == "text-outside-canvas":
        return "Move overflowing text blocks inside safe area; shorten copy or rebalance columns."
    if code == "invalid-viewbox":
        return "Normalize SVG canvas width/height/viewBox to project canvas spec."
    if code == "style-over-cardization":
        return (
            "Reduce card count and rebalance into one conclusion bar plus up to "
            "three evidence modules per dense page."
        )
    if code == "style-rhythm-monotony":
        return "Break repeated layout rhythm by switching at least one page to a different composition archetype."
    if code in {"style-conclusion-first-weak", "style-takeaway-bar-missing", "visual-headline-weak"}:
        return "Promote the key conclusion to the top safe area with clear hierarchy before supporting details."
    if code == "style-conclusion-competition":
        return (
            "Merge competing conclusion zones into one core conclusion area per page; "
            "demote secondary statements to supporting evidence blocks."
        )
    if code == "style-claim-boundary-unqualified":
        return (
            "Add an explicit qualifier (预计/计划/假设/拟/待验证 or equivalent) to the on-canvas "
            "conclusion so assumption/inference claims are not presented as established results."
        )
    if code in {"visual-hierarchy-flat", "visual-text-fragmented", "visual-density-high"}:
        return "Simplify copy blocks and rebuild a stronger title/body hierarchy with fewer fragmented text nodes."
    if code in {"visual-alignment-chaos", "visual-whitespace-low", "visual-dominance-weak"}:
        return "Re-align modules to fewer alignment tracks and restore whitespace balance between major sections."
    if code == "text-cjk-longline-in-narrow-column":
        return "Rewrite CJK long lines in narrow columns with controlled wrapping to remove hard-break artifacts."
    if code.startswith("visual-") or code.startswith("style-"):
        return "Refine hierarchy, spacing, and emphasis to satisfy visual delivery gate."
    if slide_id is not None:
        return "Repair this slide in svg_output/slide_XX.svg and rerun single-slide QA."
    return "Resolve deck-level blockers and rerun full QA."


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_uat_status(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"open", "in_progress", "resolved", "ignored", "wontfix"}:
        return candidate
    return "open"


def _finding_signature(finding: Any) -> str:
    code = str(getattr(finding, "code", ""))
    path = str(getattr(finding, "path", ""))
    message = str(getattr(finding, "message", ""))
    raw = "\n".join([code, path, message])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _next_uat_issue_id(issues: list[dict[str, Any]]) -> str:
    max_id = 0
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        match = re.fullmatch(r"UAT-(\d+)", str(issue.get("id") or ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"UAT-{max_id + 1:04d}"


def _render_uat_markdown(payload: dict[str, Any]) -> str:
    project = str(payload.get("project") or "")
    updated_at = str(payload.get("generated_at") or "")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []
    runs = payload.get("runs")
    if not isinstance(runs, list):
        runs = []

    lines = [
        "# UAT Issue Log",
        "",
        f"- project: `{project}`",
        f"- updated_at: `{updated_at}`",
        f"- total_issues: `{summary.get('total_issues', 0)}`",
        f"- open: `{summary.get('open', 0)}`",
        f"- in_progress: `{summary.get('in_progress', 0)}`",
        f"- resolved: `{summary.get('resolved', 0)}`",
        f"- ignored: `{summary.get('ignored', 0)}`",
        f"- wontfix: `{summary.get('wontfix', 0)}`",
        "",
        "## Notes",
        "",
        "- Edit `qa/uat_issues.json` field `status` to track triage (`open|in_progress|resolved|ignored|wontfix`).",
        "- If a resolved/ignored issue appears again in QA findings, it reopens automatically.",
        "",
        "## Latest Runs",
        "",
    ]
    if not runs:
        lines.append("No run history.")
    else:
        lines.append("| generated_at | ok | errors | warnings | advisories | checked_slide |")
        lines.append("|---|---:|---:|---:|---:|---|")
        for run in runs[-10:]:
            if not isinstance(run, dict):
                continue
            lines.append(
                "| "
                f"{run.get('generated_at', '')} | "
                f"{run.get('ok', '')} | "
                f"{run.get('errors', '')} | "
                f"{run.get('warnings', '')} | "
                f"{run.get('advisories', '')} | "
                f"{run.get('checked_slide', '')} |"
            )

    lines.extend(["", "## Issues", ""])
    if not issues:
        lines.append("No issues recorded.")
        return "\n".join(lines) + "\n"

    lines.append("| id | status | severity | code | occurrences | last_seen | path |")
    lines.append("|---|---|---|---|---:|---|---|")
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        lines.append(
            "| "
            f"{issue.get('id', '')} | "
            f"{issue.get('status', '')} | "
            f"{issue.get('severity', '')} | "
            f"{issue.get('code', '')} | "
            f"{issue.get('occurrences', 0)} | "
            f"{issue.get('last_seen', '')} | "
            f"{issue.get('path', '')} |"
        )
    return "\n".join(lines) + "\n"


def write_uat_issue_log(report: Any, qa_dir: Path) -> None:
    log_path = qa_dir / "uat_issues.json"
    markdown_path = qa_dir / "uat_issues.md"
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")

    payload: dict[str, Any] = {"project": report.project, "generated_at": generated_at, "runs": [], "issues": []}
    if log_path.exists():
        try:
            loaded = json.loads(log_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload.update(
                    {
                        key: value
                        for key, value in loaded.items()
                        if key in {"project", "generated_at", "summary", "runs", "issues"}
                    }
                )
        except Exception:
            payload = {"project": report.project, "generated_at": generated_at, "runs": [], "issues": []}

    runs = payload.get("runs")
    if not isinstance(runs, list):
        runs = []
    issues = payload.get("issues")
    if not isinstance(issues, list):
        issues = []

    signature_map: dict[str, dict[str, Any]] = {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        signature = str(issue.get("signature") or "").strip()
        if not signature:
            continue
        issue["status"] = _normalize_uat_status(issue.get("status"))
        issue["occurrences"] = max(1, _to_int(issue.get("occurrences"), 1))
        issue["reopen_count"] = max(0, _to_int(issue.get("reopen_count"), 0))
        signature_map[signature] = issue

    seen_signatures: set[str] = set()
    for finding in report.findings:
        signature = _finding_signature(finding)
        seen_signatures.add(signature)
        issue = signature_map.get(signature)
        if issue is None:
            issue = {
                "id": _next_uat_issue_id(issues),
                "signature": signature,
                "status": "open",
                "severity": str(getattr(finding, "severity", "")),
                "code": str(getattr(finding, "code", "")),
                "path": str(getattr(finding, "path", "")),
                "message": str(getattr(finding, "message", "")),
                "first_seen": generated_at,
                "last_seen": generated_at,
                "occurrences": 1,
                "reopen_count": 0,
                "present_in_latest_run": True,
            }
            issues.append(issue)
            signature_map[signature] = issue
            continue

        was_closed = issue.get("status") in {"resolved", "ignored", "wontfix"}
        issue["severity"] = str(getattr(finding, "severity", ""))
        issue["code"] = str(getattr(finding, "code", ""))
        issue["path"] = str(getattr(finding, "path", ""))
        issue["message"] = str(getattr(finding, "message", ""))
        issue["last_seen"] = generated_at
        issue["occurrences"] = _to_int(issue.get("occurrences"), 0) + 1
        issue["present_in_latest_run"] = True
        if was_closed:
            issue["status"] = "open"
            issue["reopen_count"] = _to_int(issue.get("reopen_count"), 0) + 1
            issue["reopened_at"] = generated_at

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("signature") or "") not in seen_signatures:
            issue["present_in_latest_run"] = False

    runs.append(
        {
            "generated_at": generated_at,
            "ok": bool(report.ok),
            "errors": int(report.errors),
            "warnings": int(report.warnings),
            "advisories": int(report.advisories),
            "checked_slide": report.metrics.get("checked_slide"),
            "finding_count": len(report.findings),
        }
    )
    if len(runs) > 200:
        runs = runs[-200:]

    status_counts = {"open": 0, "in_progress": 0, "resolved": 0, "ignored": 0, "wontfix": 0}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        status = _normalize_uat_status(issue.get("status"))
        issue["status"] = status
        status_counts[status] = status_counts.get(status, 0) + 1

    payload = {
        "project": report.project,
        "generated_at": generated_at,
        "summary": {
            "total_issues": len([item for item in issues if isinstance(item, dict)]),
            "open": status_counts.get("open", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "resolved": status_counts.get("resolved", 0),
            "ignored": status_counts.get("ignored", 0),
            "wontfix": status_counts.get("wontfix", 0),
        },
        "runs": runs,
        "issues": issues,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_uat_markdown(payload), encoding="utf-8")


def _is_deterministic_repair_safe(code: str, severity: str) -> bool:
    safe_codes = {
        "visual-density-high",
        "visual-text-fragmented",
        "visual-headline-weak",
        "visual-hierarchy-flat",
        "visual-alignment-chaos",
    }
    if code in safe_codes:
        return True
    return severity in {"advisory", "warning"} and code.startswith("visual-")


def _style_specific_repair_hint(code: str, style_profile: str) -> str | None:
    profile = style_profile.strip() or "current profile"
    if code == "style-over-cardization":
        return (
            f"{profile}: reduce card density and prioritize 1 conclusion bar + up to 3 evidence blocks "
            "on each dense page."
        )
    if code == "style-rhythm-monotony":
        return (
            f"{profile}: break repeated split layouts; replace every third similar structure with "
            "a vertical timeline or center-radial composition."
        )
    if code in {"style-conclusion-first-weak", "visual-headline-weak"}:
        return (
            f"{profile}: promote a decisive headline in the top safe area before supporting details."
        )
    return None


def write_repair_plan(
    report: Any,
    qa_dir: Path,
    *,
    readiness_status: str | None = None,
    visual_delivery_ready: bool | None = None,
    manual_review_required: bool | None = None,
) -> list[dict[str, Any]]:
    slide_actions: dict[int, list[str]] = defaultdict(list)
    for item in report.repair_recommendation or []:
        slide = item.get("slide")
        actions = item.get("actions")
        if isinstance(slide, int) and isinstance(actions, list):
            slide_actions[slide].extend(str(action) for action in actions if isinstance(action, str))

    quality_mode = _normalize_quality_mode(str(report.metrics.get("quality_mode") or "dev-fast"))
    strict_effective = bool(report.metrics.get("strict_effective") or quality_mode in {"release-safe", "premium"})
    profile = str(report.metrics.get("profile") or "presentation")
    enable_visual_qa = bool(report.metrics.get("enable_visual_qa"))
    project_cli = _project_cli_path(report.project)
    blocking_findings = [
        item
        for item in report.findings
        if _is_delivery_blocking_finding(item, quality_mode=quality_mode, strict_effective=strict_effective)
    ]

    entries: list[dict[str, Any]] = []
    seen_keys: set[tuple[int | None, str, str]] = set()
    style_profile = str(report.metrics.get("style_profile") or "").strip()
    for visual_finding in report.visual_findings or []:
        slide = visual_finding.get("slide")
        code = str(visual_finding.get("code") or "")
        severity = str(visual_finding.get("severity") or "advisory")
        if not isinstance(slide, int) or not code:
            continue
        actions = slide_actions.get(slide) or ["Refine this slide directly in svg_output/slide_XX.svg."]
        style_hint = _style_specific_repair_hint(code, style_profile)
        for action in actions:
            unique_key_visual: tuple[int | None, str, str] = (slide, code, action)
            if unique_key_visual in seen_keys:
                continue
            seen_keys.add(unique_key_visual)
            item = {
                "slide_id": slide,
                "deck_level": False,
                "repair_scope": _repair_scope(slide),
                "reject_code": _repair_reject_code(code, _repair_scope(slide)),
                "retry_budget": _retry_budget(_repair_scope(slide)),
                "category": _repair_category_for_code(code),
                "issue_code": code,
                "source_check": _source_check_for_code(code),
                "message": str(visual_finding.get("message") or ""),
                "recommended_action": action,
                "verification_command": _verification_command_for_repair(
                    project_cli_path=project_cli,
                    slide_id=slide,
                    quality_mode=quality_mode,
                    profile=profile,
                    enable_visual_qa=enable_visual_qa,
                ),
                "target_svg": _target_svg_for_slide(slide),
                "relevant_files": _repair_relevant_files(project_cli, slide),
                "executor_prompt_hint": _executor_prompt_hint(
                    code,
                    str(visual_finding.get("message") or ""),
                    action,
                    slide,
                ),
                "forbidden_shortcuts": _forbidden_shortcuts(),
                "severity": severity,
                "is_blocking": False,
                "deterministic_repair_safe": _is_deterministic_repair_safe(code, severity),
            }
            if style_hint:
                item["style_specific_hint"] = style_hint
            entries.append(item)

    for blocking_finding in blocking_findings:
        slide_id = _infer_slide_id_from_finding(blocking_finding)
        action = _recommended_action_for_blocker(blocking_finding, slide_id)
        unique_key_blocking: tuple[int | None, str, str] = (
            slide_id,
            str(getattr(blocking_finding, "code", "")),
            action,
        )
        if unique_key_blocking in seen_keys:
            continue
        seen_keys.add(unique_key_blocking)
        entries.append(
            {
                "slide_id": slide_id,
                "deck_level": slide_id is None,
                "repair_scope": _repair_scope(slide_id),
                "reject_code": _repair_reject_code(
                    str(getattr(blocking_finding, "code", "")),
                    _repair_scope(slide_id),
                ),
                "retry_budget": _retry_budget(_repair_scope(slide_id)),
                "category": _repair_category_for_code(str(getattr(blocking_finding, "code", ""))),
                "issue_code": str(getattr(blocking_finding, "code", "")),
                "source_check": _source_check_for_code(str(getattr(blocking_finding, "code", ""))),
                "message": str(getattr(blocking_finding, "message", "")),
                "recommended_action": action,
                "verification_command": _verification_command_for_repair(
                    project_cli_path=project_cli,
                    slide_id=slide_id,
                    quality_mode=quality_mode,
                    profile=profile,
                    enable_visual_qa=enable_visual_qa,
                ),
                "target_svg": _target_svg_for_slide(slide_id),
                "relevant_files": _repair_relevant_files(project_cli, slide_id),
                "executor_prompt_hint": _executor_prompt_hint(
                    str(getattr(blocking_finding, "code", "")),
                    str(getattr(blocking_finding, "message", "")),
                    action,
                    slide_id,
                ),
                "forbidden_shortcuts": _forbidden_shortcuts(),
                "severity": str(getattr(blocking_finding, "severity", "")),
                "is_blocking": True,
                "deterministic_repair_safe": _is_deterministic_repair_safe(
                    str(getattr(blocking_finding, "code", "")),
                    str(getattr(blocking_finding, "severity", "")),
                ),
            }
        )

    add_visual_gate_item = (
        readiness_status == "visual_review_required"
        or visual_delivery_ready is False
        or manual_review_required is True
    )
    has_blocking_entry = any(bool(item.get("is_blocking")) for item in entries)
    if add_visual_gate_item and not has_blocking_entry:
        entries.append(
            _visual_review_gate_item(
                project_cli=project_cli,
                quality_mode=quality_mode,
                profile=profile,
                enable_visual_qa=enable_visual_qa,
                readiness_status=str(readiness_status or "visual_review_required"),
                visual_delivery_ready=bool(visual_delivery_ready) if visual_delivery_ready is not None else False,
                manual_review_required=bool(manual_review_required)
                if manual_review_required is not None
                else True,
            )
        )

    payload = {
        "project": report.project,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "execution_guard": {
            "single_slide_max_retry_attempts": SINGLE_SLIDE_MAX_RETRY_ATTEMPTS,
            "deck_level_max_retry_attempts": DECK_LEVEL_MAX_RETRY_ATTEMPTS,
            "policy": "structure_pass_then_polish_then_qa; escalate after retry budget is exhausted",
        },
        "items": entries,
    }
    (qa_dir / "repair_plan.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return entries


def _delivery_readiness_status(
    *,
    engineering_pass: bool,
    visual_delivery_ready: bool,
    manual_review_required: bool,
    delivery_blocked: bool,
) -> str:
    if not engineering_pass:
        return "engineering_failed"
    if delivery_blocked:
        return "blocked"
    if not visual_delivery_ready or manual_review_required:
        return "visual_review_required"
    return "ready"


def _delivery_readiness_summary(status: str) -> str:
    if status == "ready":
        return "Engineering and visual delivery gates are both ready."
    if status == "visual_review_required":
        return "Engineering export passed, but visual delivery still requires review or polish."
    if status == "blocked":
        return "Delivery has blocking QA findings that must be repaired before use."
    return "Engineering checks failed; do not treat the artifact as deliverable."


def write_reports(report: Any, qa_dir: Path) -> None:
    qa_dir.mkdir(parents=True, exist_ok=True)
    quality_mode = _normalize_quality_mode(str(report.metrics.get("quality_mode") or "dev-fast"))
    strict_effective = bool(report.metrics.get("strict_effective") or quality_mode in {"release-safe", "premium"})
    template_consistency = report.metrics.get("template_consistency") if isinstance(report.metrics, dict) else None
    if not isinstance(template_consistency, dict):
        template_consistency = {
            "ok": True,
            "warning_count": 0,
            "error_count": 0,
            "advisory_count": 0,
            "warnings": [],
            "errors": [],
            "advisories": [],
            "findings": [],
        }
    blocking_findings = [
        item
        for item in report.findings
        if _is_delivery_blocking_finding(item, quality_mode=quality_mode, strict_effective=strict_effective)
    ]
    blocking_visual_warning_codes = sorted(
        {
            str(getattr(item, "code", ""))
            for item in blocking_findings
            if str(getattr(item, "severity", "")) == "warning"
            and _is_visual_delivery_code(str(getattr(item, "code", "")))
        }
    )
    engineering_pass = int(report.errors) == 0
    high_score_density_advisory_only = bool(
        report.density_flag
        and int(report.warnings) == 0
        and (report.visual_score or 0) >= 95
    )
    visual_baseline_ready = bool(
        report.visual_score is None
        or (
            report.visual_score >= 85
            and (not report.density_flag or high_score_density_advisory_only)
            and not report.hierarchy_flag
        )
    )
    visual_delivery_ready = visual_baseline_ready and not blocking_visual_warning_codes
    delivery_blocked = bool(blocking_findings)
    visual_critic_codes = [
        str(code)
        for code in report.metrics.get("visual_critic_gate_blocking_codes", [])
        if str(code)
    ]
    manual_review_required = (not visual_delivery_ready) or delivery_blocked
    readiness_status = _delivery_readiness_status(
        engineering_pass=engineering_pass,
        visual_delivery_ready=visual_delivery_ready,
        manual_review_required=manual_review_required,
        delivery_blocked=delivery_blocked,
    )
    readiness_summary = _delivery_readiness_summary(readiness_status)
    non_blocking_warning_count = int(report.metrics.get("budget_non_blocking_warning_count", 0)) + int(
        report.metrics.get("design_token_non_blocking_warning_count", 0)
    ) + int(report.metrics.get("asset_non_blocking_warning_count", 0)) + int(
        report.metrics.get("release_safe_non_blocking_warning_count", 0)
    )
    blocking_warning_count = sum(1 for item in blocking_findings if str(getattr(item, "severity", "")) == "warning")
    review_warning_count = max(0, int(report.warnings) - non_blocking_warning_count - blocking_warning_count)
    layered_verdict = {
        "quality_mode": quality_mode,
        "profile": str(report.metrics.get("profile") or "presentation"),
        "strict_effective": strict_effective,
        "readiness_status": readiness_status,
        "readiness_summary": readiness_summary,
        "engineering_pass": engineering_pass,
        "visual_baseline_ready": visual_baseline_ready,
        "visual_delivery_ready": visual_delivery_ready,
        "manual_review_required": manual_review_required,
        "delivery_blocked": delivery_blocked,
        "warning_count": int(report.warnings),
        "non_blocking_warning_count": non_blocking_warning_count,
        "review_warning_count": review_warning_count,
        "advisory_count": int(report.advisories),
        "visual_critic_gate_blocking_codes": visual_critic_codes,
        "blocking_finding_count": len(blocking_findings),
        "blocking_visual_warning_codes": blocking_visual_warning_codes,
        "blocking_findings": [_asdict_finding(item) for item in blocking_findings],
    }
    report_payload = {
        "project": report.project,
        "ok": report.ok,
        "errors": report.errors,
        "warnings": report.warnings,
        "advisories": report.advisories,
        "findings": [_asdict_finding(item) for item in report.findings],
        "metrics": report.metrics,
        "template_consistency": template_consistency,
        "visual_score": report.visual_score,
        "visual_findings": report.visual_findings or [],
        "repair_recommendation": report.repair_recommendation or [],
        "density_flag": report.density_flag,
        "hierarchy_flag": report.hierarchy_flag,
        "layered_verdict": layered_verdict,
        "engineering_pass": engineering_pass,
        "visual_delivery_ready": visual_delivery_ready,
        "manual_review_required": manual_review_required,
        "readiness_status": readiness_status,
        "readiness_summary": readiness_summary,
        "blocking_findings": layered_verdict["blocking_findings"],
    }
    write_report_json(qa_dir, report_payload)
    repair_items = write_repair_plan(
        report,
        qa_dir,
        readiness_status=readiness_status,
        visual_delivery_ready=visual_delivery_ready,
        manual_review_required=manual_review_required,
    )
    blocking_repair_items = [item for item in repair_items if bool(item.get("is_blocking"))]

    lines = [
        "# QA Report",
        "",
        f"- project: `{report.project}`",
        f"- ok: `{report.ok}`",
        f"- errors: `{report.errors}`",
        f"- warnings: `{report.warnings}`",
        f"- advisories: `{report.advisories}`",
        f"- visual_score: `{report.visual_score}`",
        f"- density_flag: `{report.density_flag}`",
        f"- hierarchy_flag: `{report.hierarchy_flag}`",
        f"- readiness_status: `{readiness_status}`",
        f"- engineering_pass: `{engineering_pass}`",
        f"- visual_delivery_ready: `{visual_delivery_ready}`",
        f"- manual_review_required: `{manual_review_required}`",
        f"- template_consistency_ok: `{template_consistency.get('ok', True)}`",
        f"- template_consistency_warnings: `{template_consistency.get('warning_count', 0)}`",
        f"- template_consistency_errors: `{template_consistency.get('error_count', 0)}`",
        "",
        "## Layered Verdict",
        "",
        f"- Quality Mode: `{quality_mode}`",
        f"- Profile: `{report.metrics.get('profile', 'presentation')}`",
        f"- Strict Effective: `{strict_effective}`",
        f"- Readiness Status: `{readiness_status}`",
        f"- Visual Critic Gate Blockers: `{visual_critic_codes}`",
        f"- Engineering Gate: `{'PASS' if engineering_pass else 'FAIL'}`",
        f"- Visual Baseline: `{'PASS' if visual_baseline_ready else 'REVIEW'}`",
        f"- Visual Deliverability: `{'READY' if visual_delivery_ready else 'REVIEW'}`",
        f"- Manual Review: `{'REQUIRED' if manual_review_required else 'NOT_REQUIRED'}`",
        f"- Blocking Findings: `{len(blocking_findings)}`",
        f"- Non-blocking Warnings: `{non_blocking_warning_count}`",
        f"- Review Warnings: `{review_warning_count}`",
        f"- Advisories: `{int(report.advisories)}`",
        "",
        "## Readiness Summary",
        "",
        f"- Status: `{readiness_status}`",
        f"- Meaning: {readiness_summary}",
        f"- Engineering export: `{'PASS' if engineering_pass else 'FAIL'}`",
        f"- Visual delivery: `{'READY' if visual_delivery_ready else 'REVIEW_REQUIRED'}`",
        f"- Manual review: `{'REQUIRED' if manual_review_required else 'NOT_REQUIRED'}`",
        f"- Blocking findings: `{len(blocking_findings)}`",
        f"- Non-blocking warnings: `{non_blocking_warning_count}`",
        f"- Review warnings: `{review_warning_count}`",
        "",
        "## Template Consistency",
        "",
        f"- ok: `{template_consistency.get('ok', True)}`",
        f"- warning_count: `{template_consistency.get('warning_count', 0)}`",
        f"- error_count: `{template_consistency.get('error_count', 0)}`",
        f"- advisory_count: `{template_consistency.get('advisory_count', 0)}`",
    ]
    template_findings = template_consistency.get("findings") if isinstance(template_consistency, dict) else []
    if isinstance(template_findings, list) and template_findings:
        for item in template_findings:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- **{item.get('severity', 'advisory')}** `{item.get('code', 'unknown')}` at "
                f"`{item.get('path', report.project)}`: {item.get('message', '')}"
            )
    else:
        lines.append("- No template consistency findings.")
    lines.extend(["", "## Metrics", ""])
    for key, value in report.metrics.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("No findings.")
    else:
        for finding in report.findings:
            lines.append(
                f"- **{getattr(finding, 'severity', '')}** `{getattr(finding, 'code', '')}` "
                f"at `{getattr(finding, 'path', '')}`: {getattr(finding, 'message', '')}"
            )
    lines.extend(["", "## Blocking Findings", ""])
    if not blocking_findings:
        lines.append("No delivery blockers in current quality mode.")
    else:
        for finding in blocking_findings:
            lines.append(
                f"- **{getattr(finding, 'severity', '')}** `{getattr(finding, 'code', '')}` "
                f"at `{getattr(finding, 'path', '')}`: {getattr(finding, 'message', '')}"
            )
    lines.extend(["", "## Next Actions", ""])
    if not blocking_repair_items:
        lines.append("No blocking repair actions. Continue with routine QA follow-up as needed.")
    else:
        for item in blocking_repair_items[:8]:
            scope = f"slide {item.get('slide_id')}" if item.get("slide_id") else "deck-level"
            lines.append(
                f"- [{item.get('severity', 'warning')}] `{item.get('issue_code')}` "
                f"({scope}, {item.get('category', 'qa_general')}): "
                f"{item.get('recommended_action')} Verify: `{item.get('verification_command')}`"
            )
    lines.extend(["", "## Visual Recommendations", ""])
    if not report.repair_recommendation:
        lines.append("No repair recommendations.")
    else:
        for item in report.repair_recommendation:
            slide = item.get("slide")
            actions = item.get("actions") or []
            lines.append(f"- slide `{slide}`:")
            for action in actions:
                lines.append(f"  - {action}")
    write_report_markdown(qa_dir, "\n".join(lines) + "\n")
    write_uat_issue_log(report, qa_dir)
