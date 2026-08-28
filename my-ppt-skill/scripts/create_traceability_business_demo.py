#!/usr/bin/env python3
"""Create the deterministic business-planning acceptance project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_PROJECT = ROOT / "projects" / "traceability-business-demo"
sys.path.insert(0, str(SCRIPT_DIR))

from generate_art_direction import generate_art_direction  # noqa: E402
from generate_slide_plan import generate_slide_plan  # noqa: E402
from render_svg import render_project  # noqa: E402

DESIGN_SPEC = """# Design Spec
- canvas: ppt169
- style: clean-business-consulting
- primary_color: #17324D
- accent_color: #2F80ED
- secondary_accent: #27AE60
- background_color: #F7F9FC
- card_bg: #FFFFFF
- text_color: #17324D
- muted_color: #5D6B79
- font_title: "Microsoft YaHei", "Arial", sans-serif
- font_body: "Microsoft YaHei", "Arial", sans-serif
- page_count: 10
- language: zh-CN
"""

OUTLINE = """# 新能源供应链合规追溯项目建设方案

1. 封面
2. 建设背景
3. 现状问题
4. 核心判断
5. 建设目标
6. 业务范围
7. 能力架构
8. 追溯业务流程
9. 实施路线
10. 总结
"""

REFERENCE_PACK = {
    "free_design_override_reason": "Deterministic business-planning acceptance fixture without customer data.",
    "style_profile": "presentation",
}


def _semantic(
    *,
    page_type: str,
    role: str,
    intent: str,
    conclusion: str,
    evidence: list[str],
    blocks: list[tuple[str, str]],
    archetype: str,
) -> dict:
    return {
        "page_type": page_type,
        "narrative_role": role,
        "page_intent": intent,
        "conclusion": conclusion,
        "evidence": evidence,
        "content_blocks": [
            {"role": block_role, "type": block_type}
            for block_role, block_type in blocks
        ],
        "visual_archetype": archetype,
        "density_level": "medium",
        "editable_priority": ["title", "conclusion", "evidence"],
    }


BLUEPRINT = {
    "slides": [
        {
            "id": 1,
            "title": "新能源供应链合规追溯项目建设方案",
            "layout_tag": "Cover-Center",
            "page_type": "cover",
            "narrative_role": "建立主题",
            "page_intent": "明确本方案聚焦供应链合规证据链建设",
            "conclusion": "",
            "evidence": [],
            "content_blocks": [{"role": "project-theme", "type": "title"}],
            "visual_archetype": "headline-hero",
            "density_level": "low",
            "editable_priority": ["title", "subtitle"],
            "content": {
                "headline": "新能源供应链合规追溯项目建设方案",
                "subtitle": "从资料响应转向全过程证据链管理",
                "date": "确定性工程验收样板",
            },
        },
        {
            "id": 2,
            "title": "外部要求正在推动供应链证明方式升级",
            "layout_tag": "Content-List-Right",
            **_semantic(
                page_type="background",
                role="交代背景与压力",
                intent="说明企业需要从临时资料响应转向持续证据准备",
                conclusion="供应链合规要求正在从单次资料提交转向过程证据的持续验证",
                evidence=["核查范围逐步延伸到多级供应商", "证明材料需要能够追溯来源和处理过程"],
                blocks=[("external-pressure", "fact"), ("operating-impact", "implication")],
                archetype="pressure-evidence-implication",
            ),
            "content": {
                "title": "外部要求正在推动供应链证明方式升级",
                "subtitle": "企业需要提前准备可核验、可复用的供应链证据",
                "items": [
                    {"title": "范围延伸", "body": "核查对象由企业内部延伸到多级供应商"},
                    {"title": "过程可证", "body": "材料需要说明来源、校验与整改过程"},
                    {"title": "持续响应", "body": "临时收集难以支撑常态化审核与客户问询"},
                ],
            },
        },
        {
            "id": 3,
            "title": "现状问题集中在资料、协同和证据三个断点",
            "layout_tag": "Grid-Three-Cards",
            **_semantic(
                page_type="problem-analysis",
                role="拆解问题",
                intent="解释当前工作方式为何难以支撑供应链合规验证",
                conclusion="资料分散、事后补充和协同困难共同造成证据链不连续",
                evidence=["材料分散在表格、邮件和不同业务系统", "缺少统一任务状态和整改闭环"],
                blocks=[("fragmented-data", "problem"), ("late-response", "cause"), ("weak-collaboration", "impact")],
                archetype="problem-cause-impact",
            ),
            "content": {
                "cards": [
                    {"title": "资料分散", "body": "同一材料存在多份版本，来源和责任人不清晰"},
                    {"title": "事后补充", "body": "审核前临时追要，无法稳定复用历史证据"},
                    {"title": "协同困难", "body": "供应商填报、校验和整改缺少统一状态"},
                ]
            },
        },
        {
            "id": 4,
            "title": "普通质量追溯不能替代合规证据链追溯",
            "layout_tag": "Statement-Bold",
            **_semantic(
                page_type="statement",
                role="核心判断",
                intent="向管理层明确本项目与普通质量追溯的边界",
                conclusion="合规追溯不仅记录结果，还必须保留规则、责任、校验和整改证据",
                evidence=["质量记录侧重批次与结果", "合规核查同时关注证明依据和处理过程"],
                blocks=[("quality-trace", "fact"), ("compliance-proof", "conclusion")],
                archetype="conclusion-evidence",
            ),
            "content": {
                "eyebrow": "核心判断",
                "statement": "合规追溯不仅记录结果，还必须保留规则、责任、校验和整改证据",
                "support": "质量记录回答“发生了什么”，证据链还要回答“依据什么、由谁确认、如何闭环”",
            },
        },
        {
            "id": 5,
            "title": "建设目标是形成四项可持续运营能力",
            "layout_tag": "Grid-Four-Cards",
            **_semantic(
                page_type="capability-map",
                role="界定目标能力",
                intent="把抽象建设目标转化为可验收的能力方向",
                conclusion="项目应同时实现可审查、可协同、可扩展和可运营",
                evidence=["证据需要按对象和任务快速检索", "供应商范围与规则变化需要平稳扩展"],
                blocks=[("auditable", "goal"), ("collaborative", "goal"), ("scalable", "goal"), ("operable", "goal")],
                archetype="capability-domains",
            ),
            "content": {
                "cards": [
                    {"title": "可审查", "body": "按材料、对象和任务还原证据链"},
                    {"title": "可协同", "body": "统一填报、校验、整改和确认状态"},
                    {"title": "可扩展", "body": "支持供应商层级与规则范围逐步扩展"},
                    {"title": "可运营", "body": "形成常态任务、提醒和质量复盘机制"},
                ]
            },
        },
        {
            "id": 6,
            "title": "业务范围需要同时覆盖企业内部与多级供应商",
            "layout_tag": "Two-Columns-Split",
            **_semantic(
                page_type="comparison",
                role="明确范围边界",
                intent="说明企业内部与供应商侧承担不同但衔接的工作",
                conclusion="内部规则治理与供应商证据协同必须在同一任务链上衔接",
                evidence=["企业内部负责规则、对象和审核口径", "供应商负责材料提交、说明和整改"],
                blocks=[("enterprise-side", "scope"), ("supplier-side", "scope")],
                archetype="two-sided-comparison",
            ),
            "content": {
                "title": "业务范围需要同时覆盖企业内部与多级供应商",
                "left": {"title": "企业内部", "body": "维护规则、材料目录、关键对象和审核口径"},
                "right": {"title": "供应商网络", "body": "完成填报、举证、问题说明和整改反馈"},
            },
        },
        {
            "id": 7,
            "title": "能力架构以规则和数据为底座贯通协同与报告",
            "layout_tag": "Architecture-Three-Zones",
            **_semantic(
                page_type="architecture",
                role="说明能力关系",
                intent="展示规则、数据、协同、证据与报告如何组成统一能力",
                conclusion="统一规则与数据底座能够让协同过程直接沉淀为可审查证据",
                evidence=["规则决定任务对象、材料和校验要求", "协同结果需要进入证据库并形成报告"],
                blocks=[
                    ("rules", "layer"),
                    ("data", "layer"),
                    ("collaboration", "module"),
                    ("evidence-report", "module"),
                ],
                archetype="layered-architecture",
            ),
            "content": {
                "left_systems": ["规则来源", "采购对象", "供应商主数据"],
                "core_modules": [
                    {"title": "规则中心", "body": "维护材料目录与校验口径"},
                    {"title": "协同任务", "body": "组织填报、校验与整改"},
                    {"title": "证据管理", "body": "保留版本、责任和处理记录"},
                    {"title": "报告输出", "body": "按对象和主题形成证明材料"},
                ],
                "right_modules": ["任务运营", "质量复核", "审查响应"],
                "storage": ["规则数据", "供应商数据", "材料证据", "过程日志"],
            },
        },
        {
            "id": 8,
            "title": "追溯流程把供应商填报转化为可验证报告",
            "layout_tag": "Process-LeftCards-CenterFlow",
            **_semantic(
                page_type="process",
                role="说明业务闭环",
                intent="明确从任务发起到报告输出的责任与状态流转",
                conclusion="任务、填报、校验、整改和报告必须形成可追踪的闭环",
                evidence=["每个环节都需要明确责任人与完成状态", "校验问题需要整改并保留前后版本"],
                blocks=[
                    ("intake-and-submission", "workflow"),
                    ("validation-and-remediation", "workflow"),
                    ("report-output", "workflow"),
                ],
                archetype="step-flow",
            ),
            "content": {
                "steps": ["任务发起", "供应商填报", "规则校验", "问题整改", "报告输出"],
                "left_cards": [
                    {"title": "责任明确", "body": "任务关联对象、材料和截止时间"},
                    {"title": "状态透明", "body": "填报、校验与整改过程可追踪"},
                    {"title": "版本留痕", "body": "保留提交和整改前后证据"},
                ],
                "flow_nodes": ["任务发起", "供应商填报", "规则校验", "问题整改", "报告输出"],
                "bottom_systems": ["采购", "供应商门户", "规则库", "证据库"],
            },
        },
        {
            "id": 9,
            "title": "实施路线从关键材料试点逐步扩展到常态运营",
            "layout_tag": "Roadmap-Lane-Milestones",
            **_semantic(
                page_type="roadmap",
                role="安排实施节奏",
                intent="说明项目如何在控制风险的前提下逐步扩大范围",
                conclusion="先验证关键材料与典型供应商，再扩展范围并固化运营机制",
                evidence=["试点可以先验证规则口径和协同流程", "扩展阶段再覆盖更多材料与供应商层级"],
                blocks=[("pilot", "phase"), ("scale", "phase"), ("operate", "phase")],
                archetype="phased-roadmap",
            ),
            "content": {
                "phases": [
                    {
                        "phase": "阶段1",
                        "title": "关键材料试点",
                        "body": "验证规则、任务和证据闭环",
                        "milestone": "试点流程可复用",
                    },
                    {
                        "phase": "阶段2",
                        "title": "范围扩展",
                        "body": "增加供应商层级与材料主题",
                        "milestone": "核心范围稳定运行",
                    },
                    {
                        "phase": "阶段3",
                        "title": "常态运营",
                        "body": "建立任务节奏和质量复盘",
                        "milestone": "形成持续运营机制",
                    },
                ],
                "summary": "以试点验证口径，以扩展验证规模，以运营保证长期有效",
            },
        },
        {
            "id": 10,
            "title": "聚焦关键材料和典型供应商，分阶段建立证据链能力",
            "layout_tag": "End-Page",
            **_semantic(
                page_type="summary",
                role="收束行动建议",
                intent="把全套方案收束为可执行的启动建议",
                conclusion="从关键材料和典型供应商切入，是兼顾业务价值与实施风险的起点",
                evidence=["聚焦范围有利于快速统一规则口径", "典型供应商能够验证真实协同复杂度"],
                blocks=[("start-scope", "priority"), ("next-action", "action")],
                archetype="conclusion-priorities",
            ),
            "content": {
                "headline": "聚焦关键材料和典型供应商，分阶段建立证据链能力",
                "message": "先验证规则与协同闭环，再逐步扩大材料、供应商和运营范围",
            },
        },
    ]
}


def create_demo_project(project_dir: Path = DEFAULT_PROJECT) -> Path:
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    for name in ("svg_output", "svg_final", "exports", "qa"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)
    (project_dir / "design_spec.md").write_text(DESIGN_SPEC, encoding="utf-8")
    (project_dir / "outline.md").write_text(OUTLINE, encoding="utf-8")
    (project_dir / "blueprint.json").write_text(
        json.dumps(BLUEPRINT, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "reference_pack.json").write_text(
        json.dumps(REFERENCE_PACK, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    generate_slide_plan(project_dir, overwrite=True)
    generate_art_direction(project_dir, overwrite=True)
    # Keep the tracked fixture input small; visual-plan outputs remain reproducible build artifacts.
    (project_dir / "reference_pack.json").write_text(
        json.dumps(REFERENCE_PACK, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    render_project(project_dir, output_dir="svg_output", clean=True)
    return project_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args(argv)
    project = create_demo_project(args.project_dir)
    print(f"Created {project} with 10 deterministic business slides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
