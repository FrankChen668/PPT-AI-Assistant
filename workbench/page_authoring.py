from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from workbench.formal_planning import apply_formal_planning_status, run_formal_planning
from workbench.page_director import direct_page
from workbench.prompt_intake import compact_for_blueprint, normalize_prompt_intake, normalize_submission_prompt
from workbench.state import add_event, load_status, save_status


PAGE_TYPES = {"content", "cover", "toc", "section"}
CONTENT_HANDLING_OPTIONS = {"preserve", "polish", "expand"}
PAGE_STYLE_OPTIONS = {"business_simple", "software_consulting"}
DEFAULT_CONTENT_HANDLING = "polish"
DEFAULT_PAGE_STYLE = "business_simple"
DEFAULT_LAYOUT_TAG = "Statement-Bold"
DEFAULT_VISUAL_BRIEF = "等待用户补充本页提示词。"
DEFAULT_SCENE_TYPE = "codex_companion"
BLUEPRINT_BODY_CHAR_LIMIT = 340
BLUEPRINT_SUPPORT_CHAR_LIMIT = 140


def require_page_type(value: str) -> str:
    page_type = str(value or "content").strip()
    if page_type not in PAGE_TYPES:
        raise ValueError("page_type must be one of: content, cover, section, toc.")
    return page_type


def normalize_content_handling(value: object) -> str:
    content_handling = str(value or DEFAULT_CONTENT_HANDLING).strip()
    return content_handling if content_handling in CONTENT_HANDLING_OPTIONS else DEFAULT_CONTENT_HANDLING


def normalize_page_style(value: object) -> str:
    page_style = str(value or DEFAULT_PAGE_STYLE).strip()
    return page_style if page_style in PAGE_STYLE_OPTIONS else DEFAULT_PAGE_STYLE


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_true_single_page_workflow(status: dict | None) -> bool:
    if not isinstance(status, dict):
        return False
    deck_type = str(status.get("deck_type") or "").strip()
    workflow_mode = str(status.get("workflow_mode") or "single_page").strip()
    return deck_type == "single" and workflow_mode == "single_page"


def read_blueprint(target: Path) -> dict:
    blueprint = read_json(target / "blueprint.json", {})
    if not isinstance(blueprint, dict):
        raise ValueError("blueprint.json must contain an object.")
    return blueprint


def default_page_title(slide_id: int) -> str:
    return f"第 {slide_id} 页"


def infer_title_from_prompt(prompt: str) -> str:
    match = re.search(r"《([^》\n]{1,80})》", str(prompt or ""))
    if match:
        return match.group(1).strip()
    for line in str(prompt or "").splitlines():
        clean = line.strip()
        if clean.startswith("主标题："):
            return clean.removeprefix("主标题：").strip()[:80]
    return ""


def normalize_page_title(slide_id: int, title: str, prompt: str) -> str:
    clean_title = str(title or "").strip()
    inferred = infer_title_from_prompt(prompt)
    title_looks_like_prompt = len(clean_title) > 80 or "\n" in clean_title or "【" in clean_title
    if inferred and (not clean_title or clean_title == default_page_title(slide_id) or title_looks_like_prompt):
        return inferred
    return clean_title or inferred or default_page_title(slide_id)


def compact_page_body(text: str, limit: int = 700) -> str:
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
        if not line or (line.startswith("【") and line.endswith("】")):
            continue
        lines.append(line)
    compact = "\n".join(lines)
    return compact[:limit].rstrip()


def build_blueprint_content_fields(title: str, prompt: str, *, eyebrow: str | None = None) -> dict[str, str]:
    intake = normalize_prompt_intake(str(title or ""), str(prompt or ""))
    compact = compact_for_blueprint(
        intake,
        body_limit=BLUEPRINT_BODY_CHAR_LIMIT,
        support_limit=BLUEPRINT_SUPPORT_CHAR_LIMIT,
    )
    content: dict[str, str] = {
        "headline": str(compact.get("headline") or title or "").strip(),
        "body": str(compact.get("body") or "").strip(),
        "statement": str(compact.get("statement") or title or "").strip(),
        "support": str(compact.get("support") or "").strip(),
    }
    if eyebrow is not None:
        content["eyebrow"] = eyebrow
    return content


def must_keep_claims_from_content(content_fields: dict[str, str]) -> list[str]:
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


