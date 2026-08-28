from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_CTX: dict = {}


def _context_not_ready(name: str) -> RuntimeError:
    return RuntimeError(f"workbench.task_writer context is not initialized: {name}")


def _require_non_empty(value: object, field: str) -> str:
    del value, field
    raise _context_not_ready("require_non_empty")


def _require_choice(value: object, field: str, choices: set[str]) -> str:
    del value, field, choices
    raise _context_not_ready("require_choice")


def _page_count_from_payload(payload: dict) -> int:
    del payload
    raise _context_not_ready("page_count_from_payload")


def _validate_project_name(name: str) -> str:
    del name
    raise _context_not_ready("validate_project_name")


def _build_project_name(deck_type: str) -> str:
    del deck_type
    raise _context_not_ready("build_project_name")


def _project_dir(name: str) -> Path:
    del name
    raise _context_not_ready("project_dir")


def _template_binding_status(target: Path) -> dict:
    del target
    raise _context_not_ready("template_binding_status")


def _bind_template_to_project(target: Path, template_id: str, *, layouts_dir: Path) -> bool:
    del target, template_id, layouts_dir
    raise _context_not_ready("bind_template_to_project")


def _resolve_route(deck_type: str, style_key: str, template_mode: str, *, template_bound: bool) -> dict:
    del deck_type, style_key, template_mode, template_bound
    raise _context_not_ready("resolve_route")


def _split_prompt(prompt: str, count: int) -> list[dict[str, str]]:
    del prompt, count
    raise _context_not_ready("split_prompt")


def _write_project_files(name: str, payload: dict) -> dict:
    del name, payload
    raise _context_not_ready("write_project_files")


def _write_json(path: Path, payload: dict) -> None:
    del path, payload
    raise _context_not_ready("write_json")

def _run_skill_command(args: list[str]) -> dict:
    del args
    raise _context_not_ready("run_skill_command")

def _run_document_intake(project_name: str, quality_threshold: int = 55) -> dict:
    del project_name, quality_threshold
    raise _context_not_ready("run_document_intake")


require_non_empty: Callable[[object, str], str] = _require_non_empty
require_choice: Callable[[object, str, set[str]], str] = _require_choice
page_count_from_payload: Callable[[dict], int] = _page_count_from_payload
validate_project_name: Callable[[str], str] = _validate_project_name
build_project_name: Callable[[str], str] = _build_project_name
project_dir: Callable[[str], Path] = _project_dir
template_binding_status: Callable[[Path], dict] = _template_binding_status
bind_template_to_project: Callable[..., bool] = _bind_template_to_project
resolve_route: Callable[..., dict] = _resolve_route
split_prompt: Callable[[str, int], list[dict[str, str]]] = _split_prompt
write_project_files: Callable[[str, dict], dict] = _write_project_files
write_json: Callable[[Path, dict], None] = _write_json
run_skill_command: Callable[[list[str]], dict] = _run_skill_command
run_document_intake: Callable[[str, int], dict] = _run_document_intake

DOCUMENT_PLANNING_MAX_SOURCE_CHARS = 100_000
DOCUMENT_PLANNING_MAX_CHARS_PER_SOURCE = 50_000

DECK_TYPES: set[str] = set()
SCENES: set[str] = set()
STYLE_PROFILES: set[str] = set()
TEMPLATE_MODES: dict[str, dict[str, Any]] = {}
template_layouts_dir: Path = Path("")
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

def normalize_workflow_mode(value: object, deck_type: str = "multi") -> str:
    mode = str(value or "").strip()
    if mode in WORKFLOW_LABELS:
        return mode
    return "single_page" if deck_type == "single" else "prompt_deck"

def workflow_label(mode: str) -> str:
    return WORKFLOW_LABELS.get(mode, "常规 PPT 生成")

def route_policy_text(route: dict) -> str:
    allowed = ", ".join(route["allowed_actions"])
    forbidden = ", ".join(route["forbidden_actions"])
    return f"Allowed: {allowed}. Forbidden: {forbidden}."

