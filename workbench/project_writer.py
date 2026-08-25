from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from workbench.formal_planning import apply_formal_planning_status, run_formal_planning
from workbench.page_director import direct_page
from workbench.prompt_intake import compact_for_blueprint, normalize_prompt_intake, normalize_submission_prompt
from workbench.rhythm_governor import govern_deck_rhythm
from workbench.style_tokens import canonicalize_style_tokens

_CTX: dict = {}


def _context_not_ready(name: str) -> RuntimeError:
    return RuntimeError(f"workbench.project_writer context is not initialized: {name}")


def _require_non_empty(value: object, field: str) -> str:
    del value, field
    raise _context_not_ready("require_non_empty")


def _project_dir(name: str) -> Path:
    del name
    raise _context_not_ready("project_dir")


def _template_binding_status(target: Path) -> dict:
    del target
    raise _context_not_ready("template_binding_status")


def _resolve_route(deck_type: str, style_key: str, template_mode: str, *, template_bound: bool) -> dict:
    del deck_type, style_key, template_mode, template_bound
    raise _context_not_ready("resolve_route")


def _resolve_template_instruction(template_mode: str, binding: dict) -> str:
    del template_mode, binding
    raise _context_not_ready("resolve_template_instruction")


def _write_text(path: Path, text: str) -> None:
    del path, text
    raise _context_not_ready("write_text")


def _write_json(path: Path, payload: dict) -> None:
    del path, payload
    raise _context_not_ready("write_json")


def _run_skill_command(args: list[str]) -> dict:
    del args
    raise _context_not_ready("run_skill_command")


