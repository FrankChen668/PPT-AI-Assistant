#!/usr/bin/env python3
"""Create the AI trends demo using the production renderer.

The demo script intentionally stops at content artifacts plus the renderer call.
It should not contain slide-specific SVG drawing code; that belongs in
render_svg.py so the demo exercises the same architecture as real projects.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
PROJECT = ROOT / "projects" / "ai-trends-demo"
sys.path.insert(0, str(SCRIPT_DIR))

from render_svg import render_project  # noqa: E402

DESIGN_SPEC = """# Design Spec
- canvas: ppt169
- style: signal-minimal
- primary_color: #101216
- accent_color: #00C2A8
- secondary_accent: #FF5A5F
- background_color: #F7F8FA
- card_bg: #FFFFFF
- text_color: #101216
- muted_color: #68707D
- data_palette: #00C2A8,#FF5A5F,#1E3A5F,#D4AC0D
- font_ladder: title 44/700 | body 20/400 | caption 12/400
- font_title: "PingFang SC", "Microsoft YaHei", "Arial", sans-serif
- font_body: "PingFang SC", "Microsoft YaHei", "Arial", sans-serif
- page_count: 10
- audience: executive decision makers
- language: zh-CN
- topic: AI 趋势 2026：从工具到操作系统
"""


OUTLINE = """# AI 趋势 2026：从工具到操作系统