def parse_source_inputs(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        rows = [raw]
    elif isinstance(raw, list):
        rows = [str(item) for item in raw if str(item or "").strip()]
    else:
        rows = [str(raw)]
    normalized: list[str] = []
    for row in rows:
        for piece in row.splitlines():
            candidate = piece.strip()
            if candidate:
                normalized.append(candidate)
    if len(normalized) > 20:
        raise ValueError("source_inputs supports at most 20 items.")
    return normalized

def import_sources_for_document(project_name: str, source_inputs: list[str], move_files: bool) -> dict:
    project_path = str(project_dir(project_name))
    args = [
        "scripts/ppt_master/project_manager.py",
        "import-sources",
        project_path,
        *source_inputs,
    ]
    if move_files:
        args.append("--move")
    result = run_skill_command(args)
    if int(result.get("returncode", 1)) != 0:
        details = str(result.get("stderr") or result.get("stdout") or "").strip()
        detail_line = details.splitlines()[-1] if details else "import-sources failed."
        raise ValueError(f"文档导入失败：{detail_line}")
    return {
        "count": len(source_inputs),
        "items": source_inputs,
        "move_files": bool(move_files),
        "stdout": str(result.get("stdout") or "").strip(),
    }

def run_document_intake_for_document(project_name: str, quality_threshold: int = 55) -> dict:
    result = run_document_intake(project_name, quality_threshold)
    if not isinstance(result, dict):
        raise ValueError("文档 Intake 返回结果无效。")
    gate_passed = bool(result.get("gate_passed"))
    parse_quality_score = int(result.get("parse_quality_score") or 0)
    response = {
        "project": project_name,
        "quality_threshold": quality_threshold,
        "parse_quality_score": parse_quality_score,
        "gate_passed": gate_passed,
        "fallback_triggered": bool(result.get("fallback_triggered", False)),
        "record_count": int(result.get("record_count") or 0),
        "artifacts": {
            "source_manifest": str(result.get("source_manifest_path") or ""),
            "document_ir": str(result.get("document_ir_path") or ""),
            "parse_report": str(result.get("parse_report_path") or ""),
        },
    }
    if not gate_passed:
        response["warning"] = (
            "Intake quality gate is not passed yet. "
            "Please review parse_report.json and补齐源文档/假设后再进入正式规划。"
        )
    return response


def build_document_planning_context(project_name: str) -> str:
    project_path = project_dir(project_name).resolve()
    manifest_path = project_path / "sources" / "manifest.json"
    if not manifest_path.is_file():
        return ""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取 source manifest：{exc}") from exc
    records = manifest.get("records") if isinstance(manifest, dict) else None
    if not isinstance(records, list):
        return ""

    blocks: list[str] = []
    total_chars = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        markdown_ref = str(record.get("markdown") or "").strip()
        if not markdown_ref:
            continue
        markdown_path = Path(markdown_ref)
        if not markdown_path.is_absolute():
            markdown_path = project_path / markdown_path
        markdown_path = markdown_path.resolve()
        if project_path not in markdown_path.parents or not markdown_path.is_file():
            continue
        try:
            source_text = markdown_path.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").strip()
        except OSError as exc:
            raise ValueError(f"无法读取 source markdown：{markdown_ref} ({exc})") from exc
        if not source_text:
            continue

        remaining = DOCUMENT_PLANNING_MAX_SOURCE_CHARS - total_chars
        if remaining <= 0:
            break
        source_limit = min(DOCUMENT_PLANNING_MAX_CHARS_PER_SOURCE, remaining)
        chunk = source_text[:source_limit]
        truncated = len(source_text) > source_limit
        source_id = str(record.get("id") or record.get("original") or markdown_ref).strip()
        truncation_note = (
            f"\n[该 source 已截取前 {source_limit} 个字符，剩余内容未进入本次规划上下文。]"
            if truncated
            else ""
        )
        block = f"--- source_id: {source_id} ---\n{chunk}{truncation_note}"
        blocks.append(block)
        total_chars += len(chunk) + len(truncation_note)

    return "\n\n".join(blocks)[:DOCUMENT_PLANNING_MAX_SOURCE_CHARS]


def prepare_document_sources(payload: dict) -> dict[str, Any] | None:
    workflow_mode = normalize_workflow_mode(payload.get("workflow_mode"), str(payload.get("deck_type", "multi")))
    source_inputs = parse_source_inputs(payload.get("source_inputs"))
    page_count = page_count_from_payload(payload)
    if workflow_mode != "document_deck" or not source_inputs or page_count <= 1:
        return None

    deck_type = require_choice(payload.get("deck_type", "single"), "deck_type", DECK_TYPES)
    project_name = validate_project_name(str(payload.get("project_name") or build_project_name(deck_type)))
    target = project_dir(project_name)
    new_project = not target.exists()
    target.mkdir(parents=True, exist_ok=True)
    source_import = import_sources_for_document(project_name, source_inputs, bool(payload.get("source_move")))
    source_intake = run_document_intake_for_document(project_name)
    if not bool(source_intake.get("gate_passed")):
        warning = str(source_intake.get("warning") or "").strip()
        detail = warning or "请检查 parse_report.json 并补充可用源材料。"
        raise ValueError(f"文档 Intake 未通过，已停止内容规划：{detail}")
    source_grounded_context = build_document_planning_context(project_name)
    if not source_grounded_context.strip():
        raise ValueError("文档 Intake 已通过，但没有提取到可用于内容规划的正文。")
    return {
        "project_name": project_name,
        "new_project": new_project,
        "source_import": source_import,
        "source_intake": source_intake,
        "source_grounded_context": source_grounded_context,
    }

def create_agent_task(
    name: str,
    slides: list[dict[str, str]],
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    slide_lines = "\n".join(
        f"- `svg_output/slide_{index:02d}.svg`"
        for index, slide in enumerate(slides, start=1)
    )
    return f"""# Agent Task: PPT SVG Authoring

This is a Codex companion workbench task.
The browser did not generate AI content.
Codex must author the SVG files.

Project: `my-ppt-skill/projects/{name}`

Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}

## Required output

Write one SVG file per slide:

{slide_lines}

## Read before editing

- `design_spec.md`
- `blueprint.json`
- `agent_tasks/slide_XX.md`

## Forbidden

- Do not run `render_svg.py` to overwrite AI-authored SVG.
- Do not use `pptxgenjs`.
- Do not create a temporary python-pptx exporter.
- Do not modify slides outside the requested slide when working from a single-slide task.

## After Authoring

Return to the workbench and run:

```powershell
cd my-ppt-skill
python scripts/qa_project.py projects/{name} --snapshots
```
"""

def create_slide_task(
    name: str,
    slide: dict[str, str],
    slide_id: int,
    total: int,
    template_mode: str,
    template_instruction: str,
    route: dict,
    template_binding: dict,
) -> str:
    slide_path = f"svg_output/slide_{slide_id:02d}.svg"
    return f"""# Codex Slide Task

Project: `my-ppt-skill/projects/{name}`
Slide: `{slide_id}` of `{total}`
Output: `{slide_path}`
Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}

## Read First

1. `design_spec.md`
2. `outline.md`
3. `blueprint.json`
4. `art_direction.md`
5. `slide_visual_plan.json`

## Slide Brief

- Title: {slide['title']}
- Body: {slide['body']}

## Rules

- Only edit `my-ppt-skill/projects/{name}/{slide_path}`.
- Do not modify other slides.
- Do not run `render_svg.py`.
- Use `viewBox="0 0 1280 720"`.
- Use native SVG text elements only.
- Do not use `foreignObject`.
- Save the file immediately at `{slide_path}`.
- Run a structure pass, polish pass, and critic gate before stopping.

## After Editing

```powershell
cd my-ppt-skill
python scripts/qa_project.py projects/{name} --snapshots --slide {slide_id}
```
"""

def create_slide_regenerate_task(
    name: str,
    slide: dict[str, str],
    slide_id: int,
    total: int,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    target_svg = f"svg_output/slide_{slide_id:02d}.svg"
    do_not_edit = "\n".join(
        f"- `svg_output/slide_{index:02d}.svg`"
        for index in range(1, total + 1)
        if index != slide_id
    )
    return f"""# Codex Slide Regenerate Task

Project: `my-ppt-skill/projects/{name}`
Slide: `{slide_id}` of `{total}`
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}
Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}

## Required

Regenerate only:
- `{target_svg}`

Do not edit:
{do_not_edit or "- (none)"}

## Rules

- Do not run `render_svg.py`.
- Do not use `pptxgenjs`.
- Do not create temporary python-pptx exporter.
- Keep other pages unchanged.

## Slide Brief

- Title: {slide['title']}
- Body: {slide['body']}

## After Editing

```powershell
cd my-ppt-skill
python scripts/qa_project.py projects/{name} --snapshots --slide {slide_id}
```
"""

def create_slide_repair_task(
    name: str,
    slide_id: int,
    total: int,
    qa_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    target_svg = f"svg_output/slide_{slide_id:02d}.svg"
    do_not_edit = "\n".join(
        f"- `svg_output/slide_{index:02d}.svg`"
        for index in range(1, total + 1)
        if index != slide_id
    )
    excerpt = (qa_excerpt or "No QA excerpt captured.").strip()[:1800]
    return f"""# Codex Slide Repair Task

Project: `my-ppt-skill/projects/{name}`
Slide: `{slide_id}` of `{total}`
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}
Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}

QA reported issues for slide {slide_id:02d}:
{excerpt}

Please repair only:
- `{target_svg}`

Do not modify:
{do_not_edit or "- (none)"}

Do not run `render_svg.py`.

After repair, run:

```powershell
cd my-ppt-skill
python scripts/qa_project.py projects/{name} --snapshots --slide {slide_id}
```
"""

def create_budget_repair_task(
    name: str,
    slide_id: int,
    total: int,
    budget_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    excerpt = (budget_excerpt or "No budget excerpt captured.").strip()[:1800]
    return f"""# Codex Slide Budget Repair Task

Project: `my-ppt-skill/projects/{name}`
Slide: `{slide_id}` of `{total}`
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}
Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}

Budget reported issues for slide {slide_id:02d}:
{excerpt}

## Required

Compress or restructure the slide source content so the deck can pass export readiness.

Allowed source files:
- `blueprint.json`
- `slide_visual_plan.json`
- `agent_tasks/slide_{slide_id:02d}.md`

Keep the current authored SVG unless the source repair explicitly requires a matching text update.

## Rules

- Do not run `render_svg.py`.
- Do not use `pptxgenjs`.
- Do not create a temporary python-pptx exporter.
- Do not modify unrelated slides.
- Keep the slide's main conclusion and business meaning intact while reducing wording.

## After Editing

```powershell
cd my-ppt-skill
python scripts/qa_project.py projects/{name} --snapshots --slide {slide_id}
```
"""

def create_export_diagnostic_task(
    name: str,
    export_excerpt: str,
    route: dict,
    template_mode: str,
    template_instruction: str,
    template_binding: dict,
) -> str:
    excerpt = (export_excerpt or "No export error excerpt captured.").strip()[:1800]
    return f"""# Codex Export Diagnostic Task

Project: `my-ppt-skill/projects/{name}`
Route: `{route.get("route_id")}` / {route.get("label")}
Route policy: {route_policy_text(route)}
Template mode: `{template_mode}`
Template instruction: {template_instruction}
Template bound: `{bool(template_binding.get("bound"))}`
Template binding note: {template_binding.get("note")}

Export reported issues:
{excerpt}

## Required

Diagnose the exporter failure before changing authored slides.

Run the default recovery entry first:

```powershell
cd my-ppt-skill
python scripts/doctor_export.py projects/{name}
```

Then follow the doctor result through authoring/finalize recovery.

## Rules

- Do not run `render_svg.py`.
- Do not use `pptxgenjs`.
- Do not create a temporary python-pptx exporter.
- Do not modify SVG pages unless the doctor or QA evidence identifies a specific slide-level repair.
- Do not bypass `build_project.py --phase finalize --skip-render`.

## Verification

```powershell
cd my-ppt-skill
python scripts/build_project.py projects/{name} --phase finalize --skip-render --enable-layout-lint --enable-visual-qa --strict --safe-area-profile presentation --snapshots
```
"""

def create_workbench_task(
    payload: dict,
    *,
    content_plan: dict[str, Any] | None = None,
    document_context: dict[str, Any] | None = None,
) -> dict:
    from workbench.prompt_intake import normalize_submission_prompt

    raw_prompt = str(payload.get("raw_prompt") or payload.get("prompt") or "")
    prompt = require_non_empty(normalize_submission_prompt(raw_prompt), "prompt")
    deck_type = require_choice(payload.get("deck_type", "single"), "deck_type", DECK_TYPES)
    workflow_mode = normalize_workflow_mode(payload.get("workflow_mode"), deck_type)
    workflow_label_value = workflow_label(workflow_mode)
    source_inputs = parse_source_inputs(payload.get("source_inputs"))
    source_move = bool(payload.get("source_move"))
    page_count = page_count_from_payload(payload)
    scene_key = require_choice(payload.get("scene", "proposal"), "scene", SCENES)
    style_key = require_choice(payload.get("style_profile", "consulting_blue"), "style_profile", STYLE_PROFILES)
    template_mode = require_choice(payload.get("template_mode", "free"), "template_mode", set(TEMPLATE_MODES.keys()))
    generation_mode = "api_auto"
    project_name = validate_project_name(str(payload.get("project_name") or build_project_name(deck_type)))
    target = project_dir(project_name)
    selected_template_id = str(payload.get("selected_template_id") or "").strip()
    if selected_template_id and (not target.exists() or bool(document_context and document_context.get("new_project"))):
        # C13-B：画廊选中模板 → 新项目立即绑定（只写新项目，不覆盖已有绑定）。
        bind_template_to_project(target, selected_template_id, layouts_dir=template_layouts_dir)
    planned_slides = content_plan.get("slides") if isinstance(content_plan, dict) else None
    if content_plan and content_plan.get("status") == "used" and isinstance(planned_slides, list):
        slides = [dict(slide) for slide in planned_slides if isinstance(slide, dict)]
        deck_thesis = str(content_plan.get("deck_thesis") or "").strip()
    else:
        slides = split_prompt(raw_prompt or prompt, page_count)
        deck_thesis = ""
    if len(slides) == 1 and isinstance(slides[0], dict):
        slides[0] = {**slides[0], "prompt": prompt}
    if len(slides) > 1 and workflow_mode in {"prompt_deck", "document_deck"}:
        deck_type = "multi"
        page_count = len(slides)
    if workflow_mode == "document_deck" and not source_inputs and len(slides) <= 1:
        raise ValueError("document_deck requires source_inputs unless the pasted prompt contains explicit pages.")
    project_payload = {
        "project_name": project_name,
        "slide_title": slides[0]["title"],
        "slide_content": prompt,
        "slides": slides,
        "page_count": page_count,
        "scene": scene_key,
        "style_profile": style_key,
        "template_mode": template_mode,
        "generation_mode": generation_mode,
        "deck_type": deck_type,
        "workflow_mode": workflow_mode,
        "deck_thesis": deck_thesis,
    }
    project_data = write_project_files(project_name, project_payload)
    source_import: dict[str, Any] | None = None
    source_intake: dict[str, Any] | None = None
    if document_context is not None:
        source_import = document_context.get("source_import")
        source_intake = document_context.get("source_intake")
    elif workflow_mode == "document_deck" and source_inputs:
        source_import = import_sources_for_document(project_name, source_inputs, source_move)
        source_intake = run_document_intake_for_document(project_name)
    task_id = f"{project_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return {
        "task_id": task_id,
        "project": project_name,
        "project_path": str(project_dir(project_name)),
        "slides": project_data["slides"],
        "route": project_data["route"],
        "template_binding": project_data["template_binding"],
        "template_instruction": project_data["template_instruction"],
        "style_route": project_data["style_route"],
        "workflow_mode": workflow_mode,
        "workflow_label": workflow_label_value,
        "deck_type": deck_type,
        "page_count": page_count,
        "generation_mode": generation_mode,
        "source_import": source_import or {},
        "source_intake": source_intake or {},
    }
