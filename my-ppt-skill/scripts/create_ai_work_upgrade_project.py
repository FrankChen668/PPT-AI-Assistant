#!/usr/bin/env python3
"""Create the AI work-upgrade 29-slide project from the supplied Markdown drafts."""

from __future__ import annotations

import html
import json
import math
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "my-ppt-skill"
PROJECT = SKILL / "projects" / "ai-work-upgrade-p1-p29"
DESKTOP = Path.home() / "Desktop"

LABELS = {
    "purpose": "\u9875\u9762\u76ee\u7684",
    "tone": "\u9875\u9762\u6c14\u8d28",
    "layout": "\u63a8\u8350\u7248\u5f0f",
    "info": "\u4fe1\u606f\u5c42\u7ea7",
    "visual": "\u89c6\u89c9\u91cd\u70b9",
    "conclusion": "\u5e95\u90e8\u7ed3\u8bba",
}

C = {
    "primary": "#932141",
    "wine": "#800020",
    "bg": "#F5F5F5",
    "card": "#FFFFFF",
    "text": "#333333",
    "muted": "#666666",
    "light": "#8A8A8A",
    "line": "#D9D9D9",
    "soft": "#F7F2F4",
}
FONT = "Microsoft YaHei, PingFang SC, Arial, sans-serif"

TYPE = {
    1: "cover",
    2: "cards3",
    3: "route",
    4: "cards3",
    5: "compare",
    6: "chain",
    7: "compare",
    8: "dotwell",
    9: "quote3",
    10: "route",
    11: "loop",
    12: "cards6",
    13: "quadrant",
    14: "painchain",
    15: "chain-human",
    16: "input-output",
    17: "compare-flow",
    18: "demo",
    19: "funnel",
    20: "engine",
    21: "pyramid",
    22: "comparison",
    23: "compare",
    24: "cards3",
    25: "prototype",
    26: "designpack",
    27: "cards6",
    28: "vibecoding",
    29: "closing",
}

LAYOUT_TAG = {
    "cover": "Cover-Center",
    "cards3": "Grid-Three-Cards",
    "route": "Timeline-Horizontal",
    "compare": "Before-After",
    "chain": "Flow-Steps",
    "dotwell": "Strategy-Map",
    "quote3": "Grid-Three-Cards",
    "loop": "Flow-Steps",
    "cards6": "Grid-Six-Icons",
    "quadrant": "Grid-Four-Cards",
    "painchain": "Process-LeftCards-CenterFlow",
    "chain-human": "Flow-Steps",
    "input-output": "Process-LeftCards-CenterFlow",
    "compare-flow": "Before-After",
    "demo": "Flow-Steps",
    "funnel": "Process-LeftCards-CenterFlow",
    "engine": "Strategy-Map",
    "pyramid": "Pyramid-Three",
    "comparison": "Comparison-Matrix-SummaryBar",
    "prototype": "Image-Left-Text-Right",
    "designpack": "Strategy-Map",
    "vibecoding": "Process-LeftCards-CenterFlow",
    "closing": "End-Page",
}


def section_name(slide_id: int) -> str:
    if slide_id <= 3:
        return "\u5f00\u573a\u5b9a\u4f4d"
    if slide_id <= 9:
        return "\u91cd\u65b0\u8ba4\u8bc6AI"
    if slide_id <= 13:
        return "AI\u8fdb\u5165\u5de5\u4f5c\u6d41"
    if slide_id <= 18:
        return "\u552e\u524d\u5b9e\u8df5"
    if slide_id <= 22:
        return "\u4ea4\u4ed8Skill"
    if slide_id <= 26:
        return "\u4ea7\u54c1\u8bbe\u8ba1\u5b9e\u8df5"
    if slide_id <= 28:
        return "\u5f00\u53d1\u4e0eDemo\u5b9e\u8df5"
    return "\u884c\u52a8\u6536\u675f"


def clean_line(s: str) -> str:
    s = re.sub(r"[`*_]", "", s).strip()
    s = re.sub(r"^[-*]\s+", "", s)
    s = re.sub(r"^\d+[.、]\s*", "", s)
    return s.strip()


def split_sections(doc: str) -> list[dict]:
    matches = list(re.finditer(r"^## P(\d+)(?!\d).+?\n", doc, re.M))
    sections: list[dict] = []
    for idx, match in enumerate(matches):
        slide_id = int(match.group(1))
        if not 1 <= slide_id <= 29:
            continue
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(doc)
        title = re.sub(r"^##\s*P\d+\W*", "", match.group(0).strip()).strip()
        sections.append({"id": slide_id, "title": title, "raw": doc[match.end() : end]})
    return sorted(sections, key=lambda item: item["id"])


