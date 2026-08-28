#!/usr/bin/env python3
"""Generate copyable Executor single-slide repair prompt from qa/repair_plan.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class RepairPromptSelectionError(RuntimeError):
    """Raised when repair prompt cannot be selected from repair_plan items."""


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _project_cli_path(project_dir: Path) -> str:
    parts_lower = [part.lower() for part in project_dir.parts]
    for index, part in enumerate(parts_lower):
        if part == "projects" and index + 1 < len(project_dir.parts):
            return Path(*project_dir.parts[index:]).as_posix()
    return Path("projects", project_dir.name).as_posix()


def _load_repair_plan(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "qa" / "repair_plan.json"
    if not path.exists():
        project_cli = _project_cli_path(project_dir)
        raise FileNotFoundError(
            f"repair_plan not found: {path}\n"
            f"next_step: run `python scripts/qa_project.py {project_cli} --snapshots` first."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"invalid repair_plan.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("invalid repair_plan.json: root must be object")
    return payload


def _normalize_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items_raw = payload.get("items")
    if not isinstance(items_raw, list):
        return []
    items: list[dict[str, Any]] = []
    for index, item in enumerate(items_raw, start=1):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        normalized.setdefault("action_id", index)
        items.append(normalized)
    return items


def _available_summary(items: list[dict[str, Any]], *, blocking_only: bool = True) -> str:
    source = [item for item in items if bool(item.get("is_blocking"))] if blocking_only else items
    if not source:
        return "none"
    lines: list[str] = []
    for item in source:
        action = _as_int(item.get("action_id"))
        slide = _as_int(item.get("slide_id"))
        code = str(item.get("issue_code") or "unknown-issue")
        scope = str(item.get("repair_scope") or ("single_slide" if slide is not None else "deck_level"))
        lines.append(
            f"- action_id={action if action is not None else '?'} "
            f"slide={slide if slide is not None else 'deck'} scope={scope} code={code}"
        )
    return "\n".join(lines)


def _merge_forbidden_shortcuts(values: list[str]) -> list[str]:
    baseline = [
        "不得全量重渲染整套页面。",
        "不得使用 render_svg.py 覆盖 AI-authored svg_output。",
        "不得通过 copyfit 牺牲关键结论语义。",
        "不得修改非目标 slide。",
    ]
    merged = [*values]
    existing = {item.strip() for item in merged}
    for item in baseline:
        if item.strip() not in existing:
            merged.append(item)
    return merged


def _pick_actionable_items(
    items: list[dict[str, Any]],
    *,
    slide_id: int | None,
    action_id: int | None,
) -> list[dict[str, Any]]:
    selected = [item for item in items if bool(item.get("is_blocking"))]
    if action_id is not None:
        selected = [item for item in selected if _as_int(item.get("action_id")) == action_id]
    if slide_id is not None:
        selected = [item for item in selected if _as_int(item.get("slide_id")) == slide_id]
    return selected


def _fmt_list(values: list[str]) -> str:
    if not values:
        return "- 无"
    return "\n".join(f"- {value}" for value in values)


def _load_visual_contract(project_dir: Path, slide_id: int | None) -> dict[str, Any] | None:
    if slide_id is None:
        return None
    path = project_dir / "slide_visual_plan.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    slides = payload.get("slides")
    if not isinstance(slides, list):
        return None
    for item in slides:
        if not isinstance(item, dict):
            continue
        item_slide_id = _as_int(item.get("slide_id"))
        if item_slide_id != slide_id:
            continue
        contract = item.get("visual_contract")
        if isinstance(contract, dict):
            return contract
    return None


def _render_visual_contract_section(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return "visual_contract：\n- 无（slide_visual_plan.json 未提供目标页 contract）"
    return "\n".join(
        [
            "visual_contract（来自 slide_visual_plan.json）：",
            f"- scene_type: {contract.get('scene_type')}",
            f"- generation_strategy: {contract.get('generation_strategy')}",
            f"- focal_point: {contract.get('focal_point')}",
            f"- composition_grammar: {contract.get('composition_grammar')}",
            f"- density_budget: {contract.get('density_budget')}",
            f"- layout_intent: {contract.get('layout_intent')}",
            f"- bbox_budget: {contract.get('bbox_budget')}",
            f"- text_budget: {contract.get('text_budget')}",
            f"- deterministic_scaffold: {contract.get('deterministic_scaffold')}",
            f"- anti_patterns: {contract.get('anti_patterns')}",
            f"- must_avoid: {contract.get('must_avoid')}",
            f"- pre_authoring_checks: {contract.get('pre_authoring_checks')}",
        ]
    )


def _render_prompt(project_dir: Path, selected: list[dict[str, Any]]) -> str:
    project_cli = _project_cli_path(project_dir)
    target = selected[0]
    slide_id = _as_int(target.get("slide_id"))
    default_target_svg = f"svg_output/slide_{slide_id:02d}.svg" if isinstance(slide_id, int) else ""
    target_svg = str(target.get("target_svg") or default_target_svg)

    relevant_files_raw = target.get("relevant_files")
    relevant_files = [str(item) for item in relevant_files_raw] if isinstance(relevant_files_raw, list) else []
    if not relevant_files:
        relevant_files = [
            f"{project_cli}/design_spec.md",
            f"{project_cli}/blueprint.json",
            f"{project_cli}/art_direction.md",
            f"{project_cli}/slide_visual_plan.json",
        ]
        if target_svg:
            relevant_files.append(f"{project_cli}/{target_svg}")

    forbidden_raw = target.get("forbidden_shortcuts")
    forbidden = [str(item) for item in forbidden_raw] if isinstance(forbidden_raw, list) else []
    forbidden = _merge_forbidden_shortcuts(forbidden)

    verification_command = str(
        target.get("verification_command")
        or f"python scripts/qa_project.py {project_cli} --snapshots"
    )
    issue_code = str(target.get("issue_code") or "unknown-issue")
    reject_code = str(target.get("reject_code") or "")
    category = str(target.get("category") or "qa_general")
    source_check = str(target.get("source_check") or "qa_project")
    severity = str(target.get("severity") or "warning")
    message = str(target.get("message") or "")
    recommended_action = str(target.get("recommended_action") or "")
    executor_prompt_hint = str(target.get("executor_prompt_hint") or "")
    repair_scope = str(target.get("repair_scope") or ("single_slide" if isinstance(slide_id, int) else "deck_level"))
    retry_budget = target.get("retry_budget") if isinstance(target.get("retry_budget"), dict) else {}
    retry_max = int(retry_budget.get("max_attempts") or 0) if retry_budget else 0
    retry_attempted = int(retry_budget.get("attempted") or 0) if retry_budget else 0
    retry_escalation = str(retry_budget.get("escalation") or "") if retry_budget else ""
    visual_contract = _load_visual_contract(project_dir, slide_id)
    visual_contract_section = _render_visual_contract_section(visual_contract)
    is_deck_level = repair_scope == "deck_level" or not isinstance(slide_id, int)

    slide_line = str(slide_id) if isinstance(slide_id, int) else "deck-level"
    svg_line = target_svg or "（该项为 deck-level，无单页 SVG）"
    if is_deck_level:
        scope_execution_rules = "\n".join(
            [
                "- 这是 deck-level 阻断，不要直接进入单页 SVG 修复循环。",
                (
                    "- 先修复 deck 级输入/门禁问题（如 "
                    "reference/style_route/art_direction/visual plan/状态门禁），"
                    "再重新运行全量 QA。"
                ),
                "- 仅在 blocker 下降为 single_slide 项后，再用 `--slide <id>` 进入单页修复。",
            ]
        )
        scope_intent = "先做 deck-level 恢复，再转单页修复（如果仍需要）。"
    else:
        scope_execution_rules = "\n".join(
            [
                "- 仅修改目标页相关内容，不做全局重构。",
                "- 不要自动改其它页。",
                "- 保持咨询页信息层级、结论优先、可读性优先。",
            ]
        )
        scope_intent = "按单页方式修复并立即复核。"

    task_kind = "deck-level 修复任务" if is_deck_level else "单页修复任务"
    prompt = f"""你现在是本项目的 Executor，请按以下{task_kind}执行（只做修复，不新增功能）：