def build_page_visual_contract(slide_id: int, title: str, prompt: str) -> dict:
    clean_title = normalize_page_title(slide_id, title, prompt)
    compact_prompt = compact_page_body(prompt, 420) or DEFAULT_VISUAL_BRIEF
    return {
        "scene_type": DEFAULT_SCENE_TYPE,
        "generation_strategy": "api_auto",
        "focal_point": "top decision-zone headline",
        "primary_read_path": ["headline", "key blocks", "takeaway"],
        "composition_grammar": "one strong headline with concise structured support and restrained accent color",
        "hierarchy_ladder": "headline 42-56, body 16-24, note 13-18",
        "density_budget": {"max_text_nodes": 28, "max_body_lines": 10, "max_chars": 700},
        "whitespace_target": "open business canvas with clear safe margins",
        "template_inheritance": "free design; no fixed template selected",
        "anti_patterns": ["decorative clutter", "dense table", "prompt text on canvas"],
        "critic_checks": ["headline visible", "no overflow", "no unsupported SVG nodes"],
        "layout_intent": "support progressive page authoring",
        "bbox_budget": {
            "headline": {"x": 96, "y": 80, "w": 1088, "h": 150},
            "body": {"x": 96, "y": 240, "w": 1088, "h": 360},
        },
        "text_budget": {"headline": clean_title[:80], "body": compact_prompt},
        "deterministic_scaffold": {"allowed": False, "purpose": "AI authors SVG per page"},
        "must_avoid": ["foreignObject", "render_svg.py", "out-of-blueprint slides"],
        "pre_authoring_checks": ["read design_spec.md", "read blueprint.json", "read slide_visual_plan.json"],
    }


def build_initial_status_from_blueprint(name: str, target: Path) -> dict:
    slides = []
    try:
        blueprint = read_blueprint(target)
        raw_slides = blueprint.get("slides") if isinstance(blueprint, dict) else []
        if isinstance(raw_slides, list):
            for index, slide in enumerate(raw_slides, start=1):
                content = slide.get("content", {}) if isinstance(slide, dict) else {}
                title = ""
                if isinstance(slide, dict):
                    title = str(slide.get("title") or content.get("headline") or content.get("statement") or "").strip()
                slides.append(
                    {
                        "slide_id": index,
                        "title": title or f"{index}. 未命名页面",
                        "page_type": str(slide.get("page_type") or "content") if isinstance(slide, dict) else "content",
                        "prompt": str(content.get("body") or content.get("support") or "") if isinstance(content, dict) else "",
                        "status": "waiting_codex",
                        "svg_path": f"svg_output/slide_{index:02d}.svg",
                        "has_svg": False,
                        "qa_status": "not_run",
                        "revision_count": 0,
                        "last_error": "",
                    }
                )
    except Exception:
        slides = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    return {
        "schema_version": 2,
        "project": name,
        "route_id": "",
        "route_label": "",
        "route_policy": {"allowed_actions": [], "forbidden_actions": []},
        "route_template_mode": "free",
        "route_template_required": False,
        "workflow_mode": "prompt_deck",
        "workflow_label": "一句话生成 PPT",
        "recommended_next_action": {
            "key": "auto_generate",
            "label": "自动生成页面",
            "detail": "项目文件已存在，可继续生成缺失页面。",
        },
        "deck_type": "multi",
        "slide_count": len(slides),
        "style_profile": "",
        "template_mode": "free",
        "template_bound": False,
        "template_binding_note": "No concrete template is bound yet.",
        "template_id": "",
        "project_status": "project_created",
        "created_at": now,
        "updated_at": now,
        "slides": slides,
        "export": {
            "status": "not_ready",
            "ready": False,
            "pptx_path": "",
            "last_returncode": None,
            "last_error": "",
        },
        "events": [],
    }


def build_page_slide(
    slide_id: int,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
) -> dict:
    clean_title = normalize_page_title(slide_id, title, prompt)
    clean_prompt = prompt.strip()
    return {
        "id": slide_id,
        "title": clean_title,
        "layout_tag": DEFAULT_LAYOUT_TAG,
        "page_type": page_type,
        "content_handling": normalize_content_handling(content_handling),
        "page_style": normalize_page_style(page_style),
        "narrative_intent": "Present this page clearly as part of a progressively authored deck.",
        "content_density": "medium",
        "content": build_blueprint_content_fields(clean_title, clean_prompt),
    }


