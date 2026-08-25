from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

SKILL_DIR = Path(__file__).resolve().parents[1] / "my-ppt-skill"
SKILL_SCRIPTS_DIR = SKILL_DIR / "scripts"
FORMAL_ARTIFACTS = (
    "style_route.json",
    "reference_pack.json",
    "art_direction.md",
    "design_story_plan.json",
    "slide_visual_plan.json",
)
LEGACY_FALLBACK_ARTIFACTS = (
    "reference_pack.json",
    "art_direction.md",
    "slide_visual_plan.json",
)
REFERENCE_METADATA_KEYS = (
    "route_id",
    "route_label",
    "template_mode",
    "template_instruction",
    "template_bound",
    "template_binding_note",
    "visual_grammar_mode",
    "visual_grammar_references",
    "execution_tokens",
)
BLUEPRINT_BRIDGE_FIELDS = (
    "title",
    "content_handling",
    "page_style",
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
    "page_prompt_pattern",
    "scene_route",
    "execution_policy",
    "execution",
)


class FormalPlanningStageError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def _skill_function(module_name: str, function_name: str) -> Callable[..., Any]:
    scripts_path = str(SKILL_SCRIPTS_DIR)
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    module = importlib.import_module(module_name)
    function = getattr(module, function_name, None)
    if not callable(function):
        raise RuntimeError(f"Skill function is unavailable: {module_name}.{function_name}")
    return function


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object.")
    return payload