项目路径：`{project_cli}`
动作编号：`{target.get('action_id', '?')}`
修复范围：`{repair_scope}`
目标页：`{slide_line}`
目标 SVG：`{svg_line}`

请先阅读这些文件：
{_fmt_list(relevant_files)}

问题信息：
- 类别：`{category}`
- 来源检查：`{source_check}`
- 严重性：`{severity}`
- issue_code：`{issue_code}`
- reject_code：`{reject_code or 'n/a'}`
- 原始 message：{message}

{visual_contract_section}

修复意图（必须落实）：
- {recommended_action}
- 执行提示：{executor_prompt_hint or "按 recommended_action 执行，并保持修改面最小化。"}
- 范围策略：{scope_intent}

执行要求：
{scope_execution_rules}

禁止事项：
{_fmt_list(forbidden)}

重试预算：
- max_attempts: `{retry_max}`
- attempted: `{retry_attempted}`
- escalation: `{retry_escalation or 'n/a'}`

修复完成后，请执行复核命令：
`{verification_command}`

并返回：
1. 你具体改了什么（按元素/区域说明）
2. 复核命令结果摘要
3. 若仍失败，下一步最小修复建议
"""
    return prompt


def generate_repair_prompt(project_dir: Path, slide_id: int | None = None, action_id: int | None = None) -> str:
    project_cli = _project_cli_path(project_dir)
    payload = _load_repair_plan(project_dir)
    items = _normalize_items(payload)
    blocking_items = [item for item in items if bool(item.get("is_blocking"))]
    selected = _pick_actionable_items(items, slide_id=slide_id, action_id=action_id)

    if not items:
        raise RepairPromptSelectionError(
            "repair_plan has no items.\n"
            f"next_step: run `python scripts/qa_project.py {project_cli} --snapshots` to generate actionable items."
        )
    if not blocking_items:
        raise RepairPromptSelectionError(
            "repair_plan has no blocking actionable items.\n"
            f"available_items:\n{_available_summary(items, blocking_only=False)}\n"
            + (
                "next_step: run "
                f"`python scripts/qa_project.py {project_cli} --snapshots "
                "--enable-visual-qa --quality-mode release-safe --profile "
                "proposal_consulting`."
            )
        )
    if not selected:
        reason = "no blocking item matched"
        if action_id is not None:
            reason += f" action_id={action_id}"
        if slide_id is not None:
            reason += f" slide={slide_id}"
        raise RepairPromptSelectionError(
            f"{reason}\n"
            f"available_blocking_items:\n{_available_summary(blocking_items, blocking_only=False)}\n"
            + (
                "next_step: choose one `action_id` above or rerun "
                f"`python scripts/qa_project.py {project_cli} --snapshots`."
            )
        )
    return _render_prompt(project_dir, selected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate copyable Executor repair prompt from qa/repair_plan.json")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>")
    parser.add_argument("--slide", type=int, help="Filter blocking item by slide id")
    parser.add_argument("--action-id", type=int, help="Select specific blocking action id")
    parser.add_argument("--output", type=Path, help="Optional output file path")
    args = parser.parse_args(argv)

    project_dir = args.project_dir.resolve()
    try:
        prompt = generate_repair_prompt(project_dir, slide_id=args.slide, action_id=args.action_id)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(prompt, encoding="utf-8")
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
