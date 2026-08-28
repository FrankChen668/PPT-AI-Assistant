#!/usr/bin/env python3
"""Generate an initial slide_plan.json from blueprint.json.

This is a planning helper only:
- It does not generate SVG.
- It does not replace Executor decisions.
- It records page semantics for every slide.
- It provides copyfit/layout budget hints for dense slides.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from copyfit_contract import is_dense_slide
from design_spec_tokens import split_design_spec_lines
from profile_policy import resolve_profile_policy

PRIORITIES = {"must", "should", "can"}
COMPRESS_RULES = {"shorten", "drop_secondary", "split"}
PAGE_TYPES = {
    "cover",
    "agenda",
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
    "closing",
}

PAGE_TYPE_BY_LAYOUT = {
    "Cover-Center": "cover",
    "TOC-Numbered-Bands": "agenda",
    "Statement-Bold": "statement",
    "Section-Divider": "statement",
    "Before-After": "comparison",
    "Pros-Cons": "comparison",
    "Two-Columns-Split": "comparison",
    "Comparison-Matrix-SummaryBar": "comparison",
    "Flow-Steps": "process",
    "Process-LeftCards-CenterFlow": "process",
    "Architecture-Three-Zones": "architecture",
    "Capability-Mapping": "capability-map",
    "Strategy-Map": "capability-map",
    "Roadmap-MultiPhase": "roadmap",
    "Roadmap-Lane-Milestones": "roadmap",
    "Timeline-Horizontal": "roadmap",
    "Timeline-Vertical": "roadmap",
    "Stage-Objectives-Deliverables": "roadmap",
    "Case-Study-Evidence": "case-study",
    "Data-Single-KPI": "kpi",
    "Data-Three-KPIs": "kpi",
    "Chart-Bar": "kpi",
    "Chart-Line": "kpi",
    "End-Page": "closing",
}

VISUAL_ARCHETYPE_BY_PAGE_TYPE = {
    "cover": "headline-hero",
    "agenda": "numbered-agenda",
    "background": "pressure-evidence-implication",
    "statement": "conclusion-evidence",
    "problem-analysis": "problem-cause-impact",
    "comparison": "two-sided-comparison",
    "process": "step-flow",
    "architecture": "layered-architecture",
    "capability-map": "capability-domains",
    "roadmap": "phased-roadmap",
    "case-study": "context-action-evidence",
    "kpi": "metric-driver-implication",
    "risk": "risk-control-matrix",
    "summary": "conclusion-priorities",
    "closing": "closing-statement",
}

NARRATIVE_ROLE_BY_PAGE_TYPE = {
    "cover": "建立主题",
    "agenda": "说明叙事路径",
    "background": "交代背景与压力",
    "statement": "核心判断",
    "problem-analysis": "拆解问题",
    "comparison": "明确差异",
    "process": "说明业务闭环",
    "architecture": "说明能力关系",
    "capability-map": "界定能力范围",
    "roadmap": "安排实施节奏",
    "case-study": "提供实践证据",
    "kpi": "突出关键指标",
    "risk": "说明风险与控制",
    "summary": "收束行动建议",
    "closing": "结束与行动号召",
}


@dataclass
class SlidePlanStats:
    slides_total: int
    slides_selected: int
    slides_planned: int
    blocks_total: int


@dataclass
class BudgetReport:
    profile: str
    checked_slides: int
    overloaded_slides: list[int]
    report_path: Path


def _load_blueprint(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "blueprint.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing blueprint.json: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid blueprint.json: {exc}") from exc


def _read_design_spec_values(project_dir: Path) -> dict[str, str]:
    path = project_dir / "design_spec.md"
    if not path.exists():
        return {}
    return split_design_spec_lines(path.read_text(encoding="utf-8-sig"))


def _body_font_budget(project_dir: Path) -> tuple[int, int] | None:
    values = _read_design_spec_values(project_dir)
    ladder = values.get("font_ladder") or values.get("typography_ladder") or ""
    match = re.search(r"\bbody\b\s*([0-9]+(?:\.[0-9]+)?)\s*/", ladder, flags=re.IGNORECASE)
    if not match:
        return None
    body_size = float(match.group(1))
    low = max(10, math.floor(body_size - 1.0))
    high = max(low + 2, math.ceil(body_size + 5.5))
    return low, high


def _collect_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_collect_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_collect_text(v) for v in value)
    return ""


def infer_page_type(slide: dict[str, Any]) -> str:
    explicit = str(slide.get("page_type") or "").strip().lower().replace("_", "-")
    if explicit in PAGE_TYPES:
        return explicit
    layout_tag = str(slide.get("layout_tag") or "").strip()
    if layout_tag in PAGE_TYPE_BY_LAYOUT:
        return PAGE_TYPE_BY_LAYOUT[layout_tag]
    if layout_tag.startswith("Grid-"):
        return "capability-map"
    direct_text = " ".join(
        (
            str(slide.get("title") or ""),
            str(slide.get("narrative_intent") or ""),
        )
    ).lower()
    keyword_groups = (
        ("agenda", ("目录", "议程", "agenda")),
        ("roadmap", ("路线", "阶段", "里程碑", "roadmap", "timeline")),
        ("architecture", ("架构", "层级", "模块关系", "architecture")),
        ("process", ("流程", "步骤", "闭环", "process", "workflow")),
        ("comparison", ("对比", "差异", "现状与目标", "comparison")),
        ("problem-analysis", ("问题", "痛点", "原因", "挑战", "problem")),
        ("capability-map", ("能力", "范围", "capability")),
        ("case-study", ("案例", "实践", "case study")),
        ("kpi", ("kpi", "指标", "关键数字")),
        ("risk", ("风险", "控制", "risk")),
        ("summary", ("总结", "建议", "summary")),
        ("background", ("背景", "压力", "趋势", "background")),
    )
    for page_type, keywords in keyword_groups:
        if any(keyword in direct_text for keyword in keywords):
            return page_type
    content_text = _collect_text(slide.get("content")).lower()
    for page_type, keywords in keyword_groups:
        if (
            layout_tag in {"Content-List-Left", "Content-List-Right"}
            and page_type in {"process", "roadmap"}
        ):
            continue
        if any(keyword in content_text for keyword in keywords):
            return page_type
    return "statement"


def _normalize_semantic_text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _normalized_semantic_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _normalize_semantic_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _semantic_conclusion(slide: dict[str, Any]) -> tuple[str, str, str]:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    claims = _normalized_semantic_list(slide.get("claims"))
    if claims:
        return claims[0], "claims", "high"
    explicit = _normalize_semantic_text(slide.get("conclusion"))
    if explicit:
        return explicit, "explicit", "high"
    for key in ("conclusion", "takeaway", "statement", "summary", "headline"):
        value = _normalize_semantic_text(content.get(key))
        if value:
            return value, "content", "medium"
    if "conclusion" not in slide:
        title = _normalize_semantic_text(slide.get("title"))
        if title and infer_page_type(slide) not in {"cover", "agenda", "closing"}:
            return title, "title-fallback", "low"
    return "", "missing", "none"


def _semantic_evidence(slide: dict[str, Any]) -> list[str]:
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    values: list[Any] = []
    if isinstance(slide.get("evidence"), list):
        values.extend(slide["evidence"])
    for key in ("evidence", "facts", "supporting_points"):
        if isinstance(content.get(key), list):
            values.extend(content[key])
    for key in ("support", "explanation", "body"):
        if isinstance(content.get(key), str):
            values.append(content[key])
    evidence: list[str] = []
    for value in values:
        fragments = _collect_text_fragments(value)
        text = "；".join(fragment for fragment in fragments if fragment)
        if text and text not in evidence:
            evidence.append(text[:180])
        if len(evidence) >= 4:
            break
    return evidence


def _semantic_content_blocks(slide: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = slide.get("content_blocks")
    if isinstance(explicit, list):
        return [dict(item) for item in explicit if isinstance(item, dict)]
    content = slide.get("content") if isinstance(slide.get("content"), dict) else {}
    ignored = {"title", "headline", "subtitle", "conclusion", "takeaway", "statement", "support", "explanation"}
    blocks: list[dict[str, Any]] = []
    for key, value in content.items():
        if key in ignored or value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            for index, item in enumerate(value, start=1):
                text = " ".join(_collect_text(item).split())
                if text:
                    blocks.append({"role": f"{key}-{index}", "type": key.rstrip("s") or "content", "text": text[:180]})
        else:
            text = " ".join(_collect_text(value).split())
            if text:
                blocks.append({"role": key, "type": "fact", "text": text[:180]})
    return blocks


def build_semantic_plan_row(slide: dict[str, Any]) -> dict[str, Any]:
    page_type = infer_page_type(slide)
    conclusion, conclusion_source, conclusion_confidence = _semantic_conclusion(slide)
    claims = _normalized_semantic_list(slide.get("claims"))
    content_blocks = _semantic_content_blocks(slide)
    text_length = len(_collect_text(slide.get("content")))
    if len(content_blocks) >= 6 or text_length >= 520:
        density_level = "high"
    elif len(content_blocks) >= 3 or text_length >= 240:
        density_level = "medium"
    else:
        density_level = "low"
    page_intent = str(slide.get("page_intent") or slide.get("narrative_intent") or "").strip()
    if not page_intent:
        page_intent = f"通过{NARRATIVE_ROLE_BY_PAGE_TYPE[page_type]}推动整套材料的业务叙事"
    editable_priority = slide.get("editable_priority")
    if not isinstance(editable_priority, list) or not editable_priority:
        editable_priority = ["title", "conclusion", "evidence"]
        if page_type == "kpi":
            editable_priority.append("key-metric")
    return {
        "page_type": page_type,
        "narrative_role": str(slide.get("narrative_role") or NARRATIVE_ROLE_BY_PAGE_TYPE[page_type]),
        "page_intent": page_intent,
        "conclusion": conclusion,
        "conclusion_source": conclusion_source,
        "conclusion_confidence": conclusion_confidence,
        "supporting_claims": claims[1:],
        "evidence": _semantic_evidence(slide),
        "source_refs": _normalized_semantic_list(slide.get("source_refs")),
        "visual_intent": _normalize_semantic_text(slide.get("visual_intent")),
        "acceptance_criteria": _normalized_semantic_list(slide.get("acceptance_criteria")),
        "content_blocks": content_blocks,
        "visual_archetype": str(
            slide.get("visual_archetype") or VISUAL_ARCHETYPE_BY_PAGE_TYPE[page_type]
        ).strip(),
        "density_level": str(slide.get("density_level") or density_level).strip().lower(),
        "editable_priority": [str(item).strip() for item in editable_priority if str(item).strip()],
    }


def _collect_text_fragments(value: Any) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        dict_output: list[str] = []
        for item in value.values():
            dict_output.extend(_collect_text_fragments(item))
        return dict_output
    if isinstance(value, list):
        list_output: list[str] = []
        for item in value:
            list_output.extend(_collect_text_fragments(item))
        return list_output
    return []


def _collect_lists(value: Any) -> list[list[Any]]:
    found: list[list[Any]] = []
    if isinstance(value, list):
        found.append(value)
        for item in value:
            found.extend(_collect_lists(item))
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_collect_lists(item))
    return found


def _primary_list_lengths(slide: dict[str, Any]) -> list[int]:
    content = slide.get("content", {})
    lists = _collect_lists(content)
    if not isinstance(content, dict):
        return [len(item) for item in lists]

    layout_tag = str(slide.get("layout_tag") or "")
    core_modules = content.get("core_modules")
    if (
        layout_tag == "Architecture-Three-Zones"
        and isinstance(core_modules, list)
        and len(core_modules) <= 6
    ):
        # Six architecture layers are a required structural group, not a
        # generic primary list that should be judged by the normal max=5 cap.
        lists = [item for item in lists if item is not core_modules]
    return [len(item) for item in lists]


def _dense_score(slide: dict[str, Any]) -> int:
    content = slide.get("content", {})
    text_len = len(_collect_text(content))
    list_weight = 0
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, list):
                list_weight += len(value) * 40
    return text_len + list_weight


def _layout_objective(slide: dict[str, Any]) -> str:
    tag = str(slide.get("layout_tag") or "")
    if tag.startswith("Data-") or tag.startswith("Chart-"):
        return "data_evidence_first"
    if "Roadmap" in tag or "Flow-" in tag:
        return "sequence_clarity_first"
    if "Grid-" in tag:
        return "parallel_comparison_balance"
    return "headline_claim_first"


def _dominance_map(slide: dict[str, Any]) -> dict[str, str]:
    if str(slide.get("scene_type") or "").strip() == "core_orbit_relationship":
        return {
            "primary": "core-node",
            "secondary": "satellite_nodes",
            "tertiary": "relationship_edges",
        }
    tag = str(slide.get("layout_tag") or "")
    if tag.startswith("Data-") or tag.startswith("Chart-"):
        return {
            "primary": "key_data_or_conclusion",
            "secondary": "supporting_explanation",
            "tertiary": "annotation_or_source",
        }
    return {
        "primary": "headline_or_core_claim",
        "secondary": "evidence_or_body",
        "tertiary": "notes_or_context",
    }


def _must_keep_claims(slide: dict[str, Any]) -> list[str]:
    content = slide.get("content")
    if not isinstance(content, dict):
        return []
    ordered_keys = ("statement", "headline", "title")
    collected: list[str] = []
    for key in ordered_keys:
        value = content.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split()).strip()
            if cleaned:
                collected.append(cleaned)
    if not collected:
        title = str(slide.get("title") or "").strip()
        if title:
            collected.append(" ".join(title.split()))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in collected:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item[:90])
        if len(deduped) >= 2:
            break
    return deduped


def _density_budget_from_blocks(blocks: list[dict[str, Any]]) -> dict[str, int]:
    if not blocks:
        return {"max_text_nodes": 0, "max_body_lines": 0, "max_chars": 0}
    max_text_nodes = len(blocks) * 3
    max_body_lines = sum(int(block.get("max_lines") or 0) for block in blocks)
    max_chars = sum(
        int(block.get("max_chars_per_line") or 0) * int(block.get("max_lines") or 0)
        for block in blocks
    )
    return {
        "max_text_nodes": max(1, max_text_nodes),
        "max_body_lines": max(1, max_body_lines),
        "max_chars": max(80, max_chars),
    }


def evaluate_budget_policy(project_dir: Path, profile: str = "presentation") -> BudgetReport:
    project_dir = project_dir.resolve()
    policy = resolve_profile_policy(profile)
    blueprint = _load_blueprint(project_dir)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain slides array.")

    overloaded: list[int] = []
    details: list[dict[str, Any]] = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        sid = slide.get("id")
        if not isinstance(sid, int):
            continue
        content = slide.get("content", {})
        text_blob = _collect_text(content)
        char_count = len(text_blob)
        max_list_items = max(_primary_list_lengths(slide), default=0)
        text_nodes_proxy = 0
        if isinstance(content, dict):
            text_nodes_proxy = sum(1 for value in content.values() if isinstance(value, (str, list, dict)))

        reasons: list[str] = []
        if char_count > policy.max_chars_per_slide:
            reasons.append(f"char_count={char_count}>{policy.max_chars_per_slide}")
        if text_nodes_proxy > policy.max_text_nodes_per_slide:
            reasons.append(
                f"text_nodes_proxy={text_nodes_proxy}>{policy.max_text_nodes_per_slide}"
            )
        if max_list_items > policy.max_items_per_primary_list:
            reasons.append(
                f"max_list_items={max_list_items}>{policy.max_items_per_primary_list}"
            )
        if reasons:
            overloaded.append(sid)
        details.append(
            {
                "slide_id": sid,
                "layout_tag": slide.get("layout_tag"),
                "char_count": char_count,
                "text_nodes_proxy": text_nodes_proxy,
                "max_list_items": max_list_items,
                "overloaded": bool(reasons),
                "reasons": reasons,
            }
        )

    report_dir = project_dir / "qa"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "overload-report.json"
    payload = {
        "profile": policy.key,
        "policy": {
            "max_chars_per_slide": policy.max_chars_per_slide,
            "max_text_nodes_per_slide": policy.max_text_nodes_per_slide,
            "max_items_per_primary_list": policy.max_items_per_primary_list,
        },
        "checked_slides": len(details),
        "overloaded_slides": overloaded,
        "slides": details,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return BudgetReport(
        profile=policy.key,
        checked_slides=len(details),
        overloaded_slides=overloaded,
        report_path=report_path,
    )


def _block(
    block_id: str,
    box: list[float],
    max_lines: int,
    max_chars: int,
    font_low: int,
    font_high: int,
    *,
    section: str,
    priority: str = "should",
    compress_rule: str = "shorten",
) -> dict[str, Any]:
    if priority not in PRIORITIES:
        priority = "should"
    if compress_rule not in COMPRESS_RULES:
        compress_rule = "shorten"
    return {
        "id": block_id,
        "name": block_id,  # backward compatibility for older tooling
        "box": box,
        "max_lines": max_lines,
        "max_chars_per_line": max_chars,
        "font_size_range": [font_low, font_high],
        "priority": priority,
        "compress_rule": compress_rule,
        "section": section,
    }


def _blocks_from_auto_slots(
    auto_slots: list[dict[str, Any]],
    *,
    font_budget: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    default_font = list(font_budget or (13, 20))
    blocks: list[dict[str, Any]] = []
    for index, slot in enumerate(auto_slots, start=1):
        font_range = slot.get("font_size_range") or default_font
        blocks.append(
            _block(
                str(slot.get("block_id") or f"auto-slot-{index}"),
                list(slot["box"]),
                int(slot.get("max_lines") or 4),
                int(slot.get("max_chars_per_line") or 24),
                int(font_range[0]),
                int(font_range[1]),
                section=str(slot.get("section") or slot.get("block_id") or "auto-slot"),
                priority=str(slot.get("priority") or "should"),
                compress_rule=str(slot.get("compress_rule") or "shorten"),
            )
        )
    return blocks


def _boxes_for_layout(slide: dict[str, Any], font_budget: tuple[int, int] | None = None) -> list[dict[str, Any]]:
    tag = str(slide.get("layout_tag", ""))
    content = slide.get("content", {})
    blocks: list[dict[str, Any]] = []
    if not is_dense_slide(slide):
        return blocks

    if tag == "Grid-Three-Cards":
        xs = [80, 455, 830]
        for idx, x in enumerate(xs, start=1):
            blocks.append(
            _block(
                f"card-{idx}",
                    [x, 230, 330, 330],
                    5,
                    24,
                    15,
                    24,
                    section=f"card-{idx}",
                    priority="should",
                    compress_rule="shorten",
                )
            )
        return blocks

    if tag == "Grid-Four-Cards":
        font_low, font_high = font_budget or (15, 24)
        coords = [(80, 165), (660, 165), (80, 400), (660, 400)]
        for idx, (x, y) in enumerate(coords, start=1):
            blocks.append(
            _block(
                f"card-{idx}",
                    [x, y, 540, 190],
                    8 if font_budget else 4,
                    42 if font_budget else 24,
                    font_low,
                    font_high,
                    section=f"card-{idx}",
                    priority="should",
                    compress_rule="shorten",
                )
            )
        return blocks

    if tag == "Grid-Six-Icons":
        xs = [90, 455, 820]
        ys = [185, 410]
        idx = 1
        for y in ys:
            for x in xs:
                blocks.append(
                    _block(
                        f"item-{idx}",
                        [x, y, 300, 150],
                        3,
                        20,
                        14,
                        22,
                        section=f"card-{idx}",
                        priority="can",
                        compress_rule="drop_secondary",
                    )
                )
                idx += 1
        return blocks

    if tag == "Flow-Steps":
        steps = content.get("steps") if isinstance(content, dict) else None
        count = len(steps) if isinstance(steps, list) else 4
        count = max(3, min(5, count))
        if count == 3:
            xs = [140, 500, 860]
            w = 280
        elif count == 4:
            xs = [90, 350, 610, 870]
            w = 220
        else:
            xs = [80, 316, 552, 788, 1024]
            w = 176
        for idx, x in enumerate(xs, start=1):
            blocks.append(
                _block(
                    f"step-{idx}",
                    [x, 250, w, 210],
                    4,
                    20,
                    14,
                    22,
                    section="bottom",
                    priority="must",
                    compress_rule="split",
                )
            )
        return blocks

    if tag == "Content-List-Left":
        return [
            _block(
                "items-column",
                [560, 150, 600, 460],
                7,
                28,
                15,
                24,
                section="bottom",
                priority="must",
                compress_rule="shorten",
            )
        ]

    if tag == "Content-List-Right":
        return [
            _block(
                "items-column",
                [90, 150, 600, 460],
                7,
                28,
                15,
                24,
                section="bottom",
                priority="must",
                compress_rule="shorten",
            )
        ]

    if tag in {"Two-Columns-Split", "Before-After", "Pros-Cons"}:
        return [
            _block(
                "left-panel",
                [80, 180, 520, 420],
                7,
                24,
                15,
                24,
                section="left",
                priority="should",
                compress_rule="shorten",
            ),
            _block(
                "right-panel",
                [680, 180, 520, 420],
                7,
                24,
                15,
                24,
                section="right",
                priority="must",
                compress_rule="split",
            ),
        ]

    if tag == "Capability-Mapping":
        return [
            _block(
                "left-column",
                [80, 170, 368, 404],
                14,
                24,
                13,
                20,
                section="left",
                priority="should",
                compress_rule="shorten",
            ),
            _block(
                "middle-column",
                [484, 170, 374, 404],
                13,
                24,
                13,
                19,
                section="middle",
                priority="should",
                compress_rule="shorten",
            ),
            _block(
                "right-column",
                [886, 170, 322, 404],
                12,
                20,
                12,
                18,
                section="right",
                priority="must",
                compress_rule="split",
            ),
        ]

    score = _dense_score(slide)
    if score >= 420:
        return [
            _block(
                "main-content",
                [80, 170, 1120, 470],
                10,
                60,
                14,
                22,
                section="bottom",
                priority="must",
                compress_rule="shorten",
            )
        ]

    return [
        _block(
            "dense-content",
            [80, 170, 1120, 470],
            9,
            54,
            13,
            20,
            section="content",
            priority="must",
            compress_rule="shorten",
        )
    ]


def _build_plan_payload(
    slides: list[dict[str, Any]],
    selected_slide_id: int | None = None,
    font_budget: tuple[int, int] | None = None,
) -> tuple[dict[str, Any], SlidePlanStats]:
    plan_slides: list[dict[str, Any]] = []
    selected = 0
    planned = 0
    blocks_total = 0

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        sid = slide.get("id")
        if not isinstance(sid, int):
            continue
        if selected_slide_id is not None and sid != selected_slide_id:
            continue
        selected += 1
        blocks = _boxes_for_layout(slide, font_budget=font_budget)
        explicit_scene = str(slide.get("scene_type") or "").strip()
        if explicit_scene == "core_orbit_relationship":
            from pipeline.layout_slot_generator import generate_auto_slots

            auto_slots = generate_auto_slots(slide)
            blocks = _blocks_from_auto_slots(auto_slots, font_budget=font_budget)
            logging.info("auto_slot required for %s, generated %s slots", explicit_scene, len(auto_slots))
        if os.environ.get("ENABLE_AUTO_SLOT") == "1":
            scene = str(slide.get("scene_type") or {"Architecture-Three-Zones": "architecture_flow", "Roadmap-Lane-Milestones": "roadmap", "Comparison-Matrix-SummaryBar": "comparison"}.get(str(slide.get("layout_tag") or ""), ""))
            if scene in {"architecture_flow", "roadmap", "comparison"} and explicit_scene != "core_orbit_relationship":
                try:
                    from pipeline.layout_slot_generator import generate_auto_slots
                    auto_slots = generate_auto_slots({**slide, "scene_type": scene})
                    blocks = _blocks_from_auto_slots(auto_slots, font_budget=font_budget)
                    logging.info("auto_slot enabled for %s, generated %s slots", scene, len(auto_slots))
                except Exception as exc:
                    logging.warning("auto_slot failed for slide %s: %s, fallback to default boxes", slide.get("id"), exc)
        if blocks:
            planned += 1
            blocks_total += len(blocks)
        plan_slides.append(
            {
                "slide_id": sid,
                "id": sid,
                "blocks": blocks,
                "layout_objective": (
                    "单一核心 + 对称环绕支撑"
                    if explicit_scene == "core_orbit_relationship"
                    else _layout_objective(slide)
                ),
                "density_budget": _density_budget_from_blocks(blocks),
                "dominance_map": _dominance_map(slide),
                "must_keep_claims": _must_keep_claims(slide),
                **build_semantic_plan_row(slide),
            }
        )

    payload: dict[str, Any] = {
        "version": 2,
        "generated_by": "auto-slide-plan",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "slides": plan_slides,
    }
    stats = SlidePlanStats(
        slides_total=len(slides),
        slides_selected=selected,
        slides_planned=planned,
        blocks_total=blocks_total,
    )
    return payload, stats


def ensure_semantic_slide_plan(project_dir: Path) -> SlidePlanStats:
    """Fill semantic fields while preserving existing authored block geometry."""
    project_dir = project_dir.resolve()
    blueprint = _load_blueprint(project_dir)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain slides array.")
    generated, stats = _build_plan_payload(slides, font_budget=_body_font_budget(project_dir))
    target = project_dir / "slide_plan.json"
    if not target.exists():
        target.write_text(json.dumps(generated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return stats

    try:
        existing = json.loads(target.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ValueError(f"Invalid slide_plan.json: {exc}") from exc
    if not isinstance(existing, dict):
        raise ValueError("slide_plan.json root must be an object.")
    existing_slides = existing.get("slides")
    if not isinstance(existing_slides, list):
        existing_slides = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in existing_slides:
        if not isinstance(row, dict):
            continue
        raw_id = row.get("slide_id", row.get("id"))
        try:
            by_id[int(raw_id)] = dict(row)
        except (TypeError, ValueError):
            continue

    merged: list[dict[str, Any]] = []
    for generated_row in generated["slides"]:
        sid = int(generated_row["slide_id"])
        current = by_id.get(sid, {})
        row = dict(generated_row)
        row.update(current)
        semantic = {key: value for key, value in generated_row.items() if key in {
            "page_type",
            "narrative_role",
            "page_intent",
            "conclusion",
            "conclusion_source",
            "conclusion_confidence",
            "supporting_claims",
            "evidence",
            "source_refs",
            "visual_intent",
            "acceptance_criteria",
            "content_blocks",
            "visual_archetype",
            "density_level",
            "editable_priority",
        }}
        for key, value in semantic.items():
            if key not in current or current.get(key) in (None, "", []):
                row[key] = value
        row["slide_id"] = sid
        row["id"] = sid
        merged.append(row)

    existing.update(
        {
            "version": max(2, int(existing.get("version") or 1)),
            "generated_by": str(existing.get("generated_by") or "auto-slide-plan"),
            "semantic_fields_updated_at": datetime.now().isoformat(timespec="seconds"),
            "slides": merged,
        }
    )
    target.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


def generate_slide_plan(
    project_dir: Path,
    overwrite: bool = False,
    slide_id: int | None = None,
    dry_run: bool = False,
) -> SlidePlanStats:
    project_dir = project_dir.resolve()
    blueprint = _load_blueprint(project_dir)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain slides array.")

    payload, stats = _build_plan_payload(slides, selected_slide_id=slide_id, font_budget=_body_font_budget(project_dir))
    target = project_dir / "slide_plan.json"
    if target.exists() and not overwrite and not dry_run:
        return stats
    if not dry_run:
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate slide_plan.json draft from blueprint.json.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--slide", type=int, help="Generate plan for one slide id.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing slide_plan.json.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing file.")
    args = parser.parse_args(argv)

    try:
        stats = generate_slide_plan(
            args.project_dir,
            overwrite=args.overwrite,
            slide_id=args.slide,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return 1

    print(
        "Auto slide plan done: "
        f"slides_total={stats.slides_total}, "
        f"slides_selected={stats.slides_selected}, "
        f"slides_planned={stats.slides_planned}, "
        f"blocks_total={stats.blocks_total}"
    )
    if not args.dry_run:
        print(Path(args.project_dir).resolve() / "slide_plan.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
