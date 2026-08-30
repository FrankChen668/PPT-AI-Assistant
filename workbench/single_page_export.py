from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


def read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def selected_item(items: list, slide_id: int, id_keys: tuple[str, ...]) -> dict:
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in id_keys:
            try:
                if int(item.get(key) or 0) == int(slide_id):
                    return dict(item)
            except (TypeError, ValueError):
                continue
    raise ValueError(f"Slide {slide_id} is missing from project metadata.")


def optional_selected_item(items: list, slide_id: int, id_keys: tuple[str, ...]) -> dict | None:
    try:
        return selected_item(items, slide_id, id_keys)
    except ValueError:
        return None


def renumber_slide(item: dict, slide_id_key: str = "id") -> dict:
    next_item = dict(item)
    next_item[slide_id_key] = 1
    next_item["slide_no"] = 1
    if "slide_id" in next_item:
        next_item["slide_id"] = 1
    if "id" in next_item:
        next_item["id"] = 1
    return next_item


def first_dict_item(items: list[Any]) -> dict | None:
    for item in items:
        if isinstance(item, dict):
            return dict(item)
    return None


def fallback_blueprint_slide(slide_id: int) -> dict:
    title = f"Slide {slide_id}"
    return {
        "id": 1,
        "title": title,
        "layout_tag": "Statement-Bold",
        "page_type": "content",
        "narrative_intent": "single-slide export fallback content",
        "content": {
            "eyebrow": "",
            "statement": title,
            "support": "",
        },
    }


def fallback_visual_plan_slide(slide_id: int, blueprint_slide: dict) -> dict:
    title = str(blueprint_slide.get("title") or f"Slide {slide_id}")
    return {
        "slide_id": 1,
        "id": 1,
        "title": title,
        "page_type": str(blueprint_slide.get("page_type") or "content"),
        "layout_tag": str(blueprint_slide.get("layout_tag") or "Statement-Bold"),
        "visual_brief": "fallback visual plan generated during single-slide export",
    }


def build_finalize_command(work_dir: Path, *, strict: bool) -> list[str]:
    command = [
        sys.executable,
        "scripts/build_project.py",
        str(work_dir),
        "--phase",
        "finalize",
        "--skip-render",
        "--auto-slide-plan",
        "--auto-slide-plan-overwrite",
        "--enable-layout-lint",
        "--enable-visual-qa",
        "--safe-area-profile",
        "presentation",
        "--snapshots",
    ]
    if strict:
        command.append("--strict")
    return command


def is_locked_file_error(exc: BaseException) -> bool:
    if not isinstance(exc, OSError):
        return False
    if int(getattr(exc, "winerror", 0) or 0) == 32:
        return True
    message = str(exc).lower()
    return (
        "another process" in message
        or "being used by another process" in message
        or "process cannot access the file" in message
        or "另一个程序正在使用此文件" in str(exc)
    )


def run_with_locked_file_retry(operation: Callable[[], None], *, attempts: int = 6, initial_delay_sec: float = 0.12) -> None:
    delay = initial_delay_sec
    for index in range(attempts):
        try:
            operation()
            return
        except OSError as exc:
            if (not is_locked_file_error(exc)) or index >= attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 1.8, 1.0)


