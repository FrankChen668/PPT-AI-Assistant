#!/usr/bin/env python3
"""Validate business-slide semantic planning before rendering and export."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_CONTENT_BLOCKS_HARD = 6
MAX_CARD_GRID_RATIO = 0.40
MAX_CONSECUTIVE_ARCHETYPE = 2
MIN_EVIDENCE_ITEMS = 2

CONCLUSION_REQUIRED_PAGE_TYPES = {
    "background",
    "statement",
    "problem-analysis",
    "comparison",
    "process",
    "architecture",
    "capability-map",
    "roadmap",
    "case-study",
    "kpi",
    "risk",
    "summary",
}

GENERIC_CONCLUSIONS = {
    "持续优化",
    "稳步推进",
    "分步实施",
    "提升能力",
    "加强管理",
    "实现目标",
    "总结",
    "结论",
    "continuous improvement",
    "move forward",
}

TOPIC_CLUSTERS = {
    "process": {"流程", "步骤", "闭环", "任务", "填报", "整改", "workflow", "process"},
    "architecture": {"架构", "层级", "模块", "平台", "数据流", "architecture", "module"},
    "roadmap": {"路线", "阶段", "试点", "扩展", "里程碑", "roadmap", "timeline"},
    "risk": {"风险", "控制", "合规", "审计", "risk", "control"},
    "people": {"员工", "团建", "招聘", "培训", "team", "hiring"},
    "finance": {"预算", "收入", "成本", "利润", "finance", "revenue"},
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Missing planning input: {path}") from exc
    except Exception as exc:
        raise ValueError(f"Invalid JSON at {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def _normalize(value: object) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values()).strip()
    if isinstance(value, list):
        return " ".join(_text(item) for item in value).strip()
    return ""


def _nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return value is not None


def _finding(
    code: str,
    message: str,
    *,
    slide_id: int | None = None,
    hard_blocker: bool,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "severity": "error" if hard_blocker else "warning",
        "code": code,
        "message": message,
        "hard_blocker": hard_blocker,
        "is_blocking": hard_blocker,
    }
    if slide_id is not None:
        item["slide_id"] = slide_id
    if context:
        item["context"] = context
    return item


def _topic_clusters(text: str) -> set[str]:
    normalized = text.lower()
    return {
        cluster
        for cluster, keywords in TOPIC_CLUSTERS.items()
        if any(keyword in normalized for keyword in keywords)
    }


def _title_and_body_are_clearly_unrelated(title: str, body: str) -> bool:
    title_clusters = _topic_clusters(title)
    body_clusters = _topic_clusters(body)
    return bool(title_clusters and body_clusters and title_clusters.isdisjoint(body_clusters))


def _valid_comparison(content: dict[str, Any]) -> bool:
    direct_pairs = (("left", "right"), ("before", "after"), ("current", "target"), ("pros", "cons"))
    if any(_nonempty(content.get(left)) and _nonempty(content.get(right)) for left, right in direct_pairs):
        return True
    rows = content.get("rows")
    if isinstance(rows, list) and rows:
        return all(
            isinstance(row, dict)
            and _nonempty(row.get("left", row.get("current")))
            and _nonempty(row.get("right", row.get("target")))
            for row in rows
        )
    return False


def _valid_process(content: dict[str, Any]) -> bool:
    steps = content.get("steps") or content.get("process") or content.get("stages")
    return isinstance(steps, list) and len([item for item in steps if _nonempty(item)]) >= 2


def _valid_roadmap(content: dict[str, Any]) -> bool:
    phases = content.get("phases") or content.get("stages") or content.get("milestones")
    return isinstance(phases, list) and len([item for item in phases if _nonempty(item)]) >= 2


def _valid_architecture(content: dict[str, Any]) -> bool:
    for key in ("layers", "modules", "zones", "core_modules", "domains"):
        value = content.get(key)
        if isinstance(value, list) and len([item for item in value if _nonempty(item)]) >= 2:
            return True
    relationships = content.get("relationships") or content.get("data_flows")
    return isinstance(relationships, list) and len(relationships) >= 1


def _duplicate_occurrences(values: list[tuple[int, str]]) -> tuple[int, dict[str, list[int]]]:
    by_value: dict[str, list[int]] = {}
    for slide_id, value in values:
        normalized = _normalize(value)
        if normalized:
            by_value.setdefault(normalized, []).append(slide_id)
    duplicates = {value: ids for value, ids in by_value.items() if len(ids) > 1}
    return sum(len(ids) - 1 for ids in duplicates.values()), duplicates


def _consecutive_archetype_runs(rows: list[dict[str, Any]]) -> list[tuple[str, list[int]]]:
    runs: list[tuple[str, list[int]]] = []
    active_archetype = ""
    active_ids: list[int] = []
    for row in rows:
        archetype = str(row.get("visual_archetype") or "").strip()
        slide_id = int(row.get("slide_id") or row.get("id") or 0)
        if archetype and archetype == active_archetype:
            active_ids.append(slide_id)
            continue
        if active_archetype and len(active_ids) > MAX_CONSECUTIVE_ARCHETYPE:
            runs.append((active_archetype, active_ids))
        active_archetype = archetype
        active_ids = [slide_id] if archetype else []
    if active_archetype and len(active_ids) > MAX_CONSECUTIVE_ARCHETYPE:
        runs.append((active_archetype, active_ids))
    return runs


def evaluate_planning_quality(
    project_dir: Path,
    *,
    overloaded_slide_ids: list[int] | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    blueprint = _read_json(project_dir / "blueprint.json")
    slide_plan = _read_json(project_dir / "slide_plan.json")
    blueprint_slides = [item for item in blueprint.get("slides", []) if isinstance(item, dict)]
    plan_rows = [item for item in slide_plan.get("slides", []) if isinstance(item, dict)]
    blueprint_by_id = {
        int(item["id"]): item
        for item in blueprint_slides
        if isinstance(item.get("id"), int)
    }
    plan_by_id = {
        int(item.get("slide_id", item.get("id"))): item
        for item in plan_rows
        if isinstance(item.get("slide_id", item.get("id")), int)
    }

    hard_blockers: list[dict[str, Any]] = []
    quality_notes: list[dict[str, Any]] = []
    blueprint_ids = set(blueprint_by_id)
    plan_ids = set(plan_by_id)
    if blueprint_ids != plan_ids:
        hard_blockers.append(
            _finding(
                "planning-slide-count-mismatch",
                "Blueprint pages and semantic planning pages do not match.",
                hard_blocker=True,
                context={
                    "blueprint_slide_ids": sorted(blueprint_ids),
                    "planned_slide_ids": sorted(plan_ids),
                },
            )
        )

    overloaded = set(overloaded_slide_ids or [])
    overloaded_from_blocks: set[int] = set()
    slide_details: list[dict[str, Any]] = []
    ordered_rows = [plan_by_id[slide_id] for slide_id in sorted(plan_ids)]
    for row in ordered_rows:
        slide_id = int(row.get("slide_id") or row.get("id") or 0)
        slide = blueprint_by_id.get(slide_id, {})
        page_type = str(row.get("page_type") or "").strip()
        title = str(slide.get("title") or "").strip()
        conclusion = str(row.get("conclusion") or "").strip()
        evidence = (
            [item for item in row.get("evidence", []) if _nonempty(item)]
            if isinstance(row.get("evidence"), list)
            else []
        )
        content_blocks = (
            [item for item in row.get("content_blocks", []) if isinstance(item, dict)]
            if isinstance(row.get("content_blocks"), list)
            else []
        )
        content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
        body_text = " ".join((conclusion, _text(content), _text(evidence), _text(content_blocks))).strip()

        if not title and not body_text:
            hard_blockers.append(
                _finding(
                    "planning-empty-page",
                    "Page has no title or core content.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if _title_and_body_are_clearly_unrelated(title, body_text):
            hard_blockers.append(
                _finding(
                    "planning-title-content-unrelated",
                    "Page title and body belong to clearly different business topics.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if page_type in CONCLUSION_REQUIRED_PAGE_TYPES and not conclusion:
            hard_blockers.append(
                _finding(
                    "planning-missing-conclusion",
                    f"{page_type or 'business'} page has no explicit core conclusion.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if page_type == "comparison" and not _valid_comparison(content):
            hard_blockers.append(
                _finding(
                    "planning-invalid-comparison",
                    "Comparison page must contain two complete sides.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if page_type == "process" and not _valid_process(content):
            hard_blockers.append(
                _finding(
                    "planning-invalid-process",
                    "Process page must contain at least two valid steps.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if page_type == "roadmap" and not _valid_roadmap(content):
            hard_blockers.append(
                _finding(
                    "planning-invalid-roadmap",
                    "Roadmap page must contain at least two ordered phases or milestones.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if page_type == "architecture" and not _valid_architecture(content):
            hard_blockers.append(
                _finding(
                    "planning-invalid-architecture",
                    "Architecture page must contain layers, modules, or explicit relationships.",
                    slide_id=slide_id,
                    hard_blocker=True,
                )
            )
        if len(content_blocks) > MAX_CONTENT_BLOCKS_HARD:
            overloaded_from_blocks.add(slide_id)
        if page_type in CONCLUSION_REQUIRED_PAGE_TYPES and len(evidence) < MIN_EVIDENCE_ITEMS:
            quality_notes.append(
                _finding(
                    "planning-weak-evidence",
                    "Page has fewer than two supporting evidence items.",
                    slide_id=slide_id,
                    hard_blocker=False,
                )
            )
        if conclusion and (
            _normalize(conclusion) in {_normalize(item) for item in GENERIC_CONCLUSIONS}
            or len(_normalize(conclusion)) < 6
        ):
            quality_notes.append(
                _finding(
                    "planning-generic-conclusion",
                    "Core conclusion is too generic to guide a business decision.",
                    slide_id=slide_id,
                    hard_blocker=False,
                )
            )
        slide_details.append(
            {
                "slide_id": slide_id,
                "title": title,
                "page_type": page_type,
                "narrative_role": str(row.get("narrative_role") or ""),
                "page_intent": str(row.get("page_intent") or ""),
                "conclusion": conclusion,
                "evidence_count": len(evidence),
                "content_block_count": len(content_blocks),
                "visual_archetype": str(row.get("visual_archetype") or ""),
                "density_level": str(row.get("density_level") or ""),
            }
        )

    overloaded.update(overloaded_from_blocks)
    for slide_id in sorted(overloaded):
        hard_blockers.append(
            _finding(
                "planning-content-overload",
                f"Page exceeds the planning content budget of {MAX_CONTENT_BLOCKS_HARD} major blocks.",
                slide_id=slide_id,
                hard_blocker=True,
            )
        )

    title_count, duplicate_titles = _duplicate_occurrences(
        [(int(item.get("id") or 0), str(item.get("title") or "")) for item in blueprint_slides]
    )
    conclusion_count, duplicate_conclusions = _duplicate_occurrences(
        [(int(row.get("slide_id") or 0), str(row.get("conclusion") or "")) for row in ordered_rows]
    )
    content_block_values: list[tuple[int, str]] = []
    for row in ordered_rows:
        slide_id = int(row.get("slide_id") or 0)
        blocks = row.get("content_blocks") if isinstance(row.get("content_blocks"), list) else []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_text = str(block.get("text") or block.get("content") or "").strip()
            if block_text:
                content_block_values.append((slide_id, block_text))
    repeated_block_count, duplicate_blocks = _duplicate_occurrences(content_block_values)
    if title_count:
        quality_notes.append(
            _finding(
                "planning-repeated-title",
                "The same page title appears on multiple pages.",
                hard_blocker=False,
                context={"duplicate_groups": list(duplicate_titles.values())},
            )
        )
    if conclusion_count:
        quality_notes.append(
            _finding(
                "planning-repeated-conclusion",
                "The same core conclusion appears on multiple pages.",
                hard_blocker=False,
                context={"duplicate_groups": list(duplicate_conclusions.values())},
            )
        )
    if repeated_block_count:
        quality_notes.append(
            _finding(
                "planning-repeated-content-block",
                "The same content block is repeated verbatim on multiple pages.",
                hard_blocker=False,
                context={"duplicate_groups": list(duplicate_blocks.values())},
            )
        )

    for detail in slide_details:
        if detail["slide_id"] in overloaded:
            continue
        if detail["density_level"] == "high" or detail["content_block_count"] >= 5:
            quality_notes.append(
                _finding(
                    "planning-density-high",
                    "Page density is high but remains below the hard planning limit.",
                    slide_id=detail["slide_id"],
                    hard_blocker=False,
                )
            )

    repeated_intent_count, duplicate_intents = _duplicate_occurrences(
        [(int(row.get("slide_id") or 0), str(row.get("page_intent") or "")) for row in ordered_rows]
    )
    if repeated_intent_count:
        quality_notes.append(
            _finding(
                "planning-weak-transition",
                "Multiple pages use the same page intent, weakening narrative progression.",
                hard_blocker=False,
                context={"duplicate_groups": list(duplicate_intents.values())},
            )
        )

    repeated_runs = _consecutive_archetype_runs(ordered_rows)
    for archetype, slide_ids in repeated_runs:
        quality_notes.append(
            _finding(
                "planning-repeated-archetype",
                "The same visual structure appears on more than two consecutive pages.",
                hard_blocker=False,
                context={"visual_archetype": archetype, "slide_ids": slide_ids},
            )
        )

    card_slide_ids = [
        int(row.get("slide_id") or 0)
        for row in ordered_rows
        if "card" in str(row.get("visual_archetype") or "").lower()
        or str(blueprint_by_id.get(int(row.get("slide_id") or 0), {}).get("layout_tag") or "").startswith("Grid-")
    ]
    card_ratio = len(card_slide_ids) / len(ordered_rows) if ordered_rows else 0.0
    if card_ratio > MAX_CARD_GRID_RATIO:
        quality_notes.append(
            _finding(
                "planning-card-grid-ratio-high",
                "Card-grid pages exceed the recommended deck ratio.",
                hard_blocker=False,
                context={"ratio": round(card_ratio, 4), "slide_ids": card_slide_ids},
            )
        )

    page_type_distribution = dict(
        sorted(Counter(item["page_type"] for item in slide_details if item["page_type"]).items())
    )
    archetype_distribution = dict(
        sorted(Counter(item["visual_archetype"] for item in slide_details if item["visual_archetype"]).items())
    )
    status = "blocked" if hard_blockers else "downloadable_with_notes" if quality_notes else "approved"
    warnings = [item for item in quality_notes if item.get("severity") == "warning"]
    summary = {
        "slide_count": len(blueprint_slides),
        "planned_slide_count": len(plan_rows),
        "planning_error_count": len(hard_blockers),
        "planning_warning_count": len(warnings),
        "planning_note_count": len(quality_notes),
        "slide_type_distribution": page_type_distribution,
        "visual_archetype_distribution": archetype_distribution,
        "repeated_title_count": title_count,
        "repeated_conclusion_count": conclusion_count,
        "repeated_content_block_count": repeated_block_count,
        "repeated_page_intent_count": repeated_intent_count,
        "repeated_archetype_run_count": len(repeated_runs),
        "card_grid_slide_count": len(card_slide_ids),
        "card_grid_ratio": round(card_ratio, 4),
        "content_overload_slide_count": len(overloaded),
    }
    report = {
        "version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "planning_status": status,
        "delivery_approved": status != "blocked",
        "manual_review_required": bool(quality_notes) and status != "blocked",
        "hard_blockers": hard_blockers,
        "warnings": warnings,
        "quality_notes": quality_notes,
        "summary": summary,
        "thresholds": {
            "max_content_blocks_hard": MAX_CONTENT_BLOCKS_HARD,
            "max_card_grid_ratio": MAX_CARD_GRID_RATIO,
            "max_consecutive_archetype": MAX_CONSECUTIVE_ARCHETYPE,
            "min_evidence_items": MIN_EVIDENCE_ITEMS,
        },
        "slides": slide_details,
    }
    if write_report:
        report_dir = project_dir / "qa"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "planning-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report