1. 封面：建立主题，说明这是一个趋势判断 demo。
2. 核心判断：AI 竞争焦点从模型能力转向工作流占位。
3. 三条主线：模型商品化、Agent 工作流、私有知识层。
4. 范式迁移：从 Copilot 辅助到 Agent 闭环。
5. 能力栈：模型层、工具层、治理层三层结构。
6. 落地抓手：任务切片、数据接入、权限边界、反馈闭环。
7. 应用机会：销售运营、知识服务、研发协作、财务法务。
8. 风险治理：幻觉、越权、泄露、漂移。
9. 90 天路线图：试点、闭环、治理与指标。
10. 结束页：从高频任务开始，让 AI 进入真正工作流。
"""


BLUEPRINT: dict[str, Any] = {
    "slides": [
        {
            "id": 1,
            "title": "封面",
            "layout_tag": "Cover-Center",
            "narrative_intent": "建立主题和判断框架",
            "content": {
                "headline": "AI 趋势 2026",
                "subtitle": "从工具到操作系统",
                "date": "Demo · 2026-04-19",
            },
        },
        {
            "id": 2,
            "title": "核心判断",
            "layout_tag": "Statement-Bold",
            "narrative_intent": "给出全篇主论点",
            "content": {
                "eyebrow": "核心判断",
                "statement": "AI 的竞争焦点，正在从模型能力转向工作流入口。",
                "support": "谁能把智能嵌进高频任务、业务数据和组织权限，谁就拥有下一轮入口。",
            },
        },
        {
            "id": 3,
            "title": "三条主线",
            "layout_tag": "Grid-Three-Cards",
            "narrative_intent": "拆解趋势地图",
            "content": {
                "title": "三条主线正在同时发生",
                "cards": [
                    {"title": "模型商品化", "body": "基础能力快速接近，差异来自成本、延迟和可靠性。"},
                    {"title": "Agent 工作流", "body": "AI 从回答问题，转向规划、执行、检查和交付结果。"},
                    {"title": "私有知识层", "body": "企业价值沉淀在数据、流程、权限和反馈闭环里。"},
                ],
            },
        },
        {
            "id": 4,
            "title": "范式迁移",
            "layout_tag": "Two-Columns-Split",
            "narrative_intent": "说明产品形态的变化",
            "content": {
                "title": "从 Copilot 到 Agent：产品重心发生迁移",
                "left": {"title": "Copilot", "body": "用户发起任务，AI 辅助完成片段。价值在效率提升。"},
                "right": {"title": "Agent", "body": "系统接收目标，AI 协调工具链交付结果。价值在任务闭环。"},
            },
        },
        {
            "id": 5,
            "title": "能力栈",
            "layout_tag": "Data-Single-KPI",
            "narrative_intent": "抽象企业落地结构",
            "content": {
                "eyebrow": "企业 AI 落地结构",
                "value": "3",
                "label": "层能力栈",
                "explanation": "模型层负责生成，工具层负责行动，治理层负责可控。",
            },
        },
        {
            "id": 6,
            "title": "落地抓手",
            "page_type": "capability-map",
            "layout_tag": "Content-List-Left",
            "narrative_intent": "给出执行重点",
            "content": {
                "title": "落地不是买模型，而是重组任务。",
                "subtitle": "先挑高频、可验证、可回滚的流程。",
                "items": [
                    {"title": "任务切片", "body": "把复杂工作拆成可评价的步骤。"},
                    {"title": "数据接入", "body": "让 AI 能读到业务上下文。"},
                    {"title": "权限边界", "body": "把能看、能改、能发分层管理。"},
                    {"title": "反馈闭环", "body": "让结果持续进入评估和改进。"},
                ],
            },
        },
        {
            "id": 7,
            "title": "应用机会",
            "layout_tag": "Grid-Four-Cards",
            "narrative_intent": "展示可切入场景",
            "content": {
                "title": "最先形成价值的四类场景",
                "cards": [
                    {"title": "销售运营", "body": "线索研究、邮件草拟、会议纪要和 CRM 更新。"},
                    {"title": "知识服务", "body": "内部问答、制度检索、专家经验沉淀。"},
                    {"title": "研发协作", "body": "需求拆解、代码辅助、测试生成和缺陷归因。"},
                    {"title": "财务法务", "body": "合同初审、票据核对、预算解释和风险提示。"},
                ],
            },
        },
        {
            "id": 8,
            "title": "风险治理",
            "page_type": "risk",
            "layout_tag": "Content-List-Right",
            "narrative_intent": "提醒治理不是阻力而是部署条件",
            "content": {
                "title": "治理决定 AI 能不能进核心流程。",
                "subtitle": "速度重要，但可追责更重要。",
                "items": [
                    {"title": "幻觉", "body": "关键判断必须可引用、可复查。"},
                    {"title": "越权", "body": "动作权限要与岗位和场景绑定。"},
                    {"title": "泄露", "body": "敏感数据需要脱敏和访问审计。"},
                    {"title": "漂移", "body": "定期评估提示词、工具和模型版本。"},
                ],
            },
        },
        {
            "id": 9,
            "title": "90 天路线图",
            "layout_tag": "Section-Divider",
            "narrative_intent": "把判断转成行动节奏",
            "content": {
                "section": "90 DAYS",
                "title": "从试点到规模化",
                "subtitle": "第 1 月定场景，第 2 月跑闭环，第 3 月接治理和指标。",
                "phases": [
                    {"title": "第 1 月", "body": "确定高频、可验证的试点场景。"},
                    {"title": "第 2 月", "body": "跑通任务、数据和反馈闭环。"},
                    {"title": "第 3 月", "body": "接入治理规则和成效指标。"},
                ],
            },
        },
        {
            "id": 10,
            "title": "结束页",
            "layout_tag": "End-Page",
            "narrative_intent": "收束观点并邀请讨论",
            "content": {
                "headline": "让 AI 进入真正的工作流",
                "message": "从一个高频任务开始，用可衡量结果推动下一步。",
                "contact": "AI-PPT · projects/ai-trends-demo",
            },
        },
    ]
}

ART_DIRECTION = """# Art Direction