def run_finalize(
    runner: Callable[..., subprocess.CompletedProcess],
    command: list[str],
    *,
    cwd: Path,
) -> subprocess.CompletedProcess:
    return runner(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def single_slide_source_svg(project_dir: Path, slide_no: int) -> Path:
    source_svg = project_dir / "svg_output" / f"slide_{slide_no:02d}.svg"
    if not source_svg.exists():
        source_svg = project_dir / "svg_final" / f"slide_{slide_no:02d}.svg"
    if not source_svg.exists():
        raise ValueError(f"Slide {slide_no} SVG is missing.")
    return source_svg


def prepare_single_slide_project(project_dir: Path, slide_id: int, *, slide_no: int | None = None) -> Path:
    project_dir = project_dir.resolve()
    page_number = int(slide_no or slide_id)
    source_svg = single_slide_source_svg(project_dir, page_number)

    work_root = project_dir / "exports" / "single-pages" / "_work"
    work_dir = work_root / f"slide_{page_number:02d}"
    resolved_work = work_dir.resolve()
    resolved_root = work_root.resolve()
    if resolved_root not in resolved_work.parents and resolved_work != resolved_root:
        raise ValueError("Single-slide work directory escaped export workspace.")
    if work_dir.exists():
        run_with_locked_file_retry(lambda: shutil.rmtree(work_dir))
    (work_dir / "svg_output").mkdir(parents=True, exist_ok=True)

    for filename in [
        "design_spec.md",
        "outline.md",
        "style_route.json",
        "art_direction.md",
        "reference_pack.json",
        "template_binding.json",
    ]:
        source = project_dir / filename
        if source.exists():
            shutil.copy2(source, work_dir / filename)

    templates = project_dir / "templates"
    if templates.exists():
        shutil.copytree(templates, work_dir / "templates")

    blueprint = read_json(project_dir / "blueprint.json", {"slides": []})
    blueprint_items = blueprint.get("slides", []) if isinstance(blueprint, dict) else []
    blueprint_slide = optional_selected_item(blueprint_items, slide_id, ("id", "slide_id"))
    if not blueprint_slide:
        blueprint_slide = first_dict_item(blueprint_items) or fallback_blueprint_slide(slide_id)
    normalized_blueprint_slide = renumber_slide(blueprint_slide, "id")
    write_json(work_dir / "blueprint.json", {"slides": [normalized_blueprint_slide]})

    visual_plan = read_json(project_dir / "slide_visual_plan.json", {"slides": []})
    visual_items = visual_plan.get("slides", []) if isinstance(visual_plan, dict) else []
    visual_slide = optional_selected_item(visual_items, slide_id, ("slide_id", "id"))
    if not visual_slide:
        visual_slide = first_dict_item(visual_items) or fallback_visual_plan_slide(slide_id, normalized_blueprint_slide)
    write_json(work_dir / "slide_visual_plan.json", {"slides": [renumber_slide(visual_slide, "slide_id")]})

    slide_plan = read_json(project_dir / "slide_plan.json", {"slides": []})
    plan_items = slide_plan.get("slides", []) if isinstance(slide_plan, dict) else []
    try:
        plan_slide = selected_item(plan_items, slide_id, ("slide_id", "id"))
    except ValueError:
        plan_slide = {}
    if plan_slide:
        write_json(work_dir / "slide_plan.json", {"version": slide_plan.get("version", 1), "slides": [renumber_slide(plan_slide, "slide_id")]})

    shutil.copy2(source_svg, work_dir / "svg_output" / "slide_01.svg")
    return work_dir


def copy_single_slide_output(source_pptx: Path, final_dir: Path, slide_id: int) -> tuple[Path, bool]:
    stable_target = final_dir / f"slide_{slide_id:02d}.pptx"
    try:
        run_with_locked_file_retry(lambda: shutil.copy2(source_pptx, stable_target))
        return stable_target, False
    except OSError as exc:
        if not is_locked_file_error(exc):
            raise
    fallback_target = final_dir / f"slide_{slide_id:02d}--{time.strftime('%Y%m%d-%H%M%S')}.pptx"
    suffix = 1
    while fallback_target.exists():
        fallback_target = final_dir / f"slide_{slide_id:02d}--{time.strftime('%Y%m%d-%H%M%S')}-{suffix}.pptx"
        suffix += 1
    run_with_locked_file_retry(lambda: shutil.copy2(source_pptx, fallback_target))
    return fallback_target, True


def promote_single_slide_work_output(project_dir: Path, slide_id: int) -> Path | None:
    project_dir = project_dir.resolve()
    source_pptx = project_dir / "exports" / "single-pages" / "_work" / f"slide_{slide_id:02d}" / "exports" / "output-native.pptx"
    if not source_pptx.exists() or not source_pptx.is_file():
        return None
    final_dir = project_dir / "exports" / "single-pages"
    final_dir.mkdir(parents=True, exist_ok=True)
    promoted, _locked = copy_single_slide_output(source_pptx, final_dir, slide_id)
    return promoted if promoted.exists() else None


def export_single_slide_pptx(
    project_dir: Path,
    slide_id: int,
    *,
    slide_no: int | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict:
    project_dir = project_dir.resolve()
    page_number = int(slide_no or slide_id)
    skill_dir = project_dir.parents[1]
    work_dir = prepare_single_slide_project(project_dir, slide_id, slide_no=page_number)
    source_svg_sha256 = hashlib.sha256((work_dir / "svg_output" / "slide_01.svg").read_bytes()).hexdigest()
    strict_command = build_finalize_command(work_dir, strict=True)
    strict_completed = run_finalize(runner, strict_command, cwd=skill_dir)
    completed = strict_completed
    fallback_used = False
    strict_output_reused = False
    quality_gate_blocked = strict_completed.returncode != 0
    source_pptx = work_dir / "exports" / "output-native.pptx"
    if strict_completed.returncode != 0:
        if source_pptx.exists():
            completed = subprocess.CompletedProcess(
                strict_completed.args,
                0,
                stdout=strict_completed.stdout,
                stderr=strict_completed.stderr,
            )
            strict_output_reused = True
        else:
            relaxed_command = build_finalize_command(work_dir, strict=False)
            completed = run_finalize(runner, relaxed_command, cwd=skill_dir)
            fallback_used = True

    final_dir = project_dir / "exports" / "single-pages"
    final_dir.mkdir(parents=True, exist_ok=True)
    final_pptx = final_dir / f"slide_{page_number:02d}.pptx"
    stable_target_locked = False
    if source_pptx.exists():
        final_pptx, stable_target_locked = copy_single_slide_output(source_pptx, final_dir, page_number)
    if not final_pptx.exists():
        promoted = promote_single_slide_work_output(project_dir, page_number)
        if promoted is not None:
            final_pptx = promoted
    if completed.returncode == 0:
        summary = "single slide export completed"
        if strict_output_reused and quality_gate_blocked:
            summary = "single slide export completed with review-required findings"
        elif fallback_used and quality_gate_blocked:
            summary = "single slide export completed with relaxed fallback"
        if stable_target_locked:
            summary = f"{summary}; stable target locked, wrote versioned output"
    else:
        summary = "single slide export failed"
    if final_pptx.exists():
        try:
            download_path = str(final_pptx.relative_to(project_dir)).replace("\\", "/")
        except ValueError:
            download_path = str(final_pptx)
    else:
        download_path = ""
    artifact_pptx_sha256 = hashlib.sha256(final_pptx.read_bytes()).hexdigest() if final_pptx.exists() else ""
    return {
        "returncode": int(completed.returncode),
        "stdout": str(completed.stdout or "")[-8000:],
        "stderr": str(completed.stderr or "")[-8000:],
        "strict_stdout": str(strict_completed.stdout or "")[-8000:],
        "strict_stderr": str(strict_completed.stderr or "")[-8000:],
        "strict_returncode": int(strict_completed.returncode),
        "fallback_used": fallback_used,
        "quality_gate_blocked": quality_gate_blocked,
        "export_mode": "relaxed" if fallback_used else "strict",
        "source_svg_sha256": source_svg_sha256,
        "artifact_pptx_sha256": artifact_pptx_sha256,
        "stable_target_locked": stable_target_locked,
        "work_dir": str(work_dir),
        "export_path": str(final_pptx) if final_pptx.exists() else "",
        "download_path": download_path,
        "summary": summary,
    }