def _slide_ids(payload: dict[str, Any], *, id_keys: tuple[str, ...]) -> list[int]:
    slides = payload.get("slides")
    if not isinstance(slides, list):
        raise ValueError("slides must be a list.")
    result: list[int] = []
    for item in slides:
        if not isinstance(item, dict):
            raise ValueError("slides must contain objects.")
        raw_id: Any = None
        for key in id_keys:
            if item.get(key) is not None:
                raw_id = item.get(key)
                break
        if isinstance(raw_id, bool):
            raise ValueError("slide id must be an integer.")
        try:
            slide_id = int(raw_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("slide id must be an integer.") from exc
        result.append(slide_id)
    return result


def _resolve_reference_file(project_dir: Path, value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate.resolve()
    project_candidate = (project_dir / candidate).resolve()
    if project_candidate.is_file():
        return project_candidate
    return (SKILL_DIR / candidate).resolve()


def _free_design_reason(reference_pack: dict[str, Any]) -> str:
    for key in ("free_design_override_reason", "override_reason"):
        value = str(reference_pack.get(key) or "").strip()
        if value:
            return value
    fallback = reference_pack.get("fallback")
    if isinstance(fallback, dict):
        return str(fallback.get("reason") or "").strip()
    return ""


def _validate_reference_pack(project_dir: Path, reference_pack: dict[str, Any]) -> None:
    mode = str(reference_pack.get("mode") or "").strip().lower()
    raw_files = reference_pack.get("reference_files")
    reference_files = list(raw_files) if isinstance(raw_files, list) else []
    if mode == "free-design":
        if reference_files:
            raise ValueError("free-design reference pack must not contain reference files.")
        if not _free_design_reason(reference_pack):
            raise ValueError("free-design reference pack must explain why templates were skipped.")
        return

    primary = str(reference_pack.get("primary_template") or "").strip()
    if not primary:
        raise ValueError("reference_pack.json has no final primary template.")
    if not reference_files:
        raise ValueError("selected template has no reference files.")
    missing = [
        str(item)
        for item in reference_files
        if (_resolve_reference_file(project_dir, item) is None or not _resolve_reference_file(project_dir, item).is_file())
    ]
    if missing:
        raise ValueError(f"selected template references missing files: {missing[:3]}")


def _reference_file_exists(project_dir: Path, value: object) -> bool:
    resolved = _resolve_reference_file(project_dir, value)
    return resolved is not None and resolved.is_file()


def _sanitize_reference_pack(project_dir: Path, reference_pack: dict[str, Any]) -> dict[str, Any]:
    if str(reference_pack.get("mode") or "").strip().lower() == "free-design":
        reference_pack["reference_files"] = []
        return reference_pack

    primary = str(reference_pack.get("primary_template") or "").strip()
    raw_selected = reference_pack.get("selected_templates")
    selected = [dict(item) for item in raw_selected if isinstance(item, dict)] if isinstance(raw_selected, list) else []
    valid_selected: list[dict[str, Any]] = []
    for item in selected:
        raw_files = item.get("reference_files")
        files = [str(value) for value in raw_files if _reference_file_exists(project_dir, value)] if isinstance(raw_files, list) else []
        if not files:
            continue
        item["reference_files"] = files
        valid_selected.append(item)

    primary_entry = next(
        (item for item in valid_selected if str(item.get("template_key") or "").strip() == primary),
        None,
    )
    if selected and primary_entry is None:
        raise ValueError(f"primary template {primary or '(missing)'} has no usable reference files.")

    if valid_selected:
        ordered = [primary_entry] + [item for item in valid_selected if item is not primary_entry]
        ordered = [item for item in ordered if isinstance(item, dict)]
        reference_pack["selected_templates"] = ordered
        reference_pack["references"] = ordered
        reference_pack["secondary_templates"] = [
            str(item.get("template_key") or "") for item in ordered[1:] if str(item.get("template_key") or "").strip()
        ]
        reference_pack["reference_files"] = [
            str(value)
            for item in ordered
            for value in item.get("reference_files", [])
            if str(value).strip()
        ]
    else:
        raw_files = reference_pack.get("reference_files")
        reference_pack["reference_files"] = [
            str(value)
            for value in raw_files
            if _reference_file_exists(project_dir, value)
        ] if isinstance(raw_files, list) else []
    return reference_pack


def _merge_reference_metadata(selected: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    result = dict(selected)
    for key in REFERENCE_METADATA_KEYS:
        if key in previous:
            result[key] = previous[key]
    if (
        str(result.get("mode") or "").strip().lower() == "free-design"
        and previous.get("free_design_override_reason")
    ):
        result["free_design_override_reason"] = str(previous["free_design_override_reason"])
    return result


def _merge_dict_defaults(primary: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    result = dict(primary)
    for key, value in defaults.items():
        if key not in result or _is_empty_bridge_value(result[key]):
            result[key] = value
        elif isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dict_defaults(result[key], value)
    return result


def _is_empty_bridge_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (dict, list, tuple, set)):
        return not value
    return False


def _merge_blueprint_bridge_fields(project_dir: Path, previous_plan: dict[str, Any]) -> None:
    current_path = project_dir / "slide_visual_plan.json"
    current = _read_json(current_path)
    previous_slides = previous_plan.get("slides")
    current_slides = current.get("slides")
    if not isinstance(previous_slides, list) or not isinstance(current_slides, list):
        return
    previous_by_id = {
        int(item.get("slide_id") or item.get("id") or 0): item
        for item in previous_slides
        if isinstance(item, dict) and int(item.get("slide_id") or item.get("id") or 0) > 0
    }
    for item in current_slides:
        if not isinstance(item, dict):
            continue
        slide_id = int(item.get("slide_id") or item.get("id") or 0)
        previous = previous_by_id.get(slide_id)
        if not isinstance(previous, dict):
            continue
        for key in BLUEPRINT_BRIDGE_FIELDS:
            if key in previous:
                if key not in item or _is_empty_bridge_value(item[key]):
                    item[key] = previous[key]
                elif isinstance(item[key], dict) and isinstance(previous[key], dict):
                    item[key] = _merge_dict_defaults(item[key], previous[key])
        previous_contract = previous.get("visual_contract")
        current_contract = item.get("visual_contract")
        if isinstance(previous_contract, dict) and isinstance(current_contract, dict):
            item["visual_contract"] = _merge_dict_defaults(current_contract, previous_contract)
        elif isinstance(previous_contract, dict) and _is_empty_bridge_value(current_contract):
            item["visual_contract"] = previous_contract
    for key in ("layout_exploration", "deck_rhythm_map"):
        if key in previous_plan and key not in current:
            current[key] = previous_plan[key]
    current_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _template_mode(project_dir: Path) -> str:
    clarification_path = project_dir / "clarification_brief.json"
    if not clarification_path.is_file():
        return ""
    try:
        clarification = _read_json(clarification_path)
    except Exception:
        return ""
    return str(clarification.get("template_mode") or "").strip().lower()


def _has_bound_template(project_dir: Path) -> bool:
    clarification_path = project_dir / "clarification_brief.json"
    if not clarification_path.is_file():
        return False
    try:
        clarification = _read_json(clarification_path)
    except Exception:
        return False
    return clarification.get("template_bound") is True and bool(str(clarification.get("template_id") or "").strip())


def _select_reference_pack(project_dir: Path) -> Path:
    select_reference_templates = _skill_function(
        "select_reference_templates",
        "select_reference_templates",
    )
    requested_mode = "free-design" if _template_mode(project_dir) == "free" else None
    existing_path = project_dir / "reference_pack.json"
    previous = _read_json(existing_path) if existing_path.is_file() else {}
    max_templates = 1 if _has_bound_template(project_dir) else 3
    selected_path: Path = select_reference_templates(
        project_dir,
        mode=requested_mode,
        max_templates=max_templates,
    )
    reference_pack = _merge_reference_metadata(_read_json(selected_path), previous)
    try:
        reference_pack = _sanitize_reference_pack(project_dir, reference_pack)
        _validate_reference_pack(project_dir, reference_pack)
    except ValueError:
        if _has_bound_template(project_dir):
            raise
        selected_path = select_reference_templates(project_dir, mode="free-design")
        reference_pack = _read_json(selected_path)
        reference_pack["free_design_override_reason"] = (
            "Formal template selection did not produce usable existing reference files."
        )
        fallback = reference_pack.setdefault("fallback", {})
        if isinstance(fallback, dict):
            fallback["reason"] = "reference_files_unavailable"
        _validate_reference_pack(project_dir, reference_pack)
    selected_path.write_text(
        json.dumps(reference_pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return selected_path


def validate_formal_planning_artifacts(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    try:
        blueprint = _read_json(project_dir / "blueprint.json")
        blueprint_ids = _slide_ids(blueprint, id_keys=("id", "slide_id"))
    except Exception as exc:
        raise FormalPlanningStageError("slide_visual_plan", f"invalid blueprint.json: {exc}") from exc
    if not blueprint_ids:
        raise FormalPlanningStageError("slide_visual_plan", "blueprint.json has no slides.")

    try:
        style_route = _read_json(project_dir / "style_route.json")
    except Exception as exc:
        raise FormalPlanningStageError("style_route", str(exc)) from exc
    if not style_route.get("style_profile"):
        raise FormalPlanningStageError("style_route", "style_route.json has no style_profile.")

    try:
        reference_pack = _read_json(project_dir / "reference_pack.json")
        _validate_reference_pack(project_dir, reference_pack)
    except Exception as exc:
        raise FormalPlanningStageError("template_selection", str(exc)) from exc

    try:
        art_direction = (project_dir / "art_direction.md").read_text(encoding="utf-8").strip()
    except Exception as exc:
        raise FormalPlanningStageError("art_direction", str(exc)) from exc
    if not art_direction:
        raise FormalPlanningStageError("art_direction", "art_direction.md is empty.")

    try:
        design_story = _read_json(project_dir / "design_story_plan.json")
        design_story_ids = _slide_ids(design_story, id_keys=("slide_id", "id"))
    except Exception as exc:
        raise FormalPlanningStageError("design_story_plan", str(exc)) from exc
    if design_story_ids != blueprint_ids:
        raise FormalPlanningStageError(
            "design_story_plan",
            f"design_story_plan slide ids {design_story_ids} do not match blueprint ids {blueprint_ids}.",
        )

    try:
        visual_plan = _read_json(project_dir / "slide_visual_plan.json")
        visual_plan_ids = _slide_ids(visual_plan, id_keys=("slide_id", "id"))
    except Exception as exc:
        raise FormalPlanningStageError("slide_visual_plan", str(exc)) from exc
    if visual_plan_ids != blueprint_ids:
        raise FormalPlanningStageError(
            "slide_visual_plan",
            f"slide_visual_plan slide ids {visual_plan_ids} do not match blueprint ids {blueprint_ids}.",
        )

    return {
        "slide_count": len(blueprint_ids),
        "slide_ids": blueprint_ids,
        "template_mode": str(reference_pack.get("mode") or ""),
        "primary_template": reference_pack.get("primary_template"),
        "reference_files": list(reference_pack.get("reference_files") or []),
    }


def _snapshot_artifacts(project_dir: Path) -> dict[str, bytes | None]:
    return {
        name: (project_dir / name).read_bytes() if (project_dir / name).is_file() else None
        for name in FORMAL_ARTIFACTS
    }


def _restore_artifacts(project_dir: Path, snapshot: dict[str, bytes | None]) -> None:
    for name, content in snapshot.items():
        path = project_dir / name
        if content is None:
            if path.exists():
                path.unlink()
            continue
        path.write_bytes(content)


def _fallback_available(project_dir: Path) -> bool:
    return all((project_dir / name).is_file() for name in LEGACY_FALLBACK_ARTIFACTS)


def _failure_result(project_dir: Path, stage: str, error: BaseException) -> dict[str, Any]:
    message = " ".join(str(error).split())[:500] or error.__class__.__name__
    fallback_used = _fallback_available(project_dir)
    return {
        "formal_planning_status": "fallback" if fallback_used else "failed",
        "fallback_used": fallback_used,
        "failed_stage": stage,
        "failure_message": message,
        "artifacts": [name for name in FORMAL_ARTIFACTS if (project_dir / name).is_file()],
        "validation": {},
    }


def run_formal_planning(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    snapshot = _snapshot_artifacts(project_dir)
    previous_visual_plan = (
        _read_json(project_dir / "slide_visual_plan.json")
        if (project_dir / "slide_visual_plan.json").is_file()
        else {}
    )
    stage = "style_route"
    try:
        generate_style_route = _skill_function("route_style_profile", "generate_style_route")
        generate_style_route(project_dir, overwrite=True)

        stage = "template_selection"
        _select_reference_pack(project_dir)

        stage = "art_direction"
        generate_art_direction = _skill_function("generate_art_direction", "generate_art_direction")
        generate_art_direction(project_dir, overwrite=True)
        _merge_blueprint_bridge_fields(project_dir, previous_visual_plan)

        validation = validate_formal_planning_artifacts(project_dir)
    except FormalPlanningStageError as exc:
        _restore_artifacts(project_dir, snapshot)
        return _failure_result(project_dir, exc.stage, exc)
    except Exception as exc:
        _restore_artifacts(project_dir, snapshot)
        return _failure_result(project_dir, stage, exc)

    return {
        "formal_planning_status": "ready",
        "fallback_used": False,
        "failed_stage": "",
        "failure_message": "",
        "artifacts": list(FORMAL_ARTIFACTS),
        "validation": validation,
    }


def apply_formal_planning_status(status: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "formal_planning_status",
        "fallback_used",
        "failed_stage",
        "failure_message",
    ):
        status[key] = result.get(key)
    status["formal_planning"] = {
        "status": result.get("formal_planning_status"),
        "fallback_used": bool(result.get("fallback_used")),
        "failed_stage": str(result.get("failed_stage") or ""),
        "failure_message": str(result.get("failure_message") or ""),
        "artifacts": list(result.get("artifacts") or []),
    }
    return status


def ensure_formal_planning(project_dir: Path, status: dict[str, Any]) -> dict[str, Any]:
    planning_status = str(status.get("formal_planning_status") or "")
    if planning_status == "ready" and all((project_dir / name).is_file() for name in FORMAL_ARTIFACTS):
        return status
    if planning_status == "fallback" and all(
        (project_dir / name).is_file() for name in LEGACY_FALLBACK_ARTIFACTS
    ):
        return status
    return apply_formal_planning_status(status, run_formal_planning(project_dir))