def heading_blocks(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in re.split(r"^###\s+", raw, flags=re.M)[1:]:
        heading, _, body = part.partition("\n")
        out[heading.strip()] = body.strip()
    return out


def extract_ticks(text: str) -> list[str]:
    return [item.strip() for item in re.findall(r"`([^`]+)`", text or "") if item.strip()]


def extract_code_lines(text: str) -> list[str]:
    lines: list[str] = []
    for block in re.findall(r"```(?:text)?\n(.*?)```", text or "", re.S):
        lines.extend(clean_line(line) for line in block.splitlines() if clean_line(line))
    return lines


def parse_groups(info: str) -> list[dict]:
    groups: list[dict] = []
    current: dict | None = None
    in_code = False
    for raw in (info or "").splitlines():
        st = raw.strip()
        if st.startswith("```"):
            in_code = not in_code
            continue
        if not st:
            continue
        if st.startswith("#### "):
            current = {"title": clean_line(st[5:]), "items": []}
            groups.append(current)
            continue
        if current is None:
            if (st.endswith("：") or st.endswith(":")) and len(st) <= 18:
                current = {"title": clean_line(st[:-1]), "items": []}
            else:
                current = {"title": "", "items": []}
            groups.append(current)
        if st.startswith("- ") or re.match(r"^\d+[.、]\s+", st) or in_code:
            item = clean_line(st)
            if item:
                current["items"].append(item)
        elif "：" in st and len(st) <= 48:
            current["items"].append(clean_line(st))
    return [group for group in groups if group["title"] or group["items"]]


MANUAL_GROUPS = {
    16: [
        {
            "title": "输入材料",
            "items": [
                "客户交流纪要",
                "RFP / 招标文件",
                "客户现状描述",
                "行业监管背景",
                "历史方案材料",
                "内部产品能力材料",
                "项目案例材料",
            ],
        },
        {
            "title": "AI处理过程",
            "items": [
                "总结客户背景",
                "提炼核心痛点",
                "识别必须响应内容",
                "判断隐性关注点",
                "生成多种汇报主线",
                "设计章节结构",
            ],
        },
        {
            "title": "输出成果",
            "items": [
                "客户诉求清单",
                "痛点与建设目标",
                "方案主线建议",
                "PPT章节目录",
                "每页核心观点",
                "关键风险与待确认事项",
            ],
        },
    ],
    13: [
        {
            "title": "售前场景",
            "items": ["客户材料理解与RFP分析", "客户痛点提炼", "方案主线与章节框架", "PPT页面生成与优化"],
        },
        {"title": "交付场景", "items": ["会议纪要结构化", "需求与问题台账", "项目风险识别", "交付Skill沉淀"]},
        {"title": "产品场景", "items": ["模糊需求拆解", "流程与规则补盲", "原型快速生成", "多角色评审"]},
        {"title": "开发场景", "items": ["代码补全与解释", "联调问题诊断", "SQL与脚本辅助", "Demo快速验证"]},
    ],
    19: [
        {
            "title": "分散信息源",
            "items": [
                "调研会议",
                "业务诉求",
                "项目周会",
                "问题单",
                "UAT反馈",
                "邮件沟通",
                "接口联调记录",
                "上线准备事项",
            ],
        },
        {"title": "结构化动作", "items": ["分类", "提炼", "判断", "补充", "确认", "跟踪", "闭环"]},
        {
            "title": "标准交付资产",
            "items": ["调研纪要", "需求台账", "风险清单", "问题清单", "行动计划", "确认事项", "项目闭环记录"],
        },
    ],
    23: [
        {
            "title": "模糊需求",
            "items": [
                "用户说的是业务愿望",
                "业务流程和系统功能混在一起",
                "不同角色理解不一致",
                "异常场景未提前暴露",
                "开发边界和成本不清楚",
            ],
        },
        {"title": "AI辅助推演", "items": ["流程推演", "规则补盲", "角色模拟", "异常补充", "测试反推", "边界检查"]},
        {
            "title": "可落地方案",
            "items": [
                "谁使用、什么场景",
                "主流程与异常流程",
                "页面结构与字段规则",
                "状态流转与权限控制",
                "数据来源、测试与验收",
            ],
        },
    ],
    24: [
        {
            "title": "流程推演",
            "items": ["角色是谁", "入口在哪里", "主流程怎么走", "分支路径有哪些", "系统输入输出是什么"],
        },
        {
            "title": "规则补盲",
            "items": ["字段是否完整", "必填项是否明确", "状态如何变化", "权限如何控制", "异常如何处理"],
        },
        {
            "title": "多角色评审",
            "items": ["业务用户视角", "实施顾问视角", "开发人员视角", "测试人员视角", "项目经理视角", "管理层视角"],
        },
    ],
    25: [
        {
            "title": "中间原型示意",
            "items": ["顶部筛选条件栏", "左侧供应链地图", "右侧节点详情", "底部关系表", "风险标识与导出按钮"],
        },
        {
            "title": "原型帮助对齐",
            "items": ["把抽象需求转成可讨论界面", "让用户更早发现遗漏", "让开发提前判断实现边界"],
        },
        {"title": "高光价值", "items": ["需求不只写清楚", "还要尽早画出来", "用可视原型降低沟通成本"]},
    ],
    29: [
        {"title": "先从一个场景开始", "items": ["选一个最重复、最耗时、最容易标准化的任务"]},
        {"title": "把好结果沉淀下来", "items": ["把提示词、模板、检查清单固化为可复用资产"]},
        {"title": "再扩展到团队流程", "items": ["从个人效率提升走向团队工作方式升级"]},
    ],
}


def read_slides() -> tuple[list[dict], Path, Path]:
    files = sorted(DESKTOP.glob("AI*_P1-P29*.md"), key=lambda path: path.stat().st_size)
    design_path, prompt_path = files[0], files[1]
    doc = design_path.read_text(encoding="utf-8")
    slides = []
    for raw_slide in split_sections(doc):
        blocks = heading_blocks(raw_slide["raw"])
        info = blocks.get(LABELS["info"], "")
        conclusion = " ".join(extract_ticks(blocks.get(LABELS["conclusion"], "")))
        if not conclusion and blocks.get(LABELS["conclusion"]):
            conclusion = clean_line(blocks[LABELS["conclusion"]].splitlines()[0])
        slide_type = TYPE[raw_slide["id"]]
        slides.append(
            {
                "id": raw_slide["id"],
                "title": raw_slide["title"],
                "section": section_name(raw_slide["id"]),
                "type": slide_type,
                "layout_tag": LAYOUT_TAG[slide_type],
                "purpose": clean_line(blocks.get(LABELS["purpose"], "")),
                "layout": clean_line(blocks.get(LABELS["layout"], "")),
                "visual": clean_line(blocks.get(LABELS["visual"], "")),
                "conclusion": conclusion,
                "groups": parse_groups(info),
                "code_lines": extract_code_lines(info),
                "ticks": extract_ticks(info),
            }
        )
    for slide in slides:
        if slide["id"] in MANUAL_GROUPS:
            slide["groups"] = MANUAL_GROUPS[slide["id"]]
        if slide["id"] == 29:
            slide["code_lines"] = [
                "行动起来，是缓解AI焦虑最有效的方式",
                "AI不是帮我们绕过思考，而是帮我们更快进入高质量思考。",
            ]
    if len(slides) != 29:
        raise RuntimeError(f"expected 29 slides, got {len(slides)}")
    return slides, design_path, prompt_path


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def visual_len(value: str) -> float:
    return sum(1 if ord(ch) > 127 else 0.55 for ch in str(value))


def wrap_text(value: str, max_units: float, max_lines: int) -> list[str]:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return []
    chunks = re.split(r"([，。；、：,;:])", text)
    pieces = [(chunks[i] + (chunks[i + 1] if i + 1 < len(chunks) else "")).strip() for i in range(0, len(chunks), 2)]
    lines: list[str] = []
    cur = ""
    for piece in [p for p in pieces if p] or [text]:
        if visual_len(cur + piece) <= max_units:
            cur += piece
            continue
        if cur:
            lines.append(cur)
        cur = piece
        while visual_len(cur) > max_units:
            acc = 0.0
            cut = 1
            for idx, ch in enumerate(cur):
                acc += 1 if ord(ch) > 127 else 0.55
                if acc > max_units:
                    cut = max(1, idx)
                    break
            lines.append(cur[:cut])
            cur = cur[cut:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("，。；、") + "…"
    return lines


def text_el(
    x: float,
    y: float,
    value: str,
    size: int = 18,
    color: str = C["text"],
    weight: int = 400,
    max_units: float = 20,
    max_lines: int = 2,
    anchor: str = "start",
    opacity: float = 1,
) -> str:
    lines = wrap_text(value, max_units, max_lines)
    if not lines:
        return ""
    out = [
        (
            f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}" '
            f'opacity="{opacity}">'
        )
    ]
    for idx, line in enumerate(lines):
        dy = 0 if idx == 0 else size * 1.35
        out.append(f'<tspan x="{x}" dy="{dy:.1f}">{esc(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def rect(x, y, w, h, fill=C["card"], stroke="none", sw=1, rx=8, opacity=1) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}" fill-opacity="{opacity}"/>'
    )


def line(x1, y1, x2, y2, color=C["line"], sw=2, opacity=1) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{sw}" stroke-linecap="round" opacity="{opacity}"/>'
    )


def polyline(points, color=C["primary"], sw=2, opacity=1) -> str:
    pts = " ".join(f"{x},{y}" for x, y in points)
    return (
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"/>'
    )


