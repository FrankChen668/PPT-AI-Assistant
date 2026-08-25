#!/usr/bin/env python3
"""Create the deterministic native PPTX fidelity acceptance project."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DEFAULT_PROJECT = ROOT / "projects" / "native-fidelity-demo"
sys.path.insert(0, str(SCRIPT_DIR))

from render_svg import render_project  # noqa: E402
from render_theme import Theme  # noqa: E402
from svg_canvas import SvgCanvas  # noqa: E402

DESIGN_SPEC = """# Design Spec
- canvas: ppt169
- style: native-fidelity-fixture
- primary_color: #17324D
- accent_color: #2F80ED
- secondary_accent: #F2994A
- background_color: #F7F9FC
- card_bg: #FFFFFF
- text_color: #17324D
- muted_color: #5D6B79
- font_title: "Microsoft YaHei", "Arial", sans-serif
- font_body: "Microsoft YaHei", "Arial", sans-serif
- page_count: 8
- language: zh-CN
"""

OUTLINE = """# Native Fidelity Demo

1. 封面
2. 核心判断
3. 图片转换
4. 流程关系
5. KPI
6. 复杂分组
7. 质量备注
8. 结束页
"""

BLUEPRINT = {
    "slides": [
        {
            "id": 1,
            "title": "原生可编辑交付验收",
            "layout_tag": "Cover-Center",
            "content": {"headline": "原生可编辑交付验收", "subtitle": "关键内容、图片与箭头的固定回归样板"},
        },
        {
            "id": 2,
            "title": "核心判断",
            "layout_tag": "Statement-Bold",
            "content": {
                "statement": "关键内容必须完整进入可编辑 PPTX",
                "support": "装饰差异可以复核，主体内容损失必须阻断。",
            },
        },
        {
            "id": 3,
            "title": "图片转换",
            "layout_tag": "Image-Left-Text-Right",
            "content": {"title": "图片转换", "body": "主图、辅助图与内嵌图片均进入媒体关系。"},
        },
        {
            "id": 4,
            "title": "流程关系",
            "layout_tag": "Flow-Steps",
            "content": {"title": "流程关系", "steps": [{"title": "输入"}, {"title": "转换"}, {"title": "交付"}]},
        },
        {
            "id": 5,
            "title": "关键指标",
            "layout_tag": "Data-Single-KPI",
            "content": {"value": "98%", "label": "关键内容保真率", "explanation": "关键数字作为独立语义进入报告。"},
        },
        {
            "id": 6,
            "title": "复杂分组",
            "layout_tag": "Statement-Bold",
            "content": {"statement": "分组与简单效果保持主体结构", "support": "透明度、渐变和阴影用于非关键视觉层。"},
        },
        {
            "id": 7,
            "title": "质量备注",
            "layout_tag": "Statement-Bold",
            "content": {"statement": "复杂装饰 marker 不影响主体交付", "support": "报告应记录备注，但不阻断下载。"},
        },
        {
            "id": 8,
            "title": "验收完成",
            "layout_tag": "End-Page",
            "content": {"headline": "验收完成", "message": "同一套样板可重复执行。"},
        },
    ]
}


def _image_bytes(fmt: str, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", size, color)
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _write_assets(project_dir: Path) -> str:
    images = project_dir / "images"
    images.mkdir(parents=True, exist_ok=True)
    (images / "hero.png").write_bytes(_image_bytes("PNG", (64, 40), (47, 128, 237)))
    (images / "support.jpg").write_bytes(_image_bytes("JPEG", (32, 24), (242, 153, 74)))
    inline = _image_bytes("PNG", (16, 16), (39, 174, 96))
    return "data:image/png;base64," + base64.b64encode(inline).decode("ascii")


def _canvas(title: str) -> SvgCanvas:
    return SvgCanvas(title, Theme(), semantic_roles={title: "title"})


def _write_custom_slides(project_dir: Path, inline_image: str) -> None:
    output = project_dir / "svg_output"

    image_page = _canvas("图片转换")
    image_page.wrapped_text(80, 92, "图片转换", 1120, 36, weight=850)
    image_page.image(80, 150, 620, 340, "../images/hero.png", content_role="hero-image", element_id="hero-image")
    image_page.image(760, 170, 180, 120, "../images/support.jpg", element_id="support-jpeg")
    image_page.image(980, 170, 120, 120, inline_image, element_id="inline-png")
    image_page.wrapped_text(760, 350, "主图可移动替换；辅助图保持独立图片对象。", 400, 22, max_lines=3)
    image_page.footer()
    (output / "slide_03.svg").write_text(image_page.output(), encoding="utf-8")

    flow = _canvas("流程关系")
    flow.wrapped_text(80, 92, "流程关系", 1120, 36, weight=850)
    for index, (x, label) in enumerate(((100, "输入"), (480, "转换"), (860, "交付")), start=1):
        flow.card(x, 220, 260, 150)
        flow.text(x + 130, 300, f"{index}. {label}", 28, weight=800, anchor="middle")
    flow.line(360, 295, 470, 295, "#17324D", 4, arrow=True, extra_attrs='id="straight-arrow"')
    flow.polyline(
        [(740, 295), (800, 295), (800, 420), (990, 420)],
        "#2F80ED",
        4,
        arrow=True,
        extra_attrs='id="elbow-arrow"',
    )
    flow.wrapped_text(100, 500, "直线与折线的箭头方向均指向流程终点。", 1050, 22, max_lines=2)
    flow.footer()
    (output / "slide_04.svg").write_text(flow.output(), encoding="utf-8")

    grouped = _canvas("复杂分组")
    grouped.defs.append(
        '<linearGradient id="soft-grad" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#DCEBFF"/>'
        '<stop offset="1" stop-color="#FFFFFF"/>'
        "</linearGradient>"
    )
    grouped.wrapped_text(80, 92, "复杂分组", 1120, 36, weight=850)
    grouped.add('<g id="primary-group" data-content-role="primary-content">')
    grouped.add('<rect x="160" y="180" width="960" height="330" rx="24" fill="url(#soft-grad)" filter="url(#shadow)"/>')
    grouped.add(
        '<text x="640" y="300" text-anchor="middle" font-family="Microsoft YaHei" font-size="38" '
        'font-weight="800" fill="#17324D">主体分组保持可编辑</text>'
    )
    grouped.add(
        '<circle cx="500" cy="390" r="48" fill="#2F80ED" opacity="0.72"/>'
        '<circle cx="640" cy="390" r="48" fill="#27AE60" opacity="0.72"/>'
        '<circle cx="780" cy="390" r="48" fill="#F2994A" opacity="0.72"/>'
    )
    grouped.add('</g>')
    grouped.footer()
    (output / "slide_06.svg").write_text(grouped.output(), encoding="utf-8")

    notes = _canvas("质量备注")
    notes.defs.append(
        '<marker id="decorative-dot" viewBox="0 0 20 20" refX="10" refY="10" markerWidth="10" '
        'markerHeight="10"><circle cx="10" cy="10" r="8" fill="#F2994A"/></marker>'
    )
    notes.wrapped_text(80, 92, "质量备注", 1120, 36, weight=850)
    notes.wrapped_text(120, 230, "复杂装饰端点允许降级，但必须记录。", 980, 42, weight=800, max_lines=2)
    notes.line(220, 390, 980, 390, "#5D6B79", 4, extra_attrs='id="decorative-marker" marker-end="url(#decorative-dot)"')
    notes.footer()
    (output / "slide_07.svg").write_text(notes.output(), encoding="utf-8")


def create_demo_project(project_dir: Path = DEFAULT_PROJECT) -> Path:
    project_dir = project_dir.resolve()
    for name in ("svg_output", "svg_final", "exports", "qa", "images"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)
    (project_dir / "design_spec.md").write_text(DESIGN_SPEC, encoding="utf-8")
    (project_dir / "outline.md").write_text(OUTLINE, encoding="utf-8")
    (project_dir / "blueprint.json").write_text(
        json.dumps(BLUEPRINT, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (project_dir / "reference_pack.json").write_text(
        json.dumps(
            {"free_design_override_reason": "Deterministic native conversion acceptance fixture."},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    inline_image = _write_assets(project_dir)
    render_project(project_dir, output_dir="svg_output", clean=False)
    _write_custom_slides(project_dir, inline_image)
    return project_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args(argv)
    project = create_demo_project(args.project_dir)
    print(f"Created {project} with 8 deterministic slides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
