#!/usr/bin/env python3
"""Canonical Layout DSL contracts for rendering, QA, and regression.

This module keeps layout metadata out of individual pipeline stages. The
renderer owns geometry, while contracts define the stable layout names, minimal
content requirements, and regression fixtures shared by QA.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

CORE_SLIDE_KEYS = frozenset({"id", "title", "layout_tag", "content"})


@dataclass(frozen=True)
class LayoutContract:
    tag: str
    family: str
    required_content: tuple[str, ...]
    sample_content: dict[str, Any]


def expected_content_skeleton(value: Any) -> Any:
    """Return a JSON-serializable skeleton mirroring sample content shapes."""
    if isinstance(value, dict):
        return {str(key): expected_content_skeleton(val) for key, val in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        return [expected_content_skeleton(value[0])]
    if isinstance(value, tuple):
        if not value:
            return []
        return [expected_content_skeleton(value[0])]
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return 0
    if isinstance(value, float):
        return 0
    return ""


def expected_content(tag: str) -> dict[str, Any]:
    """A minimal shape template for docs and schema checks."""
    return expected_content_skeleton(sample_content(tag))


def validate_content_shape(tag: str, content: Any) -> list[str]:
    """Return human-friendly validation messages for obvious shape issues."""
    contract = LAYOUT_CONTRACTS.get(tag)
    if contract is None:
        return [f"Unknown layout_tag: {tag!r}."]
    messages: list[str] = []
    if not isinstance(content, dict):
        return ["content must be an object."]

    for key in contract.required_content:
        if key not in content or content[key] in (None, "", []):
            messages.append(f"Missing required content key: {key}.")

    # Light shape checks for common composite fields.
    list_keys = {
        "items",
        "cards",
        "steps",
        "events",
        "kpis",
        "pros",
        "cons",
        "bars",
        "points",
        "layers",
        "phases",
        "capabilities",
    }
    for key in sorted(list_keys & set(content)):
        value = content.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            messages.append(f"content.{key} must be an array.")
            continue
        if value and not all(isinstance(item, dict) for item in value):
            messages.append(f"content.{key} items should be objects.")

    if "columns" in content:
        cols = content.get("columns")
        if cols is not None and (not isinstance(cols, list) or not all(isinstance(c, str) for c in cols)):
            messages.append("content.columns must be an array of strings.")
    if "rows" in content:
        rows = content.get("rows")
        if rows is None:
            pass
        elif not isinstance(rows, list):
            messages.append("content.rows must be an array.")
        else:
            for idx, row in enumerate(rows, start=1):
                if isinstance(row, list):
                    continue
                if isinstance(row, dict) and "cells" in row and isinstance(row.get("cells"), list):
                    continue
                if tag == "Comparison-Matrix-SummaryBar" and isinstance(row, dict):
                    if {"dimension", "left", "right"}.issubset(row.keys()):
                        continue
                messages.append(f"content.rows[{idx}] must be an array, or an object with cells[].")
                break

    return messages


COMMON_ITEMS: tuple[dict[str, str], ...] = (
    {"title": "Alpha", "body": "One focused point with enough text to wrap."},
    {"title": "Beta", "body": "Second point for layout validation."},
    {"title": "Gamma", "body": "Third point for spacing checks."},
    {"title": "Delta", "body": "Fourth point when needed."},
    {"title": "Epsilon", "body": "Fifth point when needed."},
    {"title": "Zeta", "body": "Sixth point when needed."},
)


def _events() -> list[dict[str, str]]:
    return [
        {"date": "M1", **COMMON_ITEMS[0]},
        {"date": "M2", **COMMON_ITEMS[1]},
        {"date": "M3", **COMMON_ITEMS[2]},
        {"date": "M4", **COMMON_ITEMS[3]},
    ]


LAYOUT_CONTRACTS: dict[str, LayoutContract] = {
    "Cover-Center": LayoutContract(
        "Cover-Center",
        "narrative",
        ("headline",),
        {"headline": "Architecture Smoke Test", "subtitle": "All layouts rendered by one engine", "date": "2026"},
    ),
    "Statement-Bold": LayoutContract(
        "Statement-Bold",
        "narrative",
        ("statement",),
        {
            "eyebrow": "Signal",
            "statement": "One renderer should keep layout decisions clean and reusable.",
            "support": "Blueprint data flows into SVG without touching PPT export code.",
        },
    ),
    "Content-List-Left": LayoutContract(
        "Content-List-Left",
        "narrative",
        ("items",),
        {"title": "Left list title", "subtitle": "Stable rhythm", "items": list(COMMON_ITEMS[:4])},
    ),
    "Content-List-Right": LayoutContract(
        "Content-List-Right",
        "narrative",
        ("items",),
        {"title": "Right list title", "subtitle": "Stable rhythm", "items": list(COMMON_ITEMS[:4])},
    ),
    "Section-Divider": LayoutContract(
        "Section-Divider",
        "section",
        ("title",),
        {"section": "01", "title": "Section Divider", "subtitle": "Chapter boundary."},
    ),
    "End-Page": LayoutContract(
        "End-Page",
        "ending",
        ("headline",),
        {"headline": "End Page", "message": "Closing message", "contact": "demo@example.com"},
    ),
    "Two-Columns-Split": LayoutContract(
        "Two-Columns-Split",
        "comparison",
        ("left", "right"),
        {"title": "Two columns", "left": COMMON_ITEMS[0], "right": COMMON_ITEMS[1]},
    ),
    "Before-After": LayoutContract(
        "Before-After",
        "comparison",
        ("before", "after"),
        {"title": "Before and after", "before": COMMON_ITEMS[0], "after": COMMON_ITEMS[1]},
    ),
    "Pros-Cons": LayoutContract(
        "Pros-Cons",
        "comparison",
        ("pros", "cons"),
        {"title": "Pros and cons", "pros": list(COMMON_ITEMS[:3]), "cons": list(COMMON_ITEMS[3:6])},
    ),
    "Grid-Three-Cards": LayoutContract(
        "Grid-Three-Cards",
        "grid",
        ("cards",),
        {"title": "Three cards", "cards": list(COMMON_ITEMS[:3])},
    ),
    "Grid-Four-Cards": LayoutContract(
        "Grid-Four-Cards",
        "grid",
        ("cards",),
        {"title": "Four cards", "cards": list(COMMON_ITEMS[:4])},
    ),
    "Grid-Six-Icons": LayoutContract(
        "Grid-Six-Icons",
        "grid",
        ("items",),
        {"title": "Six icons", "items": list(COMMON_ITEMS[:6])},
    ),
    "Pyramid-Three": LayoutContract(
        "Pyramid-Three",
        "hierarchy",
        ("layers",),
        {"title": "Three-layer pyramid", "layers": list(COMMON_ITEMS[:3])},
    ),
    "Timeline-Horizontal": LayoutContract(
        "Timeline-Horizontal",
        "process",
        ("events",),
        {"title": "Horizontal timeline", "events": _events()},
    ),
    "Timeline-Vertical": LayoutContract(
        "Timeline-Vertical",
        "process",
        ("events",),
        {"title": "Vertical timeline", "events": _events()},
    ),
    "Flow-Steps": LayoutContract(
        "Flow-Steps",
        "process",
        ("steps",),
        {"title": "Flow steps", "steps": list(COMMON_ITEMS[:4])},
    ),
    "Data-Single-KPI": LayoutContract(
        "Data-Single-KPI",
        "data",
        ("value", "label"),
        {"eyebrow": "Metric", "value": "42", "label": "Core KPI", "explanation": "A single number with context."},
    ),
    "Data-Three-KPIs": LayoutContract(
        "Data-Three-KPIs",
        "data",
        ("kpis",),
        {
            "title": "Three KPIs",
            "kpis": [
                {"value": "3x", "label": "Speed", "body": "Faster iteration."},
                {"value": "82%", "label": "Quality", "body": "Higher pass rate."},
                {"value": "12", "label": "Layouts", "body": "Reusable modules."},
            ],
        },
    ),
    "Chart-Bar": LayoutContract(
        "Chart-Bar",
        "data",
        ("bars",),
        {
            "title": "Bar chart",
            "bars": [
                {"label": "A", "value": 30},
                {"label": "B", "value": 55},
                {"label": "C", "value": 80},
                {"label": "D", "value": 45},
            ],
            "insight": "Category C leads.",
        },
    ),
    "Chart-Line": LayoutContract(
        "Chart-Line",
        "data",
        ("points",),
        {
            "title": "Line chart",
            "points": [
                {"label": "Q1", "value": 20},
                {"label": "Q2", "value": 30},
                {"label": "Q3", "value": 68},
                {"label": "Q4", "value": 90},
            ],
            "insight": "Momentum compounds.",
        },
    ),
    "Image-Left-Text-Right": LayoutContract(
        "Image-Left-Text-Right",
        "visual",
        ("title",),
        {"title": "Image left", "body": "Reference visual with explanatory text.", "items": list(COMMON_ITEMS[:3])},
    ),
    "Image-Right-Text-Left": LayoutContract(
        "Image-Right-Text-Left",
        "visual",
        ("title",),
        {
            "title": "Image right",
            "body": "Text leads while visual anchors the right side.",
            "items": list(COMMON_ITEMS[:3]),
        },
    ),
    "Strategy-Map": LayoutContract(
        "Strategy-Map",
        "complex",
        ("north_star", "pillars"),
        {
            "title": "Strategy map",
            "north_star": "Build an AI-driven presentation engine with enterprise-grade visual quality.",
            "pillars": [
                {"title": "Content", "body": "Narrative structure and message clarity."},
                {"title": "Design", "body": "Visual hierarchy and brand rhythm."},
                {"title": "Execution", "body": "Reliable generation and QA gates."},
            ],
            "initiatives": list(COMMON_ITEMS[:4]),
        },
    ),
    "Capability-Mapping": LayoutContract(
        "Capability-Mapping",
        "complex",
        ("capabilities",),
        {
            "title": "Capability mapping",
            "capabilities": [
                {"title": "Strategist", "body": "Scope and narrative design", "system_support": "Prompt constraints"},
                {"title": "Designer", "body": "Blueprint and copyfit planning", "system_support": "Contract validator"},
                {"title": "Executor", "body": "Per-slide SVG authoring", "system_support": "Visual QA"},
            ],
            "support_summary": "System support should be visually strongest in this mapping page.",
        },
    ),
    "Roadmap-MultiPhase": LayoutContract(
        "Roadmap-MultiPhase",
        "complex",
        ("phases",),
        {
            "title": "Multi-phase roadmap",
            "phases": [
                {"phase": "P1", "title": "Baseline", "body": "Visual metrics and sample bench"},
                {"phase": "P2", "title": "Quality", "body": "Visual QA and targeted repair loop"},
                {"phase": "P3", "title": "Expansion", "body": "Complex-page capability packs"},
            ],
            "milestone": "v1 freeze",
        },
    ),
    "TOC-Numbered-Bands": LayoutContract(
        "TOC-Numbered-Bands",
        "bid",
        ("sections",),
        {
            "title": "目录",
            "active": 2,
            "sections": [
                {"number": "1", "title": "项目背景与需求理解"},
                {"number": "2", "title": "解决方案总体设计"},
                {"number": "3", "title": "实施路径与交付保障"},
                {"number": "4", "title": "案例与能力证明"},
            ],
        },
    ),
    "Comparison-Matrix-SummaryBar": LayoutContract(
        "Comparison-Matrix-SummaryBar",
        "bid",
        ("rows",),
        {
            "title": "普通追溯 vs 合规追溯能力边界",
            "left_title": "普通质量追溯",
            "right_title": "供应链合规追溯",
            "rows": [
                {"dimension": "目标", "left": "内部定位质量问题", "right": "形成外部可审查证据链"},
                {"dimension": "对象", "left": "批次/工序记录", "right": "供应商/交易/文件/风险规则"},
                {"dimension": "输出", "left": "内部查询报告", "right": "监管与客户审查报告"},
            ],
            "summary": "合规追溯核心不是查到批次，而是形成可举证、可审计、可复核的证明链。",
        },
    ),
    "Regulation-Table-TwoAxis": LayoutContract(
        "Regulation-Table-TwoAxis",
        "bid",
        ("columns", "rows"),
        {
            "title": "法规要求与应对要点对照",
            "columns": ["标准名称", "内容摘要", "对系统建设要求"],
            "rows": [
                ["UFLPA", "关注上游来源与强迫劳动风险", "提供可追溯来源链与审计证据"],
                ["欧盟CSDDD", "关注供应链尽责调查与披露", "建立供应商协同与风险处置机制"],
                ["ISO 22095", "定义追溯事件模型与术语", "统一对象、粒度与记录口径"],
            ],
            "footnote": "本页用于快速建立法规与建设动作的一一映射。",
        },
    ),
    "Process-LeftCards-CenterFlow": LayoutContract(
        "Process-LeftCards-CenterFlow",
        "bid",
        ("left_cards", "flow_nodes"),
        {
            "title": "可信追溯数据空间流程闭环",
            "left_cards": [
                {"title": "身份可信", "body": "参与方、人员与设备具备可信身份"},
                {"title": "数据可信", "body": "全流程数据在可控环境中采集与加工"},
                {"title": "交易可信", "body": "关键交易与协同记录可核验"},
            ],
            "flow_nodes": [
                {"title": "生产过程数据", "body": "采集与校验"},
                {"title": "供应链数据", "body": "关联与映射"},
                {"title": "运营管理数据", "body": "治理与分析"},
                {"title": "设备监控数据", "body": "监测与预警"},
            ],
            "bottom_systems": ["ERP", "MES", "WMS", "QMS", "SRM", "TMS", "IoT"],
        },
    ),
    "Architecture-Three-Zones": LayoutContract(
        "Architecture-Three-Zones",
        "bid",
        ("left_systems", "core_modules", "right_modules"),
        {
            "title": "系统集成架构",
            "left_systems": ["ERP", "MES", "WMS", "QMS", "SRM", "TMS"],
            "core_modules": [
                {"title": "数据中心", "body": "抽取、建模、调度、展示"},
                {"title": "追溯中心", "body": "正向/反向追溯、追溯地图、报告"},
                {"title": "预警管理", "body": "过程与文件异常检查"},
                {"title": "文件中心", "body": "定义、上传、查询、下载"},
            ],
            "right_modules": ["流程管理", "归档管理", "安全管理", "运维管理"],
            "storage": ["关系库", "时序库", "对象存储", "归档库"],
        },
    ),
    "Maturity-Matrix-Radar": LayoutContract(
        "Maturity-Matrix-Radar",
        "bid",
        ("dimensions", "levels"),
        {
            "title": "供应链追溯成熟度评估",
            "dimensions": ["流程", "组织", "绩效", "IT"],
            "levels": [
                {"level": "1分", "desc": "无定义，依赖人工"},
                {"level": "2分", "desc": "有基础规范但执行不稳"},
                {"level": "3分", "desc": "可执行且有闭环"},
                {"level": "4分", "desc": "协同运营并可量化"},
                {"level": "5分", "desc": "预测驱动与持续优化"},
            ],
            "summary_points": [
                "当前整体处于中等级，内部追溯优于外部协同",
                "优先补齐组织协同与流程标准化",
                "中长期通过数据治理提升成熟度上限",
            ],
        },
    ),
    "Stage-Objectives-Deliverables": LayoutContract(
        "Stage-Objectives-Deliverables",
        "bid",
        ("stage", "objectives", "deliverables"),
        {
            "title": "阶段目标与关键任务",
            "stage": "第二阶段：系统实施与测试",
            "objectives": [
                "完成需求转化与功能开发",
                "完成系统集成与SIT测试",
            ],
            "tasks": [
                "需求文档编写与模块边界定义",
                "核心功能开发与接口联调",
                "制定并执行SIT测试计划",
            ],
            "deliverables": [
                "系统架构与配置文档",
                "测试报告与缺陷清单",
                "初版可运行代码与运维手册",
            ],
        },
    ),
    "Case-Study-Evidence": LayoutContract(
        "Case-Study-Evidence",
        "bid",
        ("background", "goals", "evidence_blocks"),
        {
            "title": "案例：数据伴生追溯项目",
            "background": "客户为大型制造企业，需要打通产线全链路追溯并提升审查响应效率。",
            "goals": [
                "建立设备级过程数据采集能力",
                "打通业务系统并形成可追溯证据链",
                "提升异常发现与预警响应效率",
            ],
            "evidence_blocks": [
                {"title": "关键字段模型", "body": "定义原材料、工序、质量与交易字段"},
                {"title": "平台能力截图", "body": "展示追溯分析、告警与报表模块"},
                {"title": "实施结果", "body": "缩短定位时间并降低人工对账成本"},
            ],
            "result": "项目上线后形成“可查、可证、可审、可报”的运营能力。",
        },
    ),
    "SLA-Double-Table": LayoutContract(
        "SLA-Double-Table",
        "bid",
        ("left_rows", "right_rows"),
        {
            "title": "故障响应级别与时效约定",
            "left_title": "SLA指标与目标",
            "left_rows": [
                {"metric": "严重级别1响应时间", "target": "1小时内"},
                {"metric": "严重级别2响应时间", "target": "2小时内"},
                {"metric": "严重级别3响应时间", "target": "4小时内"},
                {"metric": "严重级别4响应时间", "target": "8小时内"},
            ],
            "right_title": "严重级别定义",
            "right_rows": [
                {"level": "严重级别1", "desc": "关键业务不可用或停止"},
                {"level": "严重级别2", "desc": "核心功能受损，业务明显受影响"},
                {"level": "严重级别3", "desc": "局部功能异常，有替代方案"},
                {"level": "严重级别4", "desc": "轻微影响，不阻断主流程"},
            ],
        },
    ),
    "Roadmap-Lane-Milestones": LayoutContract(
        "Roadmap-Lane-Milestones",
        "bid",
        ("phases",),
        {
            "title": "实施路线图与里程碑",
            "phases": [
                {
                    "phase": "P1",
                    "title": "诊断与蓝图",
                    "body": "目标定义、规则梳理、方案定稿",
                    "milestone": "蓝图评审通过",
                },
                {
                    "phase": "P2",
                    "title": "建设与联调",
                    "body": "核心功能开发、系统集成、SIT",
                    "milestone": "联调与测试完成",
                },
                {"phase": "P3", "title": "上线与运营", "body": "试运行、验收、运营优化", "milestone": "稳定运营达标"},
            ],
            "summary": "三阶段并行保障：业务、数据、系统协同推进，确保按期上线。",
        },
    ),
}


def layout_tags() -> list[str]:
    return list(LAYOUT_CONTRACTS)


def required_content_keys(tag: str) -> tuple[str, ...]:
    contract = LAYOUT_CONTRACTS.get(tag)
    return contract.required_content if contract else ()


def sample_content(tag: str) -> dict[str, Any]:
    if tag not in LAYOUT_CONTRACTS:
        raise KeyError(f"Unknown layout tag: {tag}")
    return deepcopy(LAYOUT_CONTRACTS[tag].sample_content)


def sample_slide(slide_id: int, tag: str) -> dict[str, Any]:
    return {
        "id": slide_id,
        "title": tag,
        "layout_tag": tag,
        "narrative_intent": "regression coverage",
        "content": sample_content(tag),
    }


def sample_blueprint(tags: list[str] | None = None) -> dict[str, Any]:
    selected = tags or layout_tags()
    return {"slides": [sample_slide(idx, tag) for idx, tag in enumerate(selected, start=1)]}