def build_page_visual_plan(
    slide_id: int,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
    *,
    mode: str = "append_page",
) -> dict:
    clean_title = normalize_page_title(slide_id, title, prompt)
    compact_prompt = compact_page_body(prompt, 420) or DEFAULT_VISUAL_BRIEF
    director = direct_page(title=clean_title, prompt=prompt, mode=mode)
    content_fields = build_blueprint_content_fields(clean_title, prompt)
    visual_contract = build_page_visual_contract(slide_id, clean_title, prompt)
    visual_contract.update(director["visual_contract_patch"])
    density_budget = visual_contract.get("density_budget")
    if not isinstance(density_budget, dict):
        density_budget = {"max_text_nodes": 28, "max_body_lines": 10, "max_chars": 700}
    return {
        "slide_id": slide_id,
        "title": clean_title,
        "page_type": page_type,
        "content_handling": normalize_content_handling(content_handling),
        "page_style": normalize_page_style(page_style),
        "layout_tag": DEFAULT_LAYOUT_TAG,
        "narrative_intent": "Present this page clearly as part of a progressively authored deck.",
        "page_type_decision": director["page_type_decision"],
        "circle_role": director["circle_role"],
        "selected_archetype": director["selected_archetype"],
        "visual_archetype": director["visual_archetype"],
        "composition_intent": director["composition_intent"],
        "hierarchy_strategy": director["hierarchy_strategy"],
        "layout_objective": director["composition_intent"],
        "density_budget": density_budget,
        "dominance_map": {
            "primary": "headline",
            "secondary": "main visual structure",
            "tertiary": "takeaway or supporting note",
        },
        "must_keep_claims": must_keep_claims_from_content(content_fields),
        "rhythm_role": director["rhythm_role"],
        "argument_pattern": director["argument_pattern"],
        "proof_objects": director["proof_objects"],
        "reference_slides": [],
        "variation_rule": director["variation_rule"],
        "visual_brief": compact_prompt,
        "avoid": [
            "Do not use foreignObject.",
            "Do not run render_svg.py.",
            "Do not include prompt instructions on the slide canvas.",
        ],
        "scene_route": {"scene_type": DEFAULT_SCENE_TYPE, "generation_strategy": "api_auto"},
        "execution": {"strategy": "api_auto"},
        "execution_policy": {
            "scene_type": DEFAULT_SCENE_TYPE,
            "generation_strategy": "api_auto",
            "risk_level": "medium",
            "required_loop": "structure_pass -> polish_pass -> critic_gate",
            "qa_strictness": "standard",
            "expected_first_pass_rules": [
                "viewBox is 0 0 1280 720",
                "native SVG text only",
                "no overlapping text",
            ],
        },
        "visual_contract": visual_contract,
        "page_prompt_pattern": director["page_prompt_pattern"],
    }


def build_page_status(
    slide_id: int,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
) -> dict:
    clean_title = normalize_page_title(slide_id, title, prompt)
    return {
        "slide_id": slide_id,
        "title": clean_title,
        "page_type": page_type,
        "content_handling": normalize_content_handling(content_handling),
        "page_style": normalize_page_style(page_style),
        "prompt": prompt,
        "status": "waiting_codex",
        "svg_path": f"svg_output/slide_{slide_id:02d}.svg",
        "has_svg": False,
        "qa_status": "not_run",
        "revision_count": 0,
        "last_error": "",
    }


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def archive_deleted_slide_artifacts(target: Path, slide_id: int) -> str:
    stem = f"slide_{slide_id:02d}"
    archive_dir = target / ".workbench_archive" / "deleted-slides" / f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{stem}"
    artifact_specs = [
        ("svg_output", ".svg"),
        ("svg_final", ".svg"),
        ("agent_tasks", ".md"),
        ("agent_tasks", ".json"),
        ("executor_packets", ".json"),
        ("executor_packets", ".md"),
        ("exports/single-pages", ".pptx"),
    ]
    archived_any = False
    for folder, suffix in artifact_specs:
        src = target / folder / f"{stem}{suffix}"
        if not src.exists():
            continue
        dst = archive_dir / folder / f"{stem}{suffix}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
        archived_any = True
    work_dir = target / "exports" / "single-pages" / "_work" / stem
    if work_dir.exists():
        dst = archive_dir / "exports" / "single-pages" / "_work" / stem
        dst.parent.mkdir(parents=True, exist_ok=True)
        work_dir.replace(dst)
        archived_any = True
    revision_dir = target / "revisions" / stem
    if revision_dir.exists():
        dst = archive_dir / "revisions" / stem
        dst.parent.mkdir(parents=True, exist_ok=True)
        revision_dir.replace(dst)
        archived_any = True
    return str(archive_dir.relative_to(target)).replace("\\", "/") if archived_any else ""