def _create_agent_task(
    name: str,
    slides: list[dict[str, str]],
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    del name, slides, template_mode, template_instruction, route, template_binding
    raise _context_not_ready("create_agent_task")


def _create_slide_task(
    name: str,
    slide: dict[str, str],
    slide_id: int,
    total: int,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    del name, slide, slide_id, total, template_mode, template_instruction, route, template_binding
    raise _context_not_ready("create_slide_task")


require_non_empty: Callable[[object, str], str] = _require_non_empty
project_dir: Callable[[str], Path] = _project_dir
template_binding_status: Callable[[Path], dict] = _template_binding_status
resolve_route: Callable[..., dict] = _resolve_route
resolve_template_instruction: Callable[[str, dict], str] = _resolve_template_instruction
write_text: Callable[[Path, str], None] = _write_text
write_json: Callable[[Path, dict], None] = _write_json
run_skill_command: Callable[[list[str]], dict] = _run_skill_command
create_agent_task: Callable[..., str] = _create_agent_task
create_slide_task: Callable[..., str] = _create_slide_task

SCENES: set[str] = set()
STYLE_PROFILES: set[str] = set()
TEMPLATE_MODES: dict[str, dict[str, str]] = {}
GENERATION_MODES: set[str] = set()
SCENE_MAP: dict[str, dict[str, Any]] = {}
STYLE_MAP: dict[str, dict[str, str]] = {}

def set_context(**kwargs) -> None:
    _CTX.update(kwargs)
    globals().update(kwargs)

WORKFLOW_LABELS = {
    "single_page": "单页 PPT",
    "prompt_deck": "一句话生成 PPT",
    "document_deck": "文档生成 PPT",
    "optimize_existing": "继续处理已有项目",
    "repair_existing": "继续处理已有项目",
}
BLUEPRINT_BODY_CHAR_LIMIT = 340
BLUEPRINT_SUPPORT_CHAR_LIMIT = 140


def _ensure_default_style_drafts(target: Path) -> None:
    style_route_path = target / "style_route.json"
    if not style_route_path.exists():
        return
    try:
        style_route = json.loads(style_route_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    if not isinstance(style_route, dict) or not bool(style_route.get("requires_style_drafts", False)):
        return
    style_drafts_path = target / "style_drafts.json"
    if style_drafts_path.exists():
        return

    raw_candidates = style_route.get("template_candidates")
    candidates = raw_candidates if isinstance(raw_candidates, list) else []
    drafts: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates[:3], start=1):
        if not isinstance(candidate, dict):
            continue
        template_id = str(candidate.get("template_id") or "").strip()
        if not template_id:
            continue
        drafts.append(
            {
                "draft_id": f"draft-{index}",
                "template_id": template_id,
                "score": candidate.get("score"),
                "thesis": f"Workbench auto-selected candidate {template_id} for local API automation.",
                "risk_mitigation": "Use the first ranked draft for automated UAT; users can still revise style later.",
            }
        )
    fallback_templates = ["mckinsey", "exhibit", "consulting_classic"]
    for template_id in fallback_templates:
        if len(drafts) >= 2:
            break
        if any(item.get("template_id") == template_id for item in drafts):
            continue
        drafts.append(
            {
                "draft_id": f"draft-{len(drafts) + 1}",
                "template_id": template_id,
                "score": None,
                "thesis": f"Fallback consulting style draft: {template_id}.",
                "risk_mitigation": "Provides a valid explicit style selection for automated Workbench generation.",
            }
        )
    if not drafts:
        return
    selected = drafts[0]
    write_json(
        style_drafts_path,
        {
            "mode": "style_drafts",
            "selected_template": selected["template_id"],
            "selected_draft_id": selected["draft_id"],
            "selection_reason": "auto_selected_for_workbench_api_automation",
            "drafts": drafts,
        },
    )

def normalize_workflow_mode(value: object, deck_type: str = "multi") -> str:
    mode = str(value or "").strip()
    if mode in WORKFLOW_LABELS:
        return mode
    return "single_page" if deck_type == "single" else "prompt_deck"

def workflow_label(mode: str) -> str:
    return WORKFLOW_LABELS.get(mode, "常规 PPT 生成")


EXPLICIT_PAGE_BODY_LIMIT = 6000


def split_explicit_pages(prompt: str) -> list[dict[str, str]]:
    source = str(prompt or "").strip()
    if not source:
        return []
    marker = re.compile(
        r"(?m)^[ \t]*(?:#{1,6}[ \t]+)?"
        r"(?:\u7b2c\s*\d{1,3}\s*\u9875|[PR]\s*\d{1,3}|Page\s*\d{1,3}|Slide\s*\d{1,3})"
        r"(?:[ \t]*[\uff1a:\u3001.\-])?[ \t]*",
        re.I,
    )
    matches = list(marker.finditer(source))
    if len(matches) < 2:
        marker = re.compile(
            r"(?:^|\s)(?:\u7b2c\s*\d{1,3}\s*\u9875)"
            r"(?:[ \t]*[\uff1a:\u3001.\-])?[ \t]*",
            re.I,
        )
        matches = list(marker.finditer(source))
    if len(matches) < 2:
        return []
    slides: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[match.end() : next_start].strip()
        parts = re.split(
            r"\s*(?:\u6b63\u6587|\u5185\u5bb9|\u4e0a\u5c4f\u5185\u5bb9|姝ｆ枃|鍐呭|涓婂睆鍐呭)\s*[\uff1a:锛?]\s*",
            block,
            maxsplit=1,
        )
        if len(parts) > 1:
            raw_title = clean_explicit_page_title(parts[0])
            body_source = parts[1]
        else:
            lines = block.splitlines()
            raw_title = clean_explicit_page_title(lines[0] if lines else "")
            body_source = "\n".join(lines[1:]).strip() or block
        body = re.sub(r"\n?\s*---\s*$", "", body_source.strip())
        title = raw_title or f"Page {index + 1}"
        slides.append({"title": title[:120], "body": (body or title)[:EXPLICIT_PAGE_BODY_LIMIT]})
    return slides


def clean_explicit_page_title(value: str) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip(" \uff1a:\u3001.-锛?銆?")
    title = re.sub(
        r"^(?:\u6807\u9898|\u4e3b\u6807\u9898|\u4e0a\u5c4f\u6807\u9898|鏍囬|涓绘爣棰榺涓婂睆鏍囬)\s*[\uff1a:锛?]?\s*",
        "",
        title,
    ).strip()
    quote_match = re.match(r"^[\u201c\"「『《](?P<title>.+?)[\u201d\"」』》]\s*[\u3002.]?$", title)
    if quote_match:
        title = quote_match.group("title").strip()
    return title.strip(" \uff1a:\u3001.-锛?銆?")


def split_prompt(prompt: str, count: int) -> list[dict[str, str]]:
    clean = " ".join(prompt.split())
    if not clean:
        raise ValueError("prompt must be non-empty.")
    explicit_pages = split_explicit_pages(prompt)
    if explicit_pages:
        return explicit_pages
    quoted = re.search(r"[“\"「](.+?)[”\"」]", clean)
    topic = (quoted.group(1) if quoted else clean).strip()
    topic = topic[:36] or "PPT 生成任务"
    if count == 1:
        return [
            {
                "title": topic,
                "body": clean[:420],
                "prompt": normalize_submission_prompt(prompt),
            }
        ]
    plan = [
        ("封面：明确主题与核心结论", clean[:360]),
        ("现状与问题：说明为什么需要行动", clean[:360]),
        ("方案设计：展示主要路径和关键机制", clean[:360]),
        ("价值与收益：说明业务影响和判断依据", clean[:360]),
        ("后续计划：给出落地动作和节奏", clean[:360]),
        ("风险与保障：补充约束、依赖和缓释策略", clean[:360]),
        ("资源需求：明确组织、系统和协作投入", clean[:360]),
        ("里程碑：拆解阶段目标和验收方式", clean[:360]),
        ("附录：沉淀证据和参考信息", clean[:360]),
        ("收束页：强调决策请求", clean[:360]),
    ]
    return [
        {
            "title": f"{index}. {title}",
            "body": body,
        }
        for index, (title, body) in enumerate(plan[:count], start=1)
    ]

def create_design_spec(
    scene: dict,
    style: dict,
    page_count: int = 1,
    template_mode: str = "free",
    template_instruction: str = "",
    route: dict | None = None,
    template_binding: dict | None = None,
    generation_mode: str = "api_auto",
) -> str:
    route = route or {}
    template_binding = template_binding or {}
    if generation_mode == "api_auto":
        mode_assumptions = """- The workbench may call the configured model API to author SVG files.
- API keys must stay in local private config or environment variables, never in project status files.
- Workbench user-facing generation is fully automatic."""
    else:
        mode_assumptions = """- The workbench does not call a model API.
- AI-authored SVG should be created by the Agent from agent_task.md."""
    return f"""# Design Spec
- canvas: ppt169
- style: {style['style']}
- style_profile: {style.get('style_profile', style['label'])}
- primary_color: {style['primary_color']}
- accent_color: {style['accent_color']}
- background_color: {style['background_color']}
- card_bg: {style['card_bg']}
- text_color: {style['text_color']}
- muted_color: {style['muted_color']}
- line_color: {style['line_color']}
- font_title: {style['font_title']}
- font_body: {style['font_body']}
- font_ladder: {style['font_ladder']}
- page_count: {page_count}
- audience: {scene['audience']}
- language: zh-CN
- purpose: {scene['purpose']}
- style_objective: {style['style_goal']}
- route_id: {route.get('route_id', '')}
- route_label: {route.get('label', '')}
- generation_strategy: {route.get('generation_strategy', 'single_page_svg_authoring')}
- route_template_mode: {route.get('template_mode', template_mode)}
- route_template_required: {route.get('template_required', False)}
- template_mode: {template_mode}
- template_instruction: {template_instruction}
- template_bound: {template_binding.get('bound', False)}
- template_binding_note: {template_binding.get('note', 'No concrete template is bound yet.')}
- icon_library: tabler-outline
- image_mode: A
- quality_profile: {scene['quality_profile']}
- workbench_poc: codex_companion
- generation_mode: {generation_mode}

## Assumptions (workbench POC)
- This project is created by the local web workbench.
{mode_assumptions}
"""

def create_outline(slides: list[dict[str, Any]], deck_thesis: str = "") -> str:
    thesis = str(deck_thesis or "").strip()
    if thesis:
        lines = ["# Outline", "", "## 核心观点", "", thesis, "", "## 页面标题序列", ""]
        for index, slide in enumerate(slides, start=1):
            lines.append(f"{index}. {slide['title']}")
        lines.extend(["", "## 每页核心结论", ""])
        for index, slide in enumerate(slides, start=1):
            claims = slide.get("claims") if isinstance(slide, dict) else None
            main_claim = str(claims[0]).strip() if isinstance(claims, list) and claims else "待补充"
            lines.append(f"{index}. {slide['title']}")
            lines.append(f"   - {main_claim}")
        return "\n".join(lines) + "\n"
    lines = ["# Outline", ""]
    for index, slide in enumerate(slides, start=1):
        lines.append(f"{index}. {slide['title']}")
        lines.append(f"   - {slide['body']}")
    return "\n".join(lines) + "\n"

def compact_blueprint_body(text: str, limit: int = 700) -> str:
    clean = str(text or "").strip()
    if len(clean) <= limit:
        return clean
    section_patterns = [
        r"【上屏内容】(?P<body>.*?)(?:【推荐版式】|【视觉要求】|【底部结论】|【生成注意】|$)",
        r"【页面定位】(?P<body>.*?)(?:【上屏内容】|【推荐版式】|【视觉要求】|【底部结论】|【生成注意】|$)",
    ]
    chunks: list[str] = []
    for pattern in section_patterns:
        match = re.search(pattern, clean, re.S)
        if match:
            chunks.append(match.group("body").strip())
    if chunks:
        clean = "\n\n".join(chunks)
    lines = []
    for raw_line in clean.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【") and line.endswith("】"):
            continue
        lines.append(line)
    compact = "\n".join(lines)
    return compact[:limit].rstrip()


def _extract_bracket_section(text: str, keywords: list[str]) -> str:
    source = str(text or "")
    for keyword in keywords:
        pattern = rf"【[^】]*{re.escape(keyword)}[^】]*】(?P<body>.*?)(?=\n\s*【|\Z)"
        match = re.search(pattern, source, re.S)
        if match:
            return match.group("body").strip()
    return ""


def _extract_labeled_value(text: str, labels: list[str]) -> str:
    source = str(text or "")
    for label in labels:
        pattern = rf"^[ \t\-•]*{re.escape(label)}[：:]\s*(?P<value>.+)$"
        match = re.search(pattern, source, re.M)
        if match:
            return re.sub(r"\s+", " ", match.group("value")).strip()
    return ""


def _extract_content_bullets(text: str) -> list[str]:
    source = str(text or "")
    match = re.search(r"(?:^|\n)\s*[-•]?\s*上屏内容[：:]\s*(?P<body>.*?)(?=\n\s*【|\Z)", source, re.S)
    block = match.group("body") if match else source
    bullets: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【"):
            break
        is_list_item = bool(re.match(r"^\d+\s*[\.、]\s*", line) or line.startswith("-") or line.startswith("•"))
        if not is_list_item:
            continue
        cleaned = re.sub(r"^\d+\s*[\.、]\s*", "", line)
        cleaned = re.sub(r"^[-•]\s*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            continue
        if cleaned.startswith(("上屏标题", "上屏副标题", "上屏内容")):
            continue
        if any(token in cleaned for token in ("内部生成约束", "不要输出", "不得", "禁止事项", "输出要求")):
            continue
        bullets.append(cleaned)
    return bullets


def _build_structured_screen_copy(title: str, source: str) -> dict[str, object]:
    scoped = _extract_bracket_section(source, ["必须使用的页面文案", "上屏内容", "页面文案"]) or source
    headline = _extract_labeled_value(scoped, ["上屏标题", "主标题", "标题"]) or str(title or "").strip()
    subtitle = _extract_labeled_value(scoped, ["上屏副标题", "副标题"])
    bullets = _extract_content_bullets(scoped)

    body_lines: list[str] = []
    if headline:
        body_lines.append(f"上屏标题：{headline}")
    if subtitle:
        body_lines.append(f"上屏副标题：{subtitle}")
    if bullets:
        body_lines.append("上屏内容：")
        for index, item in enumerate(bullets[:5], start=1):
            body_lines.append(f"{index}. {item}")

    structured_body = "\n".join(body_lines).strip()
    if not structured_body:
        structured_body = compact_blueprint_body(source, BLUEPRINT_BODY_CHAR_LIMIT)

    support_parts: list[str] = []
    if subtitle:
        support_parts.append(subtitle)
    if bullets:
        support_parts.append("；".join(bullets[:2]))
        for item in bullets:
            if "勾稽" in item or "证明链" in item:
                support_parts.append(item)
                break
    structured_support = "；".join(part for part in support_parts if part).strip() or structured_body
    return {
        "headline": headline,
        "body": compact_blueprint_body(structured_body, BLUEPRINT_BODY_CHAR_LIMIT),
        "support": compact_blueprint_body(structured_support, BLUEPRINT_SUPPORT_CHAR_LIMIT),
        "bullets": bullets,
    }


def _is_three_flow_evidence_page(title: str, body: str) -> bool:
    combined = f"{title}\n{body}"
    has_three_flow = all(token in combined for token in ("物料流", "合同流", "资金流"))
    has_evidence = any(token in combined for token in ("证据文件", "证据", "勾稽", "证明链"))
    return has_three_flow and has_evidence


def infer_slide_profile(title: str, body: str) -> dict[str, object]:
    profile: dict[str, object] = {
        "layout_tag": "Statement-Bold",
        "narrative_intent": "Present the single most important message clearly and make the page review-ready.",
        "page_type": "codex_companion_page",
        "content_density": "medium",
        "features": {
            "kpi_count": 0,
            "chart_count": 0,
            "conclusion_count": 1,
            "has_comparison": False,
            "has_timeline": False,
        },
        "layout_hint": "Statement-Bold",
        "visual_archetype": "single-claim decision board",
        "composition_intent": "Place the headline in the top decision zone and support it with a concise body block.",
        "hierarchy_strategy": "Primary: headline; Secondary: body evidence; Tertiary: workbench note.",
        "rhythm_role": "single-page-proof",
        "variation_rule": "No deck-level variation required for the POC.",
        "density_budget": {"max_text_nodes": 8, "max_body_lines": 4, "max_chars": 420},
        "bbox_budget": {
            "headline": {"x": 104, "y": 126, "w": 980, "h": 110},
            "body": {"x": 104, "y": 286, "w": 920, "h": 190},
        },
        "page_prompt_pattern": {
            "pattern_id": "single_page_statement_poc",
            "conclusion_formula": "One decision-grade headline supported by concise proof text.",
            "block_structure": ["headline", "support body", "delivery/export note"],
            "composition_cues": ["top-zone dominance", "left aligned text", "restrained accent"],
            "anti_patterns": ["centered body copy", "card-heavy layout", "decorative shapes"],
        },
    }
    if _is_three_flow_evidence_page(title, body):
        profile.update(
            {
                "layout_tag": "Strategy-Map",
                "narrative_intent": "Explain why material flow, contract flow, capital flow, and evidence files must interlock into one proof chain.",
                "page_type": "data_integration",
                "content_density": "high",
                "features": {
                    "kpi_count": 0,
                    "chart_count": 0,
                    "conclusion_count": 2,
                    "has_comparison": True,
                    "has_timeline": False,
                },
                "layout_hint": "Strategy-Map",
                "visual_archetype": "three-flow evidence cross-check map",
                "composition_intent": "Lead with a judgment headline, then show three parallel flow modules and one bottom cross-check chain.",
                "hierarchy_strategy": "Primary: judgment headline; Secondary: three-flow modules; Tertiary: evidence and cross-check anchors.",
                "rhythm_role": "evidence-peak",
                "variation_rule": "Avoid generic equal-card wireframes; center the cross-check logic and evidence linkage.",
                "density_budget": {"max_text_nodes": 36, "max_body_lines": 18, "max_chars": 900},
                "bbox_budget": {
                    "headline": {"x": 84, "y": 64, "w": 1112, "h": 118},
                    "body": {"x": 72, "y": 190, "w": 1136, "h": 424},
                    "takeaway": {"x": 72, "y": 620, "w": 1136, "h": 54},
                },
                "page_prompt_pattern": {
                    "pattern_id": "three_flow_evidence_chain",
                    "conclusion_formula": "Three business flows plus evidence artifacts explain why traceability is provable, not just queryable.",
                    "block_structure": ["judgment headline", "three flow modules", "evidence ring", "cross-check takeaway"],
                    "composition_cues": ["top assertion", "parallel column rhythm", "bottom chain anchor", "restrained wine accent"],
                    "anti_patterns": ["raw prompt dump", "loose center diagram", "decorative-only circles"],
                },
            }
        )
    return profile


def build_blueprint_content_fields(title: str, body: str) -> dict[str, str]:
    intake = normalize_prompt_intake(str(title or ""), str(body or ""))
    compact = compact_for_blueprint(
        intake,
        body_limit=BLUEPRINT_BODY_CHAR_LIMIT,
        support_limit=BLUEPRINT_SUPPORT_CHAR_LIMIT,
    )
    return {
        "headline": str(compact.get("headline") or title or "").strip(),
        "body": str(compact.get("body") or "").strip(),
        "statement": str(compact.get("statement") or title or "").strip(),
        "support": str(compact.get("support") or "").strip(),
    }


def _planning_source(slide: dict[str, Any]) -> str:
    return normalize_submission_prompt(str(slide.get("prompt") or slide.get("body") or ""))


def _must_keep_claims_from_content(content_fields: dict[str, str]) -> list[str]:
    claims: list[str] = []
    for key in ("statement", "headline"):
        value = re.sub(r"\s+", " ", str(content_fields.get(key) or "")).strip()
        if not value:
            continue
        if len(value) > 90:
            value = value[:90].rstrip()
        if value not in claims:
            claims.append(value)
    return claims


def _strategy_map_contract_content(content_fields: dict[str, str]) -> dict[str, object]:
    body = str(content_fields.get("body") or content_fields.get("support") or "").strip()
    pillars: list[dict[str, str]] = []
    for label in ("物料流", "合同流", "资金流", "证据文件"):
        if label in body:
            pillars.append({"title": label, "body": f"{label}需要与其他对象勾稽，支撑可解释证明链。"})
    if not pillars:
        pillars = [
            {"title": "关键对象", "body": "明确页面中的核心业务对象。"},
            {"title": "证明关系", "body": "说明对象之间如何互相证明。"},
            {"title": "输出结果", "body": "收束为可审计、可解释的业务结论。"},
        ]
    return {
        "north_star": str(content_fields.get("statement") or content_fields.get("headline") or "").strip(),
        "pillars": pillars[:4],
    }


def _build_blueprint_slide(index: int, slide: dict[str, Any]) -> dict[str, object]:
    planning_source = _planning_source(slide)
    profile = infer_slide_profile(slide["title"], planning_source)
    content_fields = build_blueprint_content_fields(slide["title"], slide["body"])
    planned_content = slide.get("content")
    if isinstance(planned_content, dict):
        for key in ("headline", "body", "statement", "support"):
            value = str(planned_content.get(key) or "").strip()
            if value:
                content_fields[key] = value
    claims = slide.get("claims")
    if isinstance(claims, list) and claims and str(claims[0]).strip():
        content_fields["statement"] = str(claims[0]).strip()
    layout_tag = str(profile.get("layout_tag") or "Statement-Bold")
    if layout_tag == "Strategy-Map":
        content_fields = {**content_fields, **_strategy_map_contract_content(content_fields)}
    result: dict[str, object] = {
        "id": index,
        "title": slide["title"],
        "layout_tag": layout_tag,
        "narrative_intent": str(
            slide.get("narrative_intent")
            or profile.get("narrative_intent")
            or "Present the single most important message clearly and make the page review-ready."
        ),
        "page_type": "content",
        "visual_page_type": str(profile.get("page_type") or "codex_companion_page"),
        "content_density": str(profile.get("content_density") or "medium"),
        "features": profile.get("features")
        or {
            "kpi_count": 0,
            "chart_count": 0,
            "conclusion_count": 1,
            "has_comparison": False,
            "has_timeline": False,
        },
        "layout_hint": str(profile.get("layout_hint") or "Statement-Bold"),
        "prompt": planning_source,
        "content": {
            "eyebrow": "Codex Companion Workbench",
            **content_fields,
        },
    }
    for key in ("claims", "acceptance_criteria", "source_refs"):
        value = slide.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            result[key] = list(value)
    claim_boundary = str(slide.get("claim_boundary") or "").strip()
    if claim_boundary:
        result["claim_boundary"] = claim_boundary
    visual_intent = str(slide.get("visual_intent") or "").strip()
    if visual_intent:
        result["visual_intent"] = visual_intent
    return result


def _build_visual_plan_slide(
    index: int,
    slide: dict[str, str],
    scene_type: str,
    strategy: str,
    workflow_mode: str,
) -> dict[str, object]:
    planning_source = _planning_source(slide)
    profile = infer_slide_profile(slide["title"], planning_source)
    content_fields = build_blueprint_content_fields(slide["title"], slide["body"])
    director = direct_page(
        title=content_fields["headline"] or slide["title"],
        prompt=planning_source,
        mode=workflow_mode,
    )
    visual_contract = {
        "scene_type": scene_type,
        "generation_strategy": strategy,
        "focal_point": "top decision-zone headline",
        "primary_read_path": ["headline", "body", "bottom note"],
        "composition_grammar": str(
            profile.get("composition_intent")
            or "single strong headline over concise support copy with restrained accent rule"
        ),
        "hierarchy_ladder": "headline 46-54, body 22-28, note 14-18",
        "density_budget": profile.get("density_budget") or {"max_text_nodes": 8, "max_body_lines": 4, "max_chars": 420},
        "whitespace_target": "open business canvas with generous margins",
        "template_inheritance": "free design; no fixed template selected",
        "anti_patterns": ["decorative clutter", "multi-slide expansion", "equal card grid"],
        "critic_checks": ["headline visible in top zone", "no overflow", "no unsupported SVG nodes"],
        "layout_intent": "prove single-page workbench flow",
        "bbox_budget": profile.get("bbox_budget")
        or {
            "headline": {"x": 104, "y": 126, "w": 980, "h": 110},
            "body": {"x": 104, "y": 286, "w": 920, "h": 190},
        },
        "text_budget": {
            "headline": content_fields["headline"][:80],
            "body": content_fields["body"][:260],
        },
        "deterministic_scaffold": {"allowed": False, "purpose": "Codex authors the SVG manually"},
        "must_avoid": ["foreignObject", "render_svg.py", "out-of-blueprint slides"],
        "pre_authoring_checks": ["read design_spec.md", "read outline.md", "read blueprint.json"],
    }
    visual_contract.update(director["visual_contract_patch"])
    return {
        "slide_id": index,
        "layout_tag": str(profile.get("layout_tag") or "Statement-Bold"),
        "narrative_intent": str(
            profile.get("narrative_intent")
            or "Present the single most important message clearly and make the page review-ready."
        ),
        "page_type_decision": director["page_type_decision"],
        "circle_role": director["circle_role"],
        "selected_archetype": director["selected_archetype"],
        "visual_archetype": director["visual_archetype"],
        "composition_intent": director["composition_intent"],
        "hierarchy_strategy": director["hierarchy_strategy"],
        "layout_objective": str(
            profile.get("composition_intent")
            or "Lead with the decision headline, then support it with concise proof modules."
        ),
        "density_budget": profile.get("density_budget") or {"max_text_nodes": 8, "max_body_lines": 4, "max_chars": 420},
        "dominance_map": {
            "primary": "headline",
            "secondary": "support modules",
            "tertiary": "takeaway or note",
        },
        "must_keep_claims": _must_keep_claims_from_content(content_fields),
        "rhythm_role": director["rhythm_role"],
        "argument_pattern": director["argument_pattern"],
        "proof_objects": director["proof_objects"],
        "reference_slides": [],
        "variation_rule": director["variation_rule"],
        "avoid": [
            "Do not create multiple slides.",
            "Do not use foreignObject.",
            "Do not run render_svg.py.",
        ],
        "scene_route": {
            "scene_type": scene_type,
            "generation_strategy": strategy,
        },
        "execution": {
            "strategy": strategy,
        },
        "execution_policy": {
            "scene_type": scene_type,
            "generation_strategy": strategy,
            "risk_level": "medium",
            "required_loop": "structure_pass -> polish_pass -> critic_gate",
            "qa_strictness": "standard",
            "expected_first_pass_rules": [
                "viewBox is 0 0 1280 720",
                "native SVG text only",
                "one clear top-zone headline",
            ],
        },
        "visual_contract": visual_contract,
        "page_prompt_pattern": director["page_prompt_pattern"],
    }


def create_clarification_brief(
    scene: dict,
    style: dict,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> dict:
    template_id = str(template_binding.get("template_id") or "").strip()
    if bool(template_binding.get("bound")) and template_id:
        template_preference = template_id
    elif template_mode == "free":
        template_preference = "free design"
    else:
        template_preference = "no strict template"
    return {
        "autonomous_mode": True,
        "audience": scene["audience"],
        "decision_goal": scene["decision_goal"],
        "style_goal": style["style_goal"],
        "route_id": route.get("route_id"),
        "route_label": route.get("label"),
        "route_policy": {
            "allowed_actions": route.get("allowed_actions", []),
            "forbidden_actions": route.get("forbidden_actions", []),
        },
        "route_template_mode": route.get("template_mode", template_mode),
        "route_template_required": bool(route.get("template_required", False)),
        "template_mode": template_mode,
        "template_instruction": template_instruction,
        "template_bound": bool(template_binding.get("bound")),
        "template_binding_note": template_binding.get("note"),
        "template_id": template_id,
        "template_preference": template_preference,
        "assumptions": [
            "Single-page POC uses user-provided title and body as the only source content.",
            "Formal template selection may choose references when no concrete template is bound.",
        ],
    }

def create_blueprint(
    slides: list[dict[str, Any]],
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> dict:
    return {
        "route_id": route.get("route_id"),
        "route_label": route.get("label"),
        "route_policy": {
            "allowed_actions": route.get("allowed_actions", []),
            "forbidden_actions": route.get("forbidden_actions", []),
        },
        "route_template_mode": route.get("template_mode", template_mode),
        "route_template_required": bool(route.get("template_required", False)),
        "template_mode": template_mode,
        "template_instruction": template_instruction,
        "template_bound": bool(template_binding.get("bound")),
        "template_binding_note": template_binding.get("note"),
        "template_id": template_binding.get("template_id", ""),
        "slides": [
            _build_blueprint_slide(index, slide)
            for index, slide in enumerate(slides, start=1)
        ]
    }

def create_art_direction(style: dict) -> str:
    return f"""# Art Direction

## Visual Metaphor
- Core metaphor: single-page decision board with one dominant conclusion and restrained evidence support.
- Tone and mode: {style['style_goal']}.

## Rhythm Strategy
- Prioritize immediate readability and a clear top-down read path on every page.
- The workbench creates tasks; Codex is responsible for authoring each SVG.

## Composition Principles
- Treat `layout_tag` as schema only; the Executor owns visual composition.
- Keep one dominant headline in the top safe area and one supporting body block below it.
- Use restrained color and avoid decorative noise.

## Taboos
- Do not use `foreignObject`.
- Do not run `render_svg.py`.
- Do not create slides outside the blueprint.
"""

def create_reference_pack(
    style: dict,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
    visual_grammar_references: list[str] | None = None,
) -> dict:
    references = sorted({str(item) for item in (visual_grammar_references or []) if str(item).strip()})
    return {
        "primary_template": None,
        "secondary_templates": [],
        "route_id": route.get("route_id"),
        "route_label": route.get("label"),
        "style_profile": "single_page_workbench_poc",
        "template_mode": template_mode,
        "template_instruction": template_instruction,
        "free_design_override_reason": "Free design remains AI-authored per slide; references are used as visual grammar guidance only.",
        "template_bound": bool(template_binding.get("bound")),
        "template_binding_note": template_binding.get("note"),
        "visual_grammar_mode": "reference-guided-free-design",
        "visual_grammar_references": references,
        "tone": style["style_goal"],
        "themeMode": "Free-design POC with no fixed template selected.",
        "motifs": ["dominant headline", "single evidence block", "restrained accent rule"],
        "avoid": [
            "Do not add model/API invocation paths.",
            "Do not replace the repository exporter chain.",
        ],
        "reference_files": [],
        "execution_tokens": {
            "color_system": {
                "max_primary_colors_per_slide": 3,
                "primary_palette": [style["primary_color"], style["accent_color"], style["text_color"]],
            }
        },
    }

def create_slide_visual_plan(
    slides: list[dict[str, str]],
    generation_mode: str = "api_auto",
    workflow_mode: str = "prompt_deck",
) -> dict:
    scene_type = "codex_companion"
    strategy = generation_mode
    planned_slides = [
        _build_visual_plan_slide(index, slide, scene_type, strategy, workflow_mode)
        for index, slide in enumerate(slides, start=1)
    ]
    governed = govern_deck_rhythm(planned_slides)
    return {
        "version": 1,
        "slides": governed["slides"],
        "deck_rhythm_map": governed["deck_rhythm_map"],
        "layout_exploration": governed["layout_exploration"],
    }

def write_project_files(name: str, payload: dict) -> dict:
    title = require_non_empty(payload.get("slide_title"), "slide_title")
    body = require_non_empty(normalize_submission_prompt(str(payload.get("slide_content") or "")), "slide_content")
    scene_key = str(payload.get("scene", "")).strip()
    style_key = str(payload.get("style_profile", "")).strip()
    template_mode = str(payload.get("template_mode", "free") or "free").strip()
    generation_mode = "api_auto"
    if scene_key not in SCENES:
        raise ValueError("scene must be one of report, proposal, product.")
    if style_key not in STYLE_PROFILES:
        raise ValueError("style_profile must be one of " + ", ".join(sorted(STYLE_PROFILES)) + ".")
    if template_mode not in TEMPLATE_MODES:
        raise ValueError("template_mode must be one of free, reference, reuse, strict_template.")
    page_count = int(payload.get("page_count", 1) or 1)
    deck_type = str(payload.get("deck_type", "single") or "single")
    workflow_mode = normalize_workflow_mode(payload.get("workflow_mode"), deck_type)
    workflow_label_value = workflow_label(workflow_mode)
    slides = payload.get("slides")
    if not isinstance(slides, list) or not slides:
        slides = split_prompt(f"{title}。{body}", page_count)
    normalized_slides = []
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        normalized_slide: dict[str, Any] = {
            "title": require_non_empty(slide.get("title"), "slide.title"),
            "body": require_non_empty(slide.get("body"), "slide.body"),
            "prompt": normalize_submission_prompt(str(slide.get("prompt") or slide.get("body") or "")),
        }
        for key in ("narrative_intent", "visual_intent"):
            value = str(slide.get(key) or "").strip()
            if value:
                normalized_slide[key] = value
        for key in ("claims", "acceptance_criteria", "source_refs"):
            value = slide.get(key)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                normalized_slide[key] = list(value)
        claim_boundary = str(slide.get("claim_boundary") or "").strip()
        if claim_boundary:
            normalized_slide["claim_boundary"] = claim_boundary
        content = slide.get("content")
        if isinstance(content, dict):
            normalized_slide["content"] = dict(content)
        normalized_slides.append(normalized_slide)
    if not normalized_slides:
        raise ValueError("slides must contain at least one slide.")

    target = project_dir(name)
    scene = SCENE_MAP[scene_key]
    style = dict(STYLE_MAP[style_key])
    style["style_profile"] = style_key
    target.mkdir(parents=True, exist_ok=True)
    for child in ("svg_output", "svg_final", "exports", "qa"):
        (target / child).mkdir(exist_ok=True)
    binding = template_binding_status(target)
    route = resolve_route(deck_type, style_key, template_mode, template_bound=bool(binding["bound"]))
    template_instruction = resolve_template_instruction(template_mode, binding)
    prompt_text = "\n".join(f"{slide['title']}\n{slide['body']}" for slide in normalized_slides)
    canonical_style = canonicalize_style_tokens(style, prompt_text)
    visual_plan = create_slide_visual_plan(normalized_slides, generation_mode, workflow_mode)
    visual_grammar_references = [
        str((slide.get("page_prompt_pattern") or {}).get("pattern_id") or "")
        for slide in visual_plan.get("slides", [])
        if isinstance(slide, dict)
    ]

    write_text(
        target / "design_spec.md",
        create_design_spec(
            scene,
            canonical_style,
            page_count=len(normalized_slides),
            template_mode=template_mode,
            template_instruction=template_instruction,
            route=route,
            template_binding=binding,
            generation_mode=generation_mode,
        ),
    )
    write_text(
        target / "outline.md",
        create_outline(normalized_slides, str(payload.get("deck_thesis") or "")),
    )
    write_json(
        target / "clarification_brief.json",
        create_clarification_brief(scene, canonical_style, template_mode, template_instruction, route, binding),
    )
    write_json(target / "blueprint.json", create_blueprint(normalized_slides, template_mode, template_instruction, route, binding))
    write_text(
        target / "agent_task.md",
        create_agent_task(name, normalized_slides, template_mode, template_instruction, route, binding),
    )
    write_text(target / "art_direction.md", create_art_direction(canonical_style))
    write_json(
        target / "reference_pack.json",
        create_reference_pack(
            canonical_style,
            template_mode,
            template_instruction,
            route,
            binding,
            visual_grammar_references=visual_grammar_references,
        ),
    )
    write_json(target / "slide_visual_plan.json", visual_plan)
    for index, slide in enumerate(normalized_slides, start=1):
        write_text(
            target / "agent_tasks" / f"slide_{index:02d}.md",
            create_slide_task(name, slide, index, len(normalized_slides), template_mode, template_instruction, route, binding),
        )
    formal_planning = run_formal_planning(target)
    style_route = {
        "returncode": 0 if formal_planning.get("formal_planning_status") == "ready" else 1,
        "stdout": "formal planning ready" if formal_planning.get("formal_planning_status") == "ready" else "",
        "stderr": str(formal_planning.get("failure_message") or ""),
    }
    _ensure_default_style_drafts(target)
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    status_payload = apply_formal_planning_status(
        {
            "schema_version": 2,
            "project": name,
            "route_id": route["route_id"],
            "route_label": route["label"],
            "route_policy": {
                "allowed_actions": route["allowed_actions"],
                "forbidden_actions": route["forbidden_actions"],
            },
            "route_template_mode": route.get("template_mode", template_mode),
            "route_template_required": bool(route.get("template_required", False)),
            "workflow_mode": workflow_mode,
            "workflow_label": workflow_label_value,
            "generation_mode": generation_mode,
            "recommended_next_action": {
                "key": "auto_generate",
                "label": "自动生成第 1 页",
                "detail": "项目文件已创建，可开始生成第 1 页。",
            },
            "deck_type": deck_type,
            "slide_count": len(normalized_slides),
            "style_profile": style_key,
            "template_mode": template_mode,
            "template_bound": bool(binding["bound"]),
            "template_binding_note": binding["note"],
            "template_id": binding["template_id"],
            "project_status": "waiting_codex",
            "created_at": now,
            "updated_at": now,
            "slides": [
                {
                    "slide_id": index,
                    "title": slide["title"],
                    "page_type": "content",
                    "prompt": slide.get("prompt") or slide["body"],
                    "status": "waiting_codex",
                    "svg_path": f"svg_output/slide_{index:02d}.svg",
                    "has_svg": False,
                    "qa_status": "not_run",
                    "revision_count": 0,
                    "last_error": "",
                }
                for index, slide in enumerate(normalized_slides, start=1)
            ],
            "export": {
                "status": "not_ready",
                "ready": False,
                "pptx_path": "",
                "last_returncode": None,
                "last_error": "",
            },
            "events": [
                {
                    "time": now,
                    "type": "task_created",
                    "message": f"Created Codex task for {len(normalized_slides)} slides.",
                }
            ],
        },
        formal_planning,
    )
    write_json(target / "workbench_status.json", status_payload)
    return {
        "style_route": style_route,
        "formal_planning": formal_planning,
        "slides": normalized_slides,
        "route": route,
        "template_binding": binding,
        "template_instruction": template_instruction,
        "workflow_mode": workflow_mode,
        "workflow_label": workflow_label_value,
        "generation_mode": generation_mode,
    }