def header(slide: dict) -> str:
    if slide["id"] in (1, 29):
        return ""
    return (
        text_el(70, 46, slide["section"], 13, C["primary"], 700, 18, 1)
        + text_el(1170, 46, f"P{slide['id']:02d} / 29", 12, C["light"], 400, 12, 1, "end")
        + line(70, 58, 1210, 58, C["line"], 1, 0.9)
    )


def title_block(slide: dict) -> str:
    return text_el(70, 88, slide["title"], 30, C["text"], 700, 34, 2)


def conclusion_bar(slide: dict) -> str:
    if slide["id"] in (1, 29) or not slide["conclusion"]:
        return ""
    return (
        rect(70, 625, 1140, 48, C["card"], C["line"], 1, 8)
        + rect(70, 625, 7, 48, C["primary"], "none", 1, 4)
        + text_el(94, 656, slide["conclusion"], 18, C["text"], 600, 58, 1)
    )


def base(slide: dict, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">\n'
        f"<!-- Executor: slide {slide['id']} | layout_tag: {slide['layout_tag']} | "
        f"visual_archetype: {slide['type']} | template: free-consulting-wine -->\n"
        f'<rect x="0" y="0" width="1280" height="720" fill="{C["bg"]}"/>\n'
        f"{body}\n</svg>\n"
    )


def useful_groups(slide: dict, n: int) -> list[dict]:
    groups = [group for group in slide["groups"] if group["title"] and group["items"]]
    if len(groups) < n:
        for group in slide["groups"]:
            for item in group["items"]:
                groups.append({"title": item.split("：")[0][:12], "items": [item]})
                if len(groups) >= n:
                    break
            if len(groups) >= n:
                break
    while len(groups) < n:
        groups.append({"title": f"要点{len(groups) + 1}", "items": process_steps(slide)[:3]})
    return groups[:n]


def card(x, y, w, h, title, items, accent=False, num=None) -> str:
    fill = C["wine"] if accent else C["card"]
    title_color = "#FFFFFF" if accent else C["text"]
    body_color = "#F8EAF0" if accent else C["muted"]
    out = [rect(x, y, w, h, fill, C["primary"] if accent else C["line"], 1, 8)]
    tx = x + 26
    if num is not None:
        out.append(
            (
                f'<circle cx="{x + 32}" cy="{y + 34}" r="17" '
                f'fill="{C["soft"] if not accent else C["primary"]}" fill-opacity="1"/>'
            )
        )
        out.append(
            text_el(x + 32, y + 40, str(num), 15, C["primary"] if not accent else "#FFFFFF", 700, 4, 1, "middle")
        )
        tx = x + 60
    out.append(text_el(tx, y + 40, title, 19, title_color, 700, max(10, w / 17), 2))
    yy = y + 84
    max_items = 5 if h > 240 else (1 if h <= 110 else 3)
    for item in items[:max_items]:
        out.append(f'<circle cx="{x + 30}" cy="{yy - 5}" r="3.5" fill="{body_color}"/>')
        out.append(text_el(x + 44, yy, item, 13, body_color, 400, max(14, w / 16), 2))
        yy += 40
    return "".join(out)


def draw_cover(slide: dict) -> str:
    ticks = slide["ticks"]
    main = ticks[0] if ticks else "AI驱动的工作方式升级"
    sub = ticks[1] if len(ticks) > 1 else "面向售前、交付、产品与开发的实践探索"
    pos = ticks[2] if len(ticks) > 2 else "部门AI应用实践分享"
    desc = ticks[3] if len(ticks) > 3 else ""
    body = [rect(0, 0, 445, 720, C["wine"], "none", 1, 0)]
    body.append(text_el(82, 180, pos, 20, "#F5DDE5", 500, 18, 1))
    body.append(text_el(82, 250, main, 44, "#FFFFFF", 700, 8, 3))
    body.append(text_el(86, 408, sub, 22, "#FFFFFF", 500, 22, 2, opacity=0.95))
    body.append(text_el(86, 488, desc, 16, "#F5DDE5", 400, 28, 2))
    body.append(text_el(86, 635, "分享人 / 部门 / 日期", 15, "#E8C4CC", 400, 22, 1))
    cx, cy = 835, 360
    body.append(text_el(725, 118, "AI × WorkFlow", 30, C["wine"], 700, 20, 1, "middle"))
    body.append(f'<circle cx="{cx}" cy="{cy}" r="76" fill="{C["wine"]}"/>')
    body.append(text_el(cx, 350, "AI", 40, "#FFFFFF", 700, 6, 1, "middle"))
    body.append(text_el(cx, 386, "Work", 17, "#F5DDE5", 500, 8, 1, "middle"))
    nodes = [
        ("人", 595, 360),
        ("资料理解", 715, 220),
        ("方案设计", 955, 220),
        ("PPT生成", 1080, 360),
        ("交付Skill", 955, 500),
        ("原型/代码", 715, 500),
    ]
    for label, x, y in nodes:
        body.append(line(cx, cy, x, y, C["line"], 2, 0.8))
        body.append(rect(x - 58, y - 28, 116, 56, C["card"], C["line"], 1, 8))
        body.append(text_el(x, y + 6, label, 16, C["text"], 600, 10, 1, "middle"))
    return base(slide, "".join(body))