def move_path(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    remove_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.replace(dst)


def rename_slide_artifacts(target: Path, old_id: int, new_id: int) -> None:
    if old_id == new_id:
        return
    old_stem = f"slide_{old_id:02d}"
    new_stem = f"slide_{new_id:02d}"
    artifact_specs = [
        ("svg_output", ".svg"),
        ("svg_final", ".svg"),
        ("agent_tasks", ".md"),
        ("agent_tasks", ".json"),
        ("executor_packets", ".json"),
        ("executor_packets", ".md"),
        ("exports/single-pages", ".pptx"),
    ]
    for folder, suffix in artifact_specs:
        move_path(target / folder / f"{old_stem}{suffix}", target / folder / f"{new_stem}{suffix}")
    move_path(target / "revisions" / old_stem, target / "revisions" / new_stem)
    move_path(target / "exports" / "single-pages" / "_work" / old_stem, target / "exports" / "single-pages" / "_work" / new_stem)


def delete_slide_artifacts(target: Path, slide_id: int) -> None:
    stem = f"slide_{slide_id:02d}"
    artifact_specs = [
        ("svg_output", ".svg"),
        ("svg_final", ".svg"),
        ("agent_tasks", ".md"),
        ("agent_tasks", ".json"),
        ("executor_packets", ".json"),
        ("executor_packets", ".md"),
        ("exports/single-pages", ".pptx"),
    ]
    for folder, suffix in artifact_specs:
        remove_path(target / folder / f"{stem}{suffix}")
    remove_path(target / "revisions" / stem)
    remove_path(target / "exports" / "single-pages" / "_work" / stem)


def default_title_after_reindex(title: str, old_id: int, new_id: int) -> str:
    clean = str(title or "").strip()
    return default_page_title(new_id) if clean == default_page_title(old_id) else clean


def reindex_blueprint_slides(slides: list, deleted_slide_id: int) -> list:
    next_slides: list[dict[str, Any]] = []
    for old_index, slide in enumerate(slides, start=1):
        if old_index == deleted_slide_id:
            continue
        if not isinstance(slide, dict):
            slide = {}
        new_id = len(next_slides) + 1
        next_slide = dict(slide)
        next_slide["id"] = new_id
        next_slide["title"] = default_title_after_reindex(str(next_slide.get("title") or ""), old_index, new_id)
        content = next_slide.get("content")
        if isinstance(content, dict):
            next_content = dict(content)
            for key in ("headline", "statement"):
                if str(next_content.get(key) or "") == default_page_title(old_index):
                    next_content[key] = default_page_title(new_id)
            next_slide["content"] = next_content
        next_slides.append(next_slide)
    return next_slides


def reindex_blueprint_slides_after_insert(slides: list, inserted_slide_id: int, inserted_slide: dict) -> list:
    next_slides: list[dict[str, Any]] = []

    def append_existing(old_index: int, item: Any) -> None:
        if not isinstance(item, dict):
            item = {}
        new_id = len(next_slides) + 1
        next_slide = dict(item)
        next_slide["id"] = new_id
        next_slide["title"] = default_title_after_reindex(str(next_slide.get("title") or ""), old_index, new_id)
        content = next_slide.get("content")
        if isinstance(content, dict):
            next_content = dict(content)
            for key in ("headline", "statement"):
                if str(next_content.get(key) or "") == default_page_title(old_index):
                    next_content[key] = default_page_title(new_id)
            next_slide["content"] = next_content
        next_slides.append(next_slide)

    for old_index, slide in enumerate(slides, start=1):
        if old_index == inserted_slide_id:
            next_slide = dict(inserted_slide)
            next_slide["id"] = inserted_slide_id
            next_slides.append(next_slide)
        append_existing(old_index, slide)
    if inserted_slide_id > len(slides):
        next_slide = dict(inserted_slide)
        next_slide["id"] = inserted_slide_id
        next_slides.append(next_slide)
    return next_slides


def reindex_slide_plan_items(items: list, deleted_slide_id: int, id_key: str) -> list:
    next_items: list[dict[str, Any]] = []
    for old_index, item in enumerate(items, start=1):
        item_id = old_index
        if isinstance(item, dict):
            item_id = int(item.get(id_key) or item.get("id") or old_index)
        if item_id == deleted_slide_id:
            continue
        if not isinstance(item, dict):
            item = {}
        new_id = len(next_items) + 1
        next_item = dict(item)
        next_item[id_key] = new_id
        if "id" in next_item:
            next_item["id"] = new_id
        next_item["title"] = default_title_after_reindex(str(next_item.get("title") or ""), item_id, new_id)
        next_items.append(next_item)
    return next_items


def reindex_slide_plan_items_after_insert(items: list, inserted_slide_id: int, inserted_item: dict, id_key: str) -> list:
    next_items: list[dict[str, Any]] = []

    def append_existing(old_index: int, item: Any) -> None:
        item_id = old_index
        if isinstance(item, dict):
            item_id = int(item.get(id_key) or item.get("id") or old_index)
        if not isinstance(item, dict):
            item = {}
        new_id = len(next_items) + 1
        next_item = dict(item)
        next_item[id_key] = new_id
        if "id" in next_item:
            next_item["id"] = new_id
        next_item["title"] = default_title_after_reindex(str(next_item.get("title") or ""), item_id, new_id)
        next_items.append(next_item)

    for old_index, item in enumerate(items, start=1):
        item_id = old_index
        if isinstance(item, dict):
            item_id = int(item.get(id_key) or item.get("id") or old_index)
        if item_id == inserted_slide_id:
            next_item = dict(inserted_item)
            next_item[id_key] = inserted_slide_id
            if "id" in next_item:
                next_item["id"] = inserted_slide_id
            next_items.append(next_item)
        append_existing(old_index, item)
    if inserted_slide_id > len(items):
        next_item = dict(inserted_item)
        next_item[id_key] = inserted_slide_id
        if "id" in next_item:
            next_item["id"] = inserted_slide_id
        next_items.append(next_item)
    return next_items


def reindex_status_slides(target: Path, status_slides: list, deleted_slide_id: int) -> list:
    def slide_svg_exists(slide_num: int) -> bool:
        output_svg = target / "svg_output" / f"slide_{slide_num:02d}.svg"
        final_svg = target / "svg_final" / f"slide_{slide_num:02d}.svg"
        return output_svg.exists() or final_svg.exists()

    next_slides: list[dict[str, Any]] = []
    for old_index, slide in enumerate(status_slides, start=1):
        item_id = old_index
        if isinstance(slide, dict):
            item_id = int(slide.get("slide_id") or old_index)
        if item_id == deleted_slide_id:
            continue
        if not isinstance(slide, dict):
            slide = {}
        new_id = len(next_slides) + 1
        next_slide = dict(slide)
        next_slide["slide_id"] = new_id
        next_slide["title"] = default_title_after_reindex(str(next_slide.get("title") or ""), item_id, new_id)
        next_slide["svg_path"] = f"svg_output/slide_{new_id:02d}.svg"
        next_slide["has_svg"] = slide_svg_exists(new_id)
        if not next_slide["has_svg"]:
            next_slide["qa_status"] = "not_run"
            if next_slide.get("status") not in {"waiting_prompt"}:
                next_slide["status"] = "waiting_codex"
            next_slide["last_error"] = ""
        next_slides.append(next_slide)
    return next_slides


def reindex_status_slides_after_insert(target: Path, status_slides: list, inserted_slide_id: int, inserted_status: dict) -> list:
    def slide_svg_exists(slide_num: int) -> bool:
        output_svg = target / "svg_output" / f"slide_{slide_num:02d}.svg"
        final_svg = target / "svg_final" / f"slide_{slide_num:02d}.svg"
        return output_svg.exists() or final_svg.exists()

    next_slides: list[dict[str, Any]] = []

    def append_existing(old_index: int, item: Any) -> None:
        item_id = old_index
        if isinstance(item, dict):
            item_id = int(item.get("slide_id") or old_index)
        if not isinstance(item, dict):
            item = {}
        new_id = len(next_slides) + 1
        next_slide = dict(item)
        next_slide["slide_id"] = new_id
        next_slide["title"] = default_title_after_reindex(str(next_slide.get("title") or ""), item_id, new_id)
        next_slide["svg_path"] = f"svg_output/slide_{new_id:02d}.svg"
        next_slide["has_svg"] = slide_svg_exists(new_id)
        if not next_slide["has_svg"]:
            next_slide["qa_status"] = "not_run"
            if next_slide.get("status") not in {"waiting_prompt"}:
                next_slide["status"] = "waiting_codex"
            next_slide["last_error"] = ""
        next_slides.append(next_slide)

    for old_index, slide in enumerate(status_slides, start=1):
        item_id = old_index
        if isinstance(slide, dict):
            item_id = int(slide.get("slide_id") or old_index)
        if item_id == inserted_slide_id:
            next_slide = dict(inserted_status)
            next_slide["slide_id"] = inserted_slide_id
            next_slide["svg_path"] = f"svg_output/slide_{inserted_slide_id:02d}.svg"
            next_slide["has_svg"] = False
            next_slides.append(next_slide)
        append_existing(old_index, slide)
    if inserted_slide_id > len(status_slides):
        next_slide = dict(inserted_status)
        next_slide["slide_id"] = inserted_slide_id
        next_slide["svg_path"] = f"svg_output/slide_{inserted_slide_id:02d}.svg"
        next_slide["has_svg"] = False
        next_slides.append(next_slide)
    return next_slides


def clear_stale_delivery_artifacts(target: Path) -> None:
    remove_path(target / "exports" / "output-native.pptx")
    remove_path(target / "exports" / "output.pptx")
    for qa_name in ("report.md", "report.json", "contact-sheet.png", "repair_plan.json"):
        remove_path(target / "qa" / qa_name)


def delete_slide_from_project(target: Path, slide_id: int) -> dict:
    blueprint = read_blueprint(target)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json slides must be a list.")
    if slide_id < 1 or slide_id > len(slides):
        raise ValueError("slide id does not exist in blueprint.")

    archive_path = archive_deleted_slide_artifacts(target, slide_id)
    delete_slide_artifacts(target, slide_id)
    for old_id in range(slide_id + 1, len(slides) + 1):
        rename_slide_artifacts(target, old_id, old_id - 1)

    blueprint["slides"] = reindex_blueprint_slides(slides, slide_id)
    write_json(target / "blueprint.json", blueprint)

    visual_path = target / "slide_visual_plan.json"
    visual_plan = read_json(visual_path, {})
    if isinstance(visual_plan, dict):
        visual_slides = visual_plan.get("slides")
        if isinstance(visual_slides, list):
            visual_plan["slides"] = reindex_slide_plan_items(visual_slides, slide_id, "slide_id")
            write_json(visual_path, visual_plan)

    slide_plan_path = target / "slide_plan.json"
    slide_plan = read_json(slide_plan_path, {})
    if isinstance(slide_plan, dict):
        slide_plan_items = slide_plan.get("slides")
        if isinstance(slide_plan_items, list):
            slide_plan["slides"] = reindex_slide_plan_items(slide_plan_items, slide_id, "slide_id")
            write_json(slide_plan_path, slide_plan)

    clear_stale_delivery_artifacts(target)
    status = load_status(target) or build_initial_status_from_blueprint(target.name, target)
    status_slides = status.setdefault("slides", [])
    if not isinstance(status_slides, list):
        raise ValueError("workbench_status.json slides must be a list.")
    status["slides"] = reindex_status_slides(target, status_slides, slide_id)
    status["slide_count"] = len(status["slides"])
    status["project_status"] = "svg_partial" if status["slides"] else "project_created"
    export = status.setdefault("export", {})
    if isinstance(export, dict):
        export["status"] = "not_ready"
        export["ready"] = False
        export["pptx_path"] = ""
        export["last_returncode"] = None
        export["last_error"] = "页面已删除，请重新生成或导出 PPT。"
    status["recommended_next_action"] = {
        "key": "auto_generate" if any(not item.get("has_svg") for item in status["slides"]) else "qa_slide",
        "label": "继续生成页面" if any(not item.get("has_svg") for item in status["slides"]) else "检查页面",
        "detail": "页面已删除，后续页已前移。请继续生成或检查页面。",
    }
    apply_formal_planning_status(status, run_formal_planning(target))
    add_event(status, "slide_deleted", f"Slide {slide_id} archived and following slides reindexed.")
    save_status(target, status)
    selected_slide_id = min(slide_id, len(status["slides"])) if status["slides"] else 1
    return {
        "deleted_slide_id": slide_id,
        "selected_slide_id": selected_slide_id,
        "slide_count": len(status["slides"]),
        "archive_path": archive_path,
        "status": status,
    }


def append_slide_to_project(
    target: Path,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
) -> dict:
    page_type = require_page_type(page_type)
    content_handling = normalize_content_handling(content_handling)
    page_style = normalize_page_style(page_style)
    status = load_status(target) or build_initial_status_from_blueprint(target.name, target)
    if is_true_single_page_workflow(status):
        raise ValueError("单页任务只能保留 1 页。需要多页 PPT 时，请新建多页任务。")
    blueprint = read_blueprint(target)
    slides = blueprint.setdefault("slides", [])
    if not isinstance(slides, list):
        raise ValueError("blueprint.json slides must be a list.")
    slide_id = len(slides) + 1
    clean_prompt = normalize_submission_prompt(prompt)
    clean_title = normalize_page_title(slide_id, title, clean_prompt)
    slides.append(build_page_slide(slide_id, page_type, clean_title, clean_prompt, content_handling, page_style))
    write_json(target / "blueprint.json", blueprint)

    visual_path = target / "slide_visual_plan.json"
    visual_plan = read_json(visual_path, {})
    if not isinstance(visual_plan, dict):
        visual_plan = {}
    visual_slides = visual_plan.setdefault("slides", [])
    if not isinstance(visual_slides, list):
        raise ValueError("slide_visual_plan.json slides must be a list.")
    visual_slides.append(
        build_page_visual_plan(slide_id, page_type, clean_title, clean_prompt, content_handling, page_style)
    )
    write_json(visual_path, visual_plan)

    if str(status.get("deck_type") or "").strip() == "single":
        status["deck_type"] = "multi"
        status["workflow_mode"] = "prompt_deck"
        status["workflow_label"] = "一句话生成 PPT"
        status["route_id"] = "multi_consulting_free"
        status["route_label"] = "多页咨询风自由设计路径"
    status_slides = status.setdefault("slides", [])
    if not isinstance(status_slides, list):
        raise ValueError("workbench_status.json slides must be a list.")
    status_slides.append(build_page_status(slide_id, page_type, clean_title, clean_prompt, content_handling, page_style))
    status["slide_count"] = len(status_slides)
    apply_formal_planning_status(status, run_formal_planning(target))
    add_event(status, "slide_appended", f"Slide {slide_id} appended.")
    save_status(target, status)
    return {"slide_id": slide_id, "slide_count": len(status_slides), "status": status_slides[-1]}


def insert_slide_after_project(
    target: Path,
    after_slide_id: int,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
) -> dict:
    page_type = require_page_type(page_type)
    content_handling = normalize_content_handling(content_handling)
    page_style = normalize_page_style(page_style)
    status = load_status(target) or build_initial_status_from_blueprint(target.name, target)
    if is_true_single_page_workflow(status):
        raise ValueError("单页任务只能保留 1 页。需要多页 PPT 时，请新建多页任务。")
    blueprint = read_blueprint(target)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json slides must be a list.")
    if after_slide_id < 1 or after_slide_id > len(slides):
        raise ValueError("insert position does not exist in blueprint.")

    inserted_slide_id = after_slide_id + 1
    for old_id in range(len(slides), after_slide_id, -1):
        rename_slide_artifacts(target, old_id, old_id + 1)

    clean_prompt = normalize_submission_prompt(prompt)
    clean_title = normalize_page_title(inserted_slide_id, title, clean_prompt)
    inserted_slide = build_page_slide(
        inserted_slide_id,
        page_type,
        clean_title,
        clean_prompt,
        content_handling,
        page_style,
    )
    blueprint["slides"] = reindex_blueprint_slides_after_insert(slides, inserted_slide_id, inserted_slide)
    write_json(target / "blueprint.json", blueprint)

    inserted_visual = build_page_visual_plan(
        inserted_slide_id,
        page_type,
        clean_title,
        clean_prompt,
        content_handling,
        page_style,
    )
    visual_path = target / "slide_visual_plan.json"
    visual_plan = read_json(visual_path, {})
    if not isinstance(visual_plan, dict):
        visual_plan = {}
    visual_slides = visual_plan.setdefault("slides", [])
    if not isinstance(visual_slides, list):
        raise ValueError("slide_visual_plan.json slides must be a list.")
    visual_plan["slides"] = reindex_slide_plan_items_after_insert(visual_slides, inserted_slide_id, inserted_visual, "slide_id")
    write_json(visual_path, visual_plan)

    slide_plan_path = target / "slide_plan.json"
    slide_plan = read_json(slide_plan_path, {})
    if isinstance(slide_plan, dict):
        slide_plan_items = slide_plan.get("slides")
        if isinstance(slide_plan_items, list):
            slide_plan["slides"] = reindex_slide_plan_items_after_insert(slide_plan_items, inserted_slide_id, inserted_visual, "slide_id")
            write_json(slide_plan_path, slide_plan)

    clear_stale_delivery_artifacts(target)
    if str(status.get("deck_type") or "").strip() == "single":
        status["deck_type"] = "multi"
        status["workflow_mode"] = "prompt_deck"
        status["workflow_label"] = "一句话生成 PPT"
        status["route_id"] = "multi_consulting_free"
        status["route_label"] = "多页咨询风自由设计路径"
    status_slides = status.setdefault("slides", [])
    if not isinstance(status_slides, list):
        raise ValueError("workbench_status.json slides must be a list.")
    inserted_status = build_page_status(
        inserted_slide_id,
        page_type,
        clean_title,
        clean_prompt,
        content_handling,
        page_style,
    )
    status["slides"] = reindex_status_slides_after_insert(target, status_slides, inserted_slide_id, inserted_status)
    status["slide_count"] = len(status["slides"])
    status["project_status"] = "svg_partial"
    export = status.setdefault("export", {})
    if isinstance(export, dict):
        export["status"] = "not_ready"
        export["ready"] = False
        export["pptx_path"] = ""
        export["last_returncode"] = None
        export["last_error"] = "页面已插入，请生成新页面并重新导出 PPT。"
    status["recommended_next_action"] = {
        "key": "auto_generate",
        "label": "继续生成页面",
        "detail": "页面已插入，请填写或生成新页面。",
    }
    apply_formal_planning_status(status, run_formal_planning(target))
    add_event(status, "slide_inserted", f"Slide {inserted_slide_id} inserted after slide {after_slide_id}.")
    save_status(target, status)
    return {
        "slide_id": inserted_slide_id,
        "slide_count": len(status["slides"]),
        "status": inserted_status,
    }


def update_page_authoring_evidence(
    target: Path,
    slide_id: int,
    page_type: str,
    title: str,
    prompt: str,
    content_handling: str = DEFAULT_CONTENT_HANDLING,
    page_style: str = DEFAULT_PAGE_STYLE,
) -> tuple[dict, int]:
    page_type = require_page_type(page_type)
    content_handling = normalize_content_handling(content_handling)
    page_style = normalize_page_style(page_style)
    blueprint = read_blueprint(target)
    slides = blueprint.get("slides")
    if not isinstance(slides, list) or slide_id > len(slides):
        raise ValueError("slide id does not exist in blueprint.")
    clean_prompt = normalize_submission_prompt(prompt)
    clean_title = normalize_page_title(slide_id, title, clean_prompt)
    slide = slides[slide_id - 1]
    if not isinstance(slide, dict):
        slide = {}
        slides[slide_id - 1] = slide
    slide_content = slide.get("content")
    current_content: dict[str, Any] = slide_content if isinstance(slide_content, dict) else {}
    next_content = {
        **current_content,
        **build_blueprint_content_fields(clean_title, clean_prompt),
    }
    slide.update(
        {
            "id": int(slide.get("id") or slide_id),
            "title": clean_title,
            "layout_tag": str(slide.get("layout_tag") or DEFAULT_LAYOUT_TAG),
            "page_type": page_type,
            "content_handling": content_handling,
            "page_style": page_style,
            "narrative_intent": str(
                slide.get("narrative_intent")
                or "Present this page clearly as part of a progressively authored deck."
            ),
            "content_density": str(slide.get("content_density") or "medium"),
            "content": next_content,
        }
    )
    write_json(target / "blueprint.json", blueprint)

    visual_path = target / "slide_visual_plan.json"
    visual_plan = read_json(visual_path, {})
    if not isinstance(visual_plan, dict):
        visual_plan = {}
    visual_slides = visual_plan.setdefault("slides", [])
    if not isinstance(visual_slides, list):
        raise ValueError("slide_visual_plan.json slides must be a list.")
    visual_item: dict[str, Any] | None = next(
        (
            item
            for item in visual_slides
            if isinstance(item, dict) and int(item.get("slide_id") or item.get("id") or 0) == slide_id
        ),
        None,
    )
    if visual_item is None:
        visual_slides.append(
            build_page_visual_plan(slide_id, page_type, clean_title, clean_prompt, content_handling, page_style)
        )
    else:
        next_visual = build_page_visual_plan(
            slide_id,
            page_type,
            clean_title,
            clean_prompt,
            content_handling,
            page_style,
            mode="update_page",
        )
        next_visual.update(
            {
                key: value
                for key, value in visual_item.items()
                if key
                not in {
                    "slide_id",
                    "title",
                    "page_type",
                    "content_handling",
                    "page_style",
                    "layout_tag",
                    "visual_brief",
                    "page_type_decision",
                    "circle_role",
                    "selected_archetype",
                    "visual_archetype",
                    "composition_intent",
                    "hierarchy_strategy",
                    "rhythm_role",
                    "argument_pattern",
                    "proof_objects",
                    "variation_rule",
                    "layout_objective",
                    "density_budget",
                    "dominance_map",
                    "must_keep_claims",
                    "visual_contract",
                    "page_prompt_pattern",
                }
            }
        )
        next_visual["slide_id"] = slide_id
        next_visual["title"] = clean_title
        next_visual["page_type"] = page_type
        next_visual["content_handling"] = content_handling
        next_visual["page_style"] = page_style
        next_visual["layout_tag"] = str(visual_item.get("layout_tag") or slide.get("layout_tag") or DEFAULT_LAYOUT_TAG)
        next_visual["visual_brief"] = compact_page_body(clean_prompt, 420) or str(
            visual_item.get("visual_brief") or DEFAULT_VISUAL_BRIEF
        )
        next_visual["execution_policy"] = visual_item.get("execution_policy") or next_visual["execution_policy"]
        visual_item.clear()
        visual_item.update(next_visual)
    write_json(visual_path, visual_plan)

    status = load_status(target) or build_initial_status_from_blueprint(target.name, target)
    status_slides = status.setdefault("slides", [])
    if not isinstance(status_slides, list):
        raise ValueError("workbench_status.json slides must be a list.")
    status_item = next((item for item in status_slides if int(item.get("slide_id") or 0) == slide_id), None)
    if status_item is None:
        status_item = build_page_status(slide_id, page_type, clean_title, clean_prompt, content_handling, page_style)
        status_slides.append(status_item)
    else:
        status_item.update(
            {
                "title": clean_title,
                "page_type": page_type,
                "content_handling": content_handling,
                "page_style": page_style,
                "prompt": clean_prompt,
                "status": "waiting_codex",
                "svg_path": f"svg_output/slide_{slide_id:02d}.svg",
                "has_svg": (target / "svg_output" / f"slide_{slide_id:02d}.svg").exists(),
                "qa_status": "not_run",
                "last_error": "",
            }
        )
        status_item.setdefault("revision_count", 0)
    status["slide_count"] = len(status_slides)
    apply_formal_planning_status(status, run_formal_planning(target))
    return status, len(slides)


def repair_budget_overload(target: Path, slide_ids: list[int] | None = None) -> dict:
    blueprint = read_blueprint(target)
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json slides must be a list.")

    selected = {int(item) for item in (slide_ids or []) if int(item) > 0}
    updated_slides: list[int] = []
    for index, slide in enumerate(slides, start=1):
        if selected and index not in selected:
            continue
        if not isinstance(slide, dict):
            continue
        raw_content = slide.get("content")
        content: dict[str, Any] = raw_content if isinstance(raw_content, dict) else {}
        title = str(slide.get("title") or content.get("headline") or f"Slide {index}").strip()
        source_prompt = str(content.get("body") or content.get("support") or title)
        next_content = {**content, **build_blueprint_content_fields(title, source_prompt)}
        if content != next_content:
            slide["content"] = next_content
            updated_slides.append(index)

    if not updated_slides:
        return {"updated_slides": [], "slide_count": len(slides)}

    write_json(target / "blueprint.json", blueprint)

    visual_path = target / "slide_visual_plan.json"
    visual_plan = read_json(visual_path, {})
    if isinstance(visual_plan, dict):
        visual_slides = visual_plan.get("slides")
        if isinstance(visual_slides, list):
            for item in visual_slides:
                if not isinstance(item, dict):
                    continue
                sid = int(item.get("slide_id") or item.get("id") or 0)
                if sid <= 0 or sid not in updated_slides:
                    continue
                item["visual_brief"] = compact_page_body(str(item.get("visual_brief") or ""), 420) or DEFAULT_VISUAL_BRIEF
            write_json(visual_path, visual_plan)

    status = load_status(target) or build_initial_status_from_blueprint(target.name, target)
    apply_formal_planning_status(status, run_formal_planning(target))
    add_event(
        status,
        "budget_repaired",
        f"Compacted blueprint text budget for slides: {', '.join(str(item) for item in updated_slides)}.",
    )
    save_status(target, status)
    return {"updated_slides": updated_slides, "slide_count": len(slides)}