- direction: signal-minimal demo fixture
- visual_goal: keep the generated demo deterministic, readable, and QA-clean for pipeline verification
- composition: simple executive narrative pages with restrained cards and accent lines
- quality_note: this fixture validates engineering gates; premium visual polish is covered by separate proposal samples
"""

REFERENCE_PACK = {
    "mode": "free_design",
    "free_design_override_reason": "Deterministic pipeline fixture; not a delivery deck.",
    "selected_references": [],
}

VISUAL_ARCHETYPES = (
    "cover",
    "statement",
    "three-card",
    "split",
    "kpi",
    "list",
    "four-card",
    "risk-list",
    "divider",
    "closing",
)

SLIDE_VISUAL_PLAN = {
    "slides": [
        {
            "slide_id": slide["id"],
            "layout_tag": slide["layout_tag"],
            "visual_role": "pipeline fixture",
            "intent": slide.get("narrative_intent", ""),
            "visual_archetype": VISUAL_ARCHETYPES[(int(slide["id"]) - 1) % len(VISUAL_ARCHETYPES)],
            "variation_rule": f"Use a distinct deterministic composition for fixture slide {slide['id']}.",
            "page_prompt_pattern": {
                "pattern_id": f"fixture-{slide['id']:02d}",
                "conclusion_formula": "claim first, support second",
                "block_structure": "title zone + content zone + footer",
                "composition_cues": ["stable grid", "clear hierarchy", "bounded text"],
                "anti_patterns": ["dense paragraphs", "decorative clutter"],
            },
            "execution_policy": {
                "scene_type": "presentation_fixture",
                "generation_strategy": "deterministic_renderer",
                "risk_level": "low",
                "required_loop": "render_then_qa",
                "qa_strictness": "non_blocking",
                "expected_first_pass_rules": ["UTF-8 SVG", "no overflow", "native export succeeds"],
            },
            "visual_contract": {
                "scene_type": "presentation_fixture",
                "generation_strategy": "deterministic_renderer",
                "focal_point": "slide title and primary content block",
                "primary_read_path": ["title", "main content", "footer"],
                "composition_grammar": "simple deterministic layout",
                "hierarchy_ladder": "title > content > support",
                "density_budget": {"max_text_nodes": 28, "max_chars": 900},
                "whitespace_target": "moderate",
                "template_inheritance": "none; fixture free design",
                "anti_patterns": ["overlap", "unbounded text", "unsupported SVG"],
                "critic_checks": ["text fits", "export succeeds", "QA stays warning-clean"],
                "layout_intent": "exercise pipeline compatibility with predictable geometry",
                "bbox_budget": {"safe_area": [60, 60, 1160, 600], "footer_band": [70, 625, 1140, 48]},
                "text_budget": {"max_chars": 900, "max_lines_per_block": 4},
                "deterministic_scaffold": {"renderer": "render_svg.py", "layout_tag": slide["layout_tag"]},
                "must_avoid": ["foreignObject", "external assets", "multiword English footers on CJK slides"],
                "pre_authoring_checks": ["blueprint content is concise", "design tokens are present"],
            },
        }
        for slide in BLUEPRINT["slides"]
    ]
}

STYLE_ROUTE = {
    "style_profile": "presentation",
    "confidence": 1.0,
    "requires_style_drafts": False,
}


def main() -> int:
    create_project(PROJECT)
    print(f"Created {PROJECT} with {len(BLUEPRINT['slides'])} rendered slides")
    return 0


def create_project(project_dir: Path = PROJECT, *, render: bool = True) -> Path:
    if project_dir.exists():
        shutil.rmtree(project_dir)
    for name in ("svg_output", "svg_final", "exports", "qa"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)

    (project_dir / "design_spec.md").write_text(DESIGN_SPEC, encoding="utf-8")
    (project_dir / "outline.md").write_text(OUTLINE, encoding="utf-8")
    (project_dir / "blueprint.json").write_text(
        json.dumps(BLUEPRINT, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "art_direction.md").write_text(ART_DIRECTION, encoding="utf-8")
    (project_dir / "reference_pack.json").write_text(
        json.dumps(REFERENCE_PACK, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "slide_visual_plan.json").write_text(
        json.dumps(SLIDE_VISUAL_PLAN, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "style_route.json").write_text(
        json.dumps(STYLE_ROUTE, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if render:
        render_project(project_dir, output_dir="svg_output", clean=True)
    return project_dir


if __name__ == "__main__":
    raise SystemExit(main())