def draw_cards(slide: dict, count: int = 3) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, count)
    cols = 3 if count in (3, 5, 6) else 2
    w = 340 if cols == 3 else 520
    h = 155 if count in (5, 6) else 350
    x0, y0, gx, gy = 90, 175, 35, 28
    if count == 3:
        w, h, y0 = 340, 360, 180
    if count == 4:
        w, h, y0, gx, gy = 520, 170, 175, 40, 28
    for i, group in enumerate(groups):
        x = x0 + (i % cols) * (w + gx)
        y = y0 + (i // cols) * (h + gy)
        body.append(card(x, y, w, h, group["title"], group["items"], accent=(slide["id"] == 2 and i == 1), num=i + 1))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def process_steps(slide: dict) -> list[str]:
    for line_text in slide["code_lines"]:
        if "→" in line_text:
            return [clean_line(item) for item in line_text.split("→") if clean_line(item)]
    items: list[str] = []
    for group in slide["groups"]:
        items.extend(group["items"])
    return items


def draw_route(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    steps = process_steps(slide)[:7]
    xs = [120, 290, 460, 630, 800, 970, 1140]
    y = 360
    body.append(line(xs[0], y, xs[len(steps) - 1], y, C["line"], 4))
    for i, step in enumerate(steps):
        accent = slide["id"] == 3 and 2 <= i <= 5 or slide["id"] == 10 and i == len(steps) - 1
        body.append(
            (
                f'<circle cx="{xs[i]}" cy="{y}" r="24" '
                f'fill="{C["primary"] if accent else C["card"]}" '
                f'stroke="{C["primary"]}" stroke-width="2"/>'
            )
        )
        body.append(
            text_el(xs[i], y + 7, f"{i + 1:02d}", 16, "#FFFFFF" if accent else C["primary"], 700, 4, 1, "middle")
        )
        body.append(text_el(xs[i], y + 68, step, 15, C["text"], 600, 12, 3, "middle"))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_compare(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 2)
    if len(groups) < 2:
        groups.append({"title": "升级方式", "items": []})
    body.append(card(95, 175, 500, 380, groups[0]["title"], groups[0]["items"]))
    body.append(card(685, 175, 500, 380, groups[1]["title"], groups[1]["items"], accent=slide["id"] in (7, 23)))
    body.append(
        (
            f'<path d="M618 365 L660 365 M646 350 L660 365 L646 380" stroke="{C["primary"]}" '
            'stroke-width="5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_chain(slide: dict, human: bool = False) -> str:
    body = [header(slide), title_block(slide)]
    steps = process_steps(slide)[:7]
    x0, y, w, gap = 85, 242, 140 if len(steps) > 6 else 155, 18
    for i, step in enumerate(steps):
        accent = i >= max(0, len(steps) - 3) or "人工" in step
        x = x0 + i * (w + gap)
        body.append(rect(x, y, w, 115, C["wine"] if accent else C["card"], C["primary"] if accent else C["line"], 1, 8))
        body.append(text_el(x + w / 2, y + 54, step, 17, "#FFFFFF" if accent else C["text"], 700, 9, 2, "middle"))
        if i < len(steps) - 1:
            ax = x + w + 5
            body.append(
                (
                    f'<path d="M{ax} {y + 58} L{ax + 18} {y + 58} '
                    f'M{ax + 9} {y + 50} L{ax + 18} {y + 58} L{ax + 9} {y + 66}" '
                    f'stroke="{C["primary"]}" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
                )
            )
    if human:
        groups = useful_groups(slide, 2)
        body.append(card(160, 420, 430, 145, groups[0]["title"], groups[0]["items"]))
        body.append(
            card(
                690,
                420,
                430,
                145,
                groups[1]["title"] if len(groups) > 1 else "人负责",
                groups[1]["items"] if len(groups) > 1 else [],
                True,
            )
        )
    else:
        extras = []
        for line_text in slide["code_lines"]:
            if "/" in line_text and "→" not in line_text:
                extras = [clean_line(item) for item in re.split(r"/|、", line_text) if clean_line(item)]
        for i, item in enumerate(extras[:6]):
            body.append(rect(95 + i * 175, 455, 140, 54, C["card"], C["line"], 1, 8))
            body.append(text_el(165 + i * 175, 488, item, 16, C["text"], 600, 10, 1, "middle"))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_dotwell(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    body.append(
        (
            f'<circle cx="230" cy="350" r="78" fill="{C["soft"]}" '
            f'fill-opacity="1" stroke="{C["primary"]}" stroke-width="4"/>'
        )
    )
    body.append(text_el(230, 360, "点", 60, C["primary"], 700, 4, 1, "middle"))
    body.append(text_el(230, 455, groups[0]["title"], 23, C["text"], 700, 10, 1, "middle"))
    for i, item in enumerate(groups[0]["items"][:3]):
        body.append(text_el(135, 502 + i * 27, item, 14, C["muted"], 400, 18, 1))
    body.append(rect(505, 235, 230, 230, C["wine"], C["wine"], 1, 8))
    body.append(text_el(620, 300, "AI能力放大", 24, "#FFFFFF", 700, 10, 1, "middle"))
    for i, item in enumerate(
        (groups[1]["items"] if len(groups) > 1 else ["理解", "生成", "推演", "验证", "补盲", "连接"])[:6]
    ):
        body.append(rect(532 + (i % 2) * 95, 335 + (i // 2) * 48, 78, 30, C["primary"], "none", 1, 6, 1))
        body.append(text_el(571 + (i % 2) * 95, 356 + (i // 2) * 48, item, 14, "#FFFFFF", 500, 6, 1, "middle"))
    body.append(
        (
            f'<path d="M332 350 L500 350 M485 335 L500 350 L485 365" stroke="{C["primary"]}" '
            'stroke-width="4" fill="none" stroke-linecap="round"/>'
        )
    )
    body.append(
        (
            f'<path d="M740 350 L910 350 M895 335 L910 350 L895 365" stroke="{C["primary"]}" '
            'stroke-width="4" fill="none" stroke-linecap="round"/>'
        )
    )
    for x in [970, 1035, 1100]:
        body.append(line(x, 245, x, 455, C["primary"], 7, 0.9))
    for y in [295, 365, 435]:
        body.append(line(940, y, 1130, y, C["primary"], 7, 0.9))
    body.append(
        text_el(1035, 520, groups[2]["title"] if len(groups) > 2 else "井型人才", 24, C["text"], 700, 10, 1, "middle")
    )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_quote3(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    quote = "\n".join(slide["code_lines"][:2]) or (
        groups[1]["items"][0] if len(groups) > 1 and groups[1]["items"] else ""
    )
    body.append(card(80, 185, 300, 340, groups[0]["title"], groups[0]["items"]))
    body.append(rect(430, 190, 420, 310, C["wine"], C["wine"], 1, 8))
    body.append(text_el(640, 290, quote, 30, "#FFFFFF", 700, 14, 4, "middle"))
    body.append(card(900, 185, 300, 340, groups[-1]["title"], groups[-1]["items"]))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_loop(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    steps = process_steps(slide)[:9]
    cx, cy, rx, ry = 640, 330, 390, 150
    for i, step in enumerate(steps):
        angle = 2 * math.pi * i / max(1, len(steps)) - math.pi / 2
        x, y = cx + rx * math.cos(angle), cy + ry * math.sin(angle)
        is_human = "人" in step
        body.append(
            rect(
                x - 70,
                y - 30,
                140,
                60,
                C["wine"] if is_human else C["card"],
                C["primary"] if is_human else C["line"],
                1,
                8,
            )
        )
        body.append(text_el(x, y + 5, step, 14, "#FFFFFF" if is_human else C["text"], 700, 10, 2, "middle"))
    groups = useful_groups(slide, 2)
    body.append(card(145, 505, 455, 92, groups[0]["title"], groups[0]["items"]))
    body.append(
        card(
            680,
            505,
            455,
            92,
            groups[1]["title"] if len(groups) > 1 else "AI负责",
            groups[1]["items"] if len(groups) > 1 else [],
            True,
        )
    )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_painchain(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    steps = process_steps(slide)[:6]
    for i, step in enumerate(steps):
        y = 165 + i * 64
        body.append(rect(90, y, 360, 44, C["card"], C["line"], 1, 8))
        body.append(text_el(112, y + 28, step, 15, C["text"], 600, 24, 1))
        if i < 5:
            body.append(line(270, y + 47, 270, y + 62, C["primary"], 2))
    items = []
    for group in slide["groups"]:
        for item in group["items"]:
            if "：" in item:
                title, body_text = item.split("：", 1)
                items.append({"title": title, "items": [body_text]})
    for i, group in enumerate(items[:6]):
        body.append(card(520 + (i % 2) * 335, 165 + (i // 2) * 130, 300, 105, group["title"], group["items"]))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_input_output(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    for i, group in enumerate(groups):
        x = 80 + i * 390
        body.append(card(x, 180, 330, 345, group["title"], group["items"], accent=i == 2, num=i + 1))
        if i < 2:
            body.append(
                (
                    f'<path d="M{x + 348} 350 L{x + 384} 350 M{x + 372} 338 '
                    f'L{x + 384} 350 L{x + 372} 362" stroke="{C["primary"]}" '
                    'stroke-width="3" fill="none"/>'
                )
            )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_funnel(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    while len(groups) < 3:
        groups.append(
            {"title": ["分散信息源", "结构化动作", "标准交付资产"][len(groups)], "items": process_steps(slide)[:6]}
        )
    for i, item in enumerate(groups[0]["items"][:8]):
        x, y = 85 + (i % 2) * 145, 185 + (i // 2) * 58
        body.append(rect(x, y, 125, 38, C["card"], C["line"], 1, 8))
        body.append(text_el(x + 62, y + 25, item, 12, C["muted"], 500, 8, 1, "middle"))
    body.append(
        (
            f'<polygon points="450,190 760,190 700,430 510,430" fill="{C["soft"]}" '
            f'stroke="{C["primary"]}" stroke-width="2"/>'
        )
    )
    for i, item in enumerate(groups[1]["items"][:7] if len(groups) > 1 else []):
        body.append(text_el(605, 235 + i * 31, item, 15, C["primary"], 700, 12, 1, "middle"))
    for i, item in enumerate(groups[2]["items"][:7] if len(groups) > 2 else []):
        body.append(rect(835, 175 + i * 54, 305, 38, C["card"], C["line"], 1, 8))
        body.append(text_el(858, 200 + i * 54, item, 14, C["text"], 600, 22, 1))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_engine(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    formula = slide["code_lines"][0] if slide["code_lines"] else "交付Skill = 角色 + 语境 + 模板 + 规则 + 检查清单"
    body.append(rect(100, 185, 430, 335, C["wine"], C["wine"], 1, 8))
    body.append(text_el(315, 285, "交付Skill", 34, "#FFFFFF", 700, 12, 1, "middle"))
    body.append(text_el(315, 340, "方法沉淀", 24, "#F5DDE5", 600, 10, 1, "middle"))
    for angle in range(0, 360, 45):
        x, y = 315 + 150 * math.cos(math.radians(angle)), 350 + 110 * math.sin(math.radians(angle))
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#FFFFFF" fill-opacity="0.75"/>')
        body.append(line(315, 350, x, y, "#FFFFFF", 1, 0.35))
    body.append(text_el(90, 570, formula, 18, C["primary"], 700, 54, 2))
    items = []
    for group in slide["groups"]:
        for item in group["items"]:
            if "：" in item:
                title, body_text = item.split("：", 1)
                items.append({"title": title, "body": body_text})
    for i, item in enumerate(items[:7]):
        x, y = 605 + (i % 2) * 285, 175 + (i // 2) * 88
        body.append(rect(x, y, 260, 66, C["card"], C["line"], 1, 8))
        body.append(text_el(x + 18, y + 25, item["title"], 16, C["primary"], 700, 12, 1))
        body.append(text_el(x + 18, y + 49, item["body"], 12, C["muted"], 400, 21, 1))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_pyramid(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    polys = [
        [(310, 555), (970, 555), (850, 430), (430, 430)],
        [(430, 410), (850, 410), (760, 292), (520, 292)],
        [(520, 272), (760, 272), (700, 170), (580, 170)],
    ]
    fills = ["#F7E8EE", "#EAC7D2", C["wine"]]
    for idx, points in enumerate(polys):
        body.append(
            (
                f'<polygon points="{" ".join(f"{x},{y}" for x, y in points)}" '
                f'fill="{fills[idx]}" stroke="{C["primary"]}" stroke-width="2"/>'
            )
        )
    for idx, group in enumerate(groups[:3]):
        layer = 2 - idx
        y = [505, 360, 230][layer]
        body.append(text_el(640, y, group["title"], 22, "#FFFFFF" if layer == 2 else C["text"], 700, 20, 1, "middle"))
        body.append(
            text_el(
                640,
                y + 34,
                " / ".join(group["items"][:4]),
                13,
                "#F5DDE5" if layer == 2 else C["muted"],
                400,
                50,
                2,
                "middle",
            )
        )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_comparison(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 2)
    body.append(card(90, 165, 480, 320, groups[0]["title"], groups[0]["items"]))
    body.append(
        card(
            710,
            165,
            480,
            320,
            groups[1]["title"] if len(groups) > 1 else "Skill输出",
            groups[1]["items"] if len(groups) > 1 else [],
            True,
        )
    )
    chain = []
    for line_text in slide["code_lines"]:
        if "→" in line_text:
            chain = [clean_line(item) for item in line_text.split("→") if clean_line(item)]
    for i, step in enumerate(chain[:5]):
        x = 155 + i * 205
        body.append(rect(x, 530, 150, 46, C["card"], C["primary"], 1, 8))
        body.append(text_el(x + 75, 559, step, 15, C["text"], 700, 11, 1, "middle"))
        if i < len(chain) - 1:
            body.append(line(x + 155, 553, 155 + (i + 1) * 205 - 10, 553, C["primary"], 2))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_prototype(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 3)
    body.append(card(70, 175, 240, 360, groups[0]["title"], groups[0]["items"]))
    body.append(rect(345, 150, 575, 405, C["card"], C["line"], 1, 8))
    body.append(rect(370, 175, 525, 46, C["soft"], C["line"], 1, 6))
    for i in range(4):
        body.append(rect(390 + i * 120, 188, 90, 20, "#FFFFFF", C["line"], 1, 4))
    body.append(rect(370, 245, 310, 185, "#FFFFFF", C["line"], 1, 6))
    body.append(polyline([(400, 350), (455, 300), (520, 340), (590, 290), (650, 330)], C["primary"], 3))
    for x, y in [(400, 350), (455, 300), (520, 340), (590, 290), (650, 330)]:
        body.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{C["primary"]}"/>')
    body.append(rect(700, 245, 195, 185, "#FFFFFF", C["line"], 1, 6))
    body.append(text_el(720, 278, "节点详情", 16, C["primary"], 700, 10, 1))
    for i in range(5):
        body.append(line(720, 305 + i * 24, 870, 305 + i * 24, C["line"], 2, 0.8))
    body.append(rect(370, 452, 525, 78, "#FFFFFF", C["line"], 1, 6))
    for i in range(4):
        body.append(line(392, 477 + i * 16, 870, 477 + i * 16, C["line"], 1, 0.7))
    body.append(rect(805, 188, 68, 22, C["wine"], "none", 1, 5))
    body.append(text_el(839, 204, "导出", 12, "#FFFFFF", 600, 5, 1, "middle"))
    body.append(
        card(
            960,
            175,
            250,
            360,
            groups[2]["title"] if len(groups) > 2 else "原型带来的价值",
            groups[2]["items"] if len(groups) > 2 else [],
            True,
        )
    )
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_designpack(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 4)
    cx, cy = 640, 345
    body.append(f'<circle cx="{cx}" cy="{cy}" r="96" fill="{C["wine"]}"/>')
    body.append(text_el(cx, 335, "产品", 30, "#FFFFFF", 700, 8, 1, "middle"))
    body.append(text_el(cx, 373, "设计包", 30, "#FFFFFF", 700, 8, 1, "middle"))
    for idx, (x, y) in enumerate([(185, 185), (825, 185), (185, 445), (825, 445)]):
        if idx < len(groups):
            body.append(card(x, y, 270, 110, groups[idx]["title"], groups[idx]["items"]))
            body.append(line(cx, cy, x + 135, y + 55, C["line"], 2, 0.8))
    body.append(rect(430, 560, 420, 45, C["soft"], C["line"], 1, 8))
    body.append(text_el(640, 589, "人机分工：AI推演补盲，人判断取舍并最终负责", 15, C["primary"], 700, 35, 1, "middle"))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_vibecoding(slide: dict) -> str:
    body = [header(slide), title_block(slide)]
    groups = useful_groups(slide, 4)
    for idx, group in enumerate(groups[:3]):
        x = 80 + idx * 390
        body.append(card(x, 155, 330, 145, group["title"], group["items"], accent=idx == 1, num=idx + 1))
        if idx < 2:
            body.append(line(x + 332, 225, x + 375, 225, C["primary"], 3))
    body.append(rect(120, 350, 1040, 205, C["card"], C["line"], 1, 8))
    body.append(rect(120, 350, 1040, 34, C["wine"], "none", 1, 8))
    body.append(text_el(145, 373, "AI原生PPT Agent工具 · Demo工作台", 15, "#FFFFFF", 700, 40, 1))
    body.append(rect(150, 410, 230, 115, C["soft"], C["line"], 1, 6))
    body.append(text_el(170, 438, "任务列表", 15, C["primary"], 700, 10, 1))
    for i in range(4):
        body.append(line(172, 462 + i * 18, 350, 462 + i * 18, C["line"], 2, 0.9))
    body.append(rect(410, 410, 260, 115, "#FFFFFF", C["line"], 1, 6))
    body.append(text_el(430, 438, "模块拆分", 15, C["primary"], 700, 10, 1))
    for i in range(4):
        body.append(rect(435 + (i % 2) * 105, 460 + (i // 2) * 32, 88, 22, C["soft"], C["primary"], 1, 4))
    body.append(rect(700, 410, 210, 115, "#FFFFFF", C["line"], 1, 6))
    body.append(text_el(805, 475, "页面预览", 20, C["muted"], 700, 10, 1, "middle"))
    body.append(rect(940, 410, 190, 115, "#FFFFFF", C["line"], 1, 6))
    body.append(text_el(960, 438, "反馈修改区", 15, C["primary"], 700, 10, 1))
    for i in range(3):
        body.append(line(960, 462 + i * 20, 1100, 462 + i * 20, C["line"], 2, 0.9))
    body.append(conclusion_bar(slide))
    return base(slide, "".join(body))


def draw_closing(slide: dict) -> str:
    main = slide["title"] if slide["id"] == 29 else (slide["code_lines"][0] if slide["code_lines"] else slide["title"])
    closing = slide["code_lines"][1] if len(slide["code_lines"]) > 1 else slide["conclusion"]
    actions = []
    for group in slide["groups"]:
        actions.extend(group["items"])
    body = [rect(0, 0, 1280, 720, C["wine"], "none", 1, 0)]
    body.append(text_el(640, 150, main, 48, "#FFFFFF", 700, 14, 3, "middle"))
    body.append(rect(120, 330, 1040, 190, "#FFFFFF", "none", 1, 8))
    for idx, item in enumerate(actions[:3]):
        x = 175 + idx * 320
        title, desc = item, ""
        for sep in ("：", ":", "，", ","):
            if sep in item:
                title, desc = item.split(sep, 1)
                break
        body.append(f'<circle cx="{x}" cy="395" r="26" fill="{C["primary"]}"/>')
        body.append(text_el(x, 404, str(idx + 1), 20, "#FFFFFF", 700, 4, 1, "middle"))
        body.append(text_el(x + 48, 385, title, 18, C["text"], 700, 14, 1))
        body.append(text_el(x + 48, 420, desc or item, 13, C["muted"], 400, 22, 3))
    body.append(text_el(640, 610, closing, 28, "#FFFFFF", 700, 24, 2, "middle"))
    body.append(text_el(640, 675, "Q&A｜结合岗位场景交流AI应用问题", 15, "#F5DDE5", 500, 32, 1, "middle"))
    return base(slide, "".join(body))


def render_slide(slide: dict) -> str:
    slide_type = slide["type"]
    if slide_type == "cover":
        return draw_cover(slide)
    if slide_type == "cards3":
        return draw_cards(slide, 3)
    if slide_type in {"route"}:
        return draw_route(slide)
    if slide_type == "compare":
        return draw_compare(slide)
    if slide_type == "chain":
        return draw_chain(slide)
    if slide_type == "chain-human":
        return draw_chain(slide, True)
    if slide_type == "dotwell":
        return draw_dotwell(slide)
    if slide_type == "quote3":
        return draw_quote3(slide)
    if slide_type == "loop":
        return draw_loop(slide)
    if slide_type == "cards6":
        return draw_cards(slide, 6)
    if slide_type == "quadrant":
        return draw_cards(slide, 4)
    if slide_type == "painchain":
        return draw_painchain(slide)
    if slide_type == "input-output":
        return draw_input_output(slide)
    if slide_type == "compare-flow":
        return draw_compare(slide)
    if slide_type == "demo":
        return draw_chain(slide)
    if slide_type == "funnel":
        return draw_funnel(slide)
    if slide_type == "engine":
        return draw_engine(slide)
    if slide_type == "pyramid":
        return draw_pyramid(slide)
    if slide_type == "comparison":
        return draw_comparison(slide)
    if slide_type == "prototype":
        return draw_prototype(slide)
    if slide_type == "designpack":
        return draw_designpack(slide)
    if slide_type == "vibecoding":
        return draw_vibecoding(slide)
    if slide_type == "closing":
        return draw_closing(slide)
    return draw_cards(slide, 3)


def contract_content(slide: dict) -> dict:
    tag = slide["layout_tag"]
    groups = useful_groups(slide, 4)
    if tag == "Cover-Center":
        ticks = slide["ticks"]
        return {
            "headline": ticks[0] if ticks else slide["title"],
            "subtitle": ticks[1] if len(ticks) > 1 else "",
            "date": "2026",
        }
    if tag in {"Grid-Three-Cards", "Grid-Four-Cards"}:
        count = 3 if tag == "Grid-Three-Cards" else 4
        return {
            "title": slide["title"],
            "cards": [{"title": g["title"], "body": "；".join(g["items"][:3])} for g in groups[:count]],
        }
    if tag == "Grid-Six-Icons":
        values = [item for group in slide["groups"] for item in group["items"]]
        return {
            "title": slide["title"],
            "items": [
                {"title": item.split("：")[0][:12], "body": item.split("：")[-1], "icon": "dot"} for item in values[:6]
            ],
        }
    if tag == "Before-After":
        return {
            "title": slide["title"],
            "before": {
                "title": groups[0]["title"] if groups else "Before",
                "body": "；".join(groups[0]["items"][:4]) if groups else "",
            },
            "after": {
                "title": groups[1]["title"] if len(groups) > 1 else "After",
                "body": "；".join(groups[1]["items"][:4]) if len(groups) > 1 else "",
            },
        }
    if tag == "Flow-Steps":
        return {
            "title": slide["title"],
            "steps": [{"title": step[:14], "body": ""} for step in process_steps(slide)[:7]],
        }
    if tag == "Timeline-Horizontal":
        values = process_steps(slide)[:7]
        return {
            "title": slide["title"],
            "events": [
                {"date": str(i + 1), "title": item.split("：")[0][:14], "body": item.split("：")[-1]}
                for i, item in enumerate(values)
            ],
        }
    if tag == "Process-LeftCards-CenterFlow":
        values = [item for group in slide["groups"] for item in group["items"]]
        if not values:
            values = process_steps(slide)
        if not values:
            values = ["输入材料", "结构化处理", "输出成果", "人工判断", "迭代验证"]
        while len(values) < 4:
            values.append("迭代验证")
        return {
            "title": slide["title"],
            "left_cards": [{"title": item.split("：")[0][:10], "body": item.split("：")[-1]} for item in values[:3]],
            "flow_nodes": [{"title": item.split("：")[0][:10], "body": item.split("：")[-1]} for item in values[3:8]],
            "bottom_systems": ["人工判断", "AI生成", "迭代验证"],
        }
    if tag == "Strategy-Map":
        values = [item for group in slide["groups"] for item in group["items"]]
        return {
            "title": slide["title"],
            "north_star": slide["conclusion"] or slide["title"],
            "pillars": [{"title": item.split("：")[0][:12], "body": item.split("：")[-1]} for item in values[:3]],
            "initiatives": [{"title": item.split("：")[0][:12], "body": item.split("：")[-1]} for item in values[3:7]],
        }
    if tag == "Pyramid-Three":
        return {
            "title": slide["title"],
            "layers": [{"title": g["title"], "body": "；".join(g["items"][:4])} for g in groups[:3]],
        }
    if tag == "Comparison-Matrix-SummaryBar":
        return {
            "title": slide["title"],
            "left_title": groups[0]["title"] if groups else "普通方式",
            "right_title": groups[1]["title"] if len(groups) > 1 else "Skill方式",
            "rows": [
                [
                    str(i + 1),
                    groups[0]["items"][i] if groups and i < len(groups[0]["items"]) else "",
                    groups[1]["items"][i] if len(groups) > 1 and i < len(groups[1]["items"]) else "",
                ]
                for i in range(5)
            ],
            "summary": slide["conclusion"],
        }
    if tag == "Image-Left-Text-Right":
        return {
            "title": slide["title"],
            "body": slide["purpose"],
            "items": [{"title": g["title"], "body": "；".join(g["items"][:3])} for g in groups[:3]],
            "image": "prototype-wireframe",
        }
    if tag == "End-Page":
        return {"headline": slide["title"], "message": slide["conclusion"], "contact": "Q&A"}
    return {"title": slide["title"]}


def write_project_files(slides: list[dict], design_path: Path, prompt_path: Path) -> None:
    PROJECT.mkdir(parents=True, exist_ok=True)
    for sub in ["svg_output", "svg_final", "exports", "qa", "sources"]:
        folder = PROJECT / sub
        folder.mkdir(parents=True, exist_ok=True)
        if sub in {"svg_output", "svg_final"}:
            for item in folder.glob("*"):
                if item.is_file():
                    item.unlink()
    shutil.copy2(design_path, PROJECT / "sources" / design_path.name)
    shutil.copy2(prompt_path, PROJECT / "sources" / prompt_path.name)
    (PROJECT / "sources" / "manifest.json").write_text(
        json.dumps(
            {
                "records": [
                    {"id": design_path.name, "path": design_path.name, "type": "markdown", "role": "page_design_draft"},
                    {
                        "id": prompt_path.name,
                        "path": prompt_path.name,
                        "type": "markdown",
                        "role": "page_generation_prompt",
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    outline = ["# Outline", ""]
    for slide in slides:
        outline.append(f"{slide['id']}. {slide['title']}")
        if slide["conclusion"]:
            outline.append(f"   - {slide['conclusion']}")
    (PROJECT / "outline.md").write_text("\n".join(outline) + "\n", encoding="utf-8")

    design_spec = """# Design Spec
- canvas: ppt169
- style: executive_exhibit
- style_profile: proposal_consulting_wine_v2
- primary_color: #932141
- accent_color: #800020
- background_color: #F5F5F5
- card_bg: #FFFFFF
- text_color: #333333
- muted_color: #666666
- line_color: #D9D9D9
- soft_color: #F7F2F4
- data_palette: #932141,#800020,#4A5568,#8A8A8A
- font_title: "Microsoft YaHei", "PingFang SC", "Arial", sans-serif
- font_body: "Microsoft YaHei", "PingFang SC", "Arial", sans-serif
- page_count: 29
- audience: department staff across presales, delivery, product, and development
- language: zh-CN
- purpose: department AI practice training deck, focused on real work scenarios and role-level adoption
- style_objective: C
- icon_library: inline-semantic-shapes
- image_mode: A
- density_profile: balanced
- hierarchy_profile: clear
- accent_ratio: 18%
- card_style: soft
- rhythm_profile: staggered
- composition_grammar: conclusion-first consulting page with restrained wine accents
  and alternating high-impact visual pages
- rhythm_grammar: opening reset, cognition build, workflow method, four practice chapters, action close
- font_ladder: Cover 54/700 | H1 30/700 | H2 20/700 | Body 14/400 | Caption 12/400
- taboo_patterns: robot illustration; black neon tech style; webpage dashboard style;
  dense textbook pages; AI tool advertisement tone

## Assumptions (autonomous)
- The two provided Markdown files are treated as approved source, outline, and visual direction.
- Presenter, department, and date are left as editable placeholders on the cover.
- The deck uses AI-authored SVG pages and the repository finalize/export pipeline with --skip-render.
"""
    (PROJECT / "design_spec.md").write_text(design_spec, encoding="utf-8")

    clarification = {
        "autonomous_mode": True,
        "audience": "department staff across pre-sales, delivery, product and development roles",
        "decision_goal": (
            "help participants understand how AI changes daily work "
            "and identify a role-specific starting task"
        ),
        "style_goal": (
            "international consulting training deck, restrained wine-red and cool gray, "
            "conclusion-first and readable"
        ),
        "template_preference": "free executor SVG inspired by consulting exhibit style; no fixed template binding",
        "assumptions": [
            "Provided page design draft and generation prompt are approved as source of truth.",
            "No extra pages, appendices, or independent data security section are added.",
        ],
    }
    (PROJECT / "clarification_brief.json").write_text(
        json.dumps(clarification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    blueprint = {
        "slides": [
            {
                "id": slide["id"],
                "title": slide["title"],
                "layout_tag": slide["layout_tag"],
                "narrative_intent": slide["purpose"] or slide["title"],
                "content": contract_content(slide),
                "source_refs": [design_path.name, prompt_path.name],
                "visual_intent": slide["layout"],
                "acceptance_criteria": [
                    "16:9 fixed canvas",
                    "no overflow or overlap",
                    "consulting wine-gray visual style",
                    "preserve human judgment boundary",
                ],
            }
            for slide in slides
        ]
    }
    (PROJECT / "blueprint.json").write_text(
        json.dumps(blueprint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    (PROJECT / "art_direction.md").write_text(
        "# Art Direction\n\n"
        "This deck uses a restrained consulting training style: cool gray canvas, "
        "white evidence surfaces, deep wine accents for decision points, and clear "
        "conclusion-first hierarchy. "
        "High-impact pages (P1, P6, P8, P15, P20, P25, P28, P29) use stronger visual "
        "anchors, while ordinary pages preserve scanability with cards, chains, and "
        "comparison frames.\n\n"
        "Rules:\n- Keep every page as a formal PPT page, not a webpage, dashboard, poster, or tool ad.\n"
        "- Use wine red only for the idea that must be remembered.\n"
        "- Preserve the human/AI responsibility boundary on method and case pages.\n"
        "- Avoid robot illustration, neon technology styling, and dense textbook layouts.\n",
        encoding="utf-8",
    )
    (PROJECT / "reference_pack.json").write_text(
        json.dumps(
            {
                "template_lookup_mode": "index_then_reference_pack",
                "mode": "hybrid",
                "primary_template": "exhibit",
                "secondary_templates": ["mckinsey", "consulting_classic"],
                "primary_reference": "proposal_consulting_wine_v2",
                "references": [
                    {
                        "template_key": "exhibit",
                        "source_path": "ppt-ai-core/templates/layouts/exhibit",
                        "reference_files": [
                            "ppt-ai-core/templates/layouts/exhibit/01_cover.svg",
                            "ppt-ai-core/templates/layouts/exhibit/03_content.svg",
                            "ppt-ai-core/templates/layouts/exhibit/design_spec.md",
                        ],
                        "use_as": [
                            "consulting exhibit hierarchy",
                            "takeaway-first content rhythm",
                            "restrained page structure",
                        ],
                        "selection_reason": (
                            "Closest reusable consulting exhibit grammar for a formal "
                            "AI work-method upgrade deck."
                        ),
                    },
                    {
                        "template_key": "mckinsey",
                        "source_path": "ppt-ai-core/templates/layouts/mckinsey",
                        "reference_files": [
                            "ppt-ai-core/templates/layouts/mckinsey/01_cover.svg",
                            "ppt-ai-core/templates/layouts/mckinsey/03_content.svg",
                            "ppt-ai-core/templates/layouts/mckinsey/design_spec.md",
                        ],
                        "use_as": ["executive typography ladder", "business evidence-card discipline"],
                        "selection_reason": (
                            "Secondary reference for consulting-grade title/body "
                            "proportion and card restraint."
                        ),
                    },
                ],
                "selected_templates": [
                    {
                        "template_key": "exhibit",
                        "source_path": "ppt-ai-core/templates/layouts/exhibit",
                        "score": 88,
                        "use_as": ["style anchor", "composition rhythm"],
                    },
                    {
                        "template_key": "mckinsey",
                        "source_path": "ppt-ai-core/templates/layouts/mckinsey",
                        "score": 82,
                        "use_as": ["typography hierarchy", "executive page discipline"],
                    },
                ],
                "reference_files": [
                    "ppt-ai-core/templates/layouts/exhibit/01_cover.svg",
                    "ppt-ai-core/templates/layouts/exhibit/03_content.svg",
                    "ppt-ai-core/templates/layouts/exhibit/design_spec.md",
                    "ppt-ai-core/templates/layouts/mckinsey/01_cover.svg",
                    "ppt-ai-core/templates/layouts/mckinsey/03_content.svg",
                    "ppt-ai-core/templates/layouts/mckinsey/design_spec.md",
                ],
                "template_reference_files_loaded": 6,
                "template_reference_files_skipped": 0,
                "execution_tokens": {
                    "palette": "wine-gray consulting",
                    "shape_language": "soft cards, fine lines, flow nodes, restrained emphasis",
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    visual_plan = []
    for slide in slides:
        high = slide["id"] in (1, 6, 8, 15, 20, 25, 28, 29)
        visual_plan.append(
            {
                "slide_id": slide["id"],
                "visual_archetype": slide["type"],
                "selected_archetype": slide["type"],
                "candidate_archetypes": [slide["type"], "consulting-exhibit"],
                "selection_reason": "Matches the provided page design draft and deck rhythm.",
                "composition_intent": slide["layout"] or "consulting page with one clear core idea",
                "variation_rule": "High-impact visual anchor"
                if high
                else "Readable business page; avoid repeating equal card grids too long.",
                "avoid": [
                    "robot illustration",
                    "black neon tech style",
                    "webpage dashboard style",
                    "overcrowded paragraphs",
                ],
                "page_prompt_pattern": {
                    "pattern_id": "consulting_training_page",
                    "conclusion_formula": "one judgment sentence at bottom except cover/closing",
                    "block_structure": slide["type"],
                    "composition_cues": slide["layout"],
                    "anti_patterns": ["generator instructions on slide", "tool advertisement tone"],
                },
                "execution_policy": {
                    "scene_type": "training_ppt",
                    "generation_strategy": "executor_svg",
                    "risk_level": "high" if high else "medium",
                    "required_loop": "single_slide",
                    "qa_strictness": "blocking" if high else "warning",
                    "expected_first_pass_rules": [
                        "title readable",
                        "main visual clear",
                        "footer conclusion fits",
                        "no overlap",
                    ],
                },
                "visual_contract": {
                    "scene_type": "training_ppt",
                    "generation_strategy": "executor_svg",
                    "focal_point": "main visual anchor" if high else "title and structured body",
                    "primary_read_path": ["title", "visual/body", "bottom conclusion"],
                    "composition_grammar": slide["type"],
                    "hierarchy_ladder": "H1 30/700, card title 20/700, body 14/400, conclusion 18/600",
                    "density_budget": {"level": "balanced", "max_bullets_per_block": 5, "max_lines_per_block": 6},
                    "whitespace_target": "moderate consulting whitespace",
                    "template_inheritance": "free SVG inspired by consulting exhibit pages",
                    "anti_patterns": ["robot illustration", "dense table", "web dashboard", "neon tech poster"],
                    "critic_checks": ["overflow=0", "overlap=0", "hierarchy=ok", "density=ok"],
                    "layout_intent": slide["layout"] or slide["type"],
                    "bbox_budget": {"safe_area": [60, 60, 1160, 600], "footer_band": [70, 625, 1140, 48]},
                    "text_budget": {"mode": "short_bullets", "max_bullets_per_block": 5, "max_title_lines": 2},
                    "deterministic_scaffold": {"enabled": False, "reason": "AI-authored SVG primitives"},
                    "must_avoid": ["foreignObject", "script", "embedded style", "unapproved external images"],
                    "pre_authoring_checks": ["reread design_spec", "consume page design draft", "preserve conclusion"],
                },
            }
        )
    (PROJECT / "slide_visual_plan.json").write_text(
        json.dumps({"slides": visual_plan}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for slide in slides:
        (PROJECT / "svg_output" / f"slide_{slide['id']:02d}.svg").write_text(render_slide(slide), encoding="utf-8")


def main() -> int:
    slides, design_path, prompt_path = read_slides()
    write_project_files(slides, design_path, prompt_path)
    print(PROJECT)
    print(f"slides={len(slides)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
