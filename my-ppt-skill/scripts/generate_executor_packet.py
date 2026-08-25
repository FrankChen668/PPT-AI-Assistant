#!/usr/bin/env python3
"""Generate compact per-slide Executor handoff packets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from profile_policy import resolve_profile_policy


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _project_cli_path(project_dir: Path) -> str:
    parts = project_dir.parts
    if "projects" in parts:
        idx = len(parts) - 1 - list(reversed(parts)).index("projects")
        if idx + 1 < len(parts):
            return "/".join(parts[idx : idx + 2])
    return str(project_dir)


def _parse_design_spec(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    summary: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        clean_key = key.strip()
        if clean_key in {
            "canvas",
            "audience",
            "decision_goal",
            "style_goal",
            "style",
            "style_profile",
            "language",
            "template_key",
            "font_title",
            "font_body",
            "font_ladder",
            "primary_color",
            "accent_color",
            "secondary_accent",
            "background_color",
            "card_bg",
            "text_color",
            "muted_color",
            "line_color",
            "soft_color",
        }:
            summary[clean_key] = value.strip().strip('"')
    return summary


def _find_slide_by_id(items: list[Any], *, id_key: str, slide_id: int) -> dict[str, Any]:
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get(id_key) or 0)
        except (TypeError, ValueError):
            continue
        if item_id == slide_id:
            return item
    return {}


def find_slide_id_by_source_page(project_dir: Path, source_page: str) -> int | None:
    """Return the blueprint slide id for a source page such as P47."""

    blueprint = _load_json(project_dir / "blueprint.json")
    page = str(source_page or "").upper().strip()
    for slide in blueprint.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        if str(slide.get("source_page", "")).upper().strip() != page:
            continue
        raw_id = slide.get("id")
        if isinstance(raw_id, int):
            return raw_id
        if isinstance(raw_id, str) and raw_id.strip().isdigit():
            return int(raw_id.strip())
        return None
    return None


def _blueprint_summary(slide: dict[str, Any]) -> dict[str, Any]:
    def _compact_text(value: str, *, limit: int) -> str:
        clean = " ".join(str(value).split())
        if len(clean) <= limit:
            return clean
        return clean[: max(0, limit - 3)] + "..."

    def _compact_node(node: Any, *, depth: int = 0) -> Any:
        if depth >= 4:
            if isinstance(node, str):
                return _compact_text(node, limit=80)
            return node
        if isinstance(node, str):
            return _compact_text(node, limit=140)
        if isinstance(node, (int, float, bool)) or node is None:
            return node
        if isinstance(node, list):
            result: list[Any] = []
            for item in node[:4]:
                result.append(_compact_node(item, depth=depth + 1))
            if len(node) > 4:
                result.append(f"...(+{len(node) - 4} more)")
            return result
        if isinstance(node, dict):
            keep_order = [
                "title",
                "headline",
                "subtitle",
                "statement",
                "body",
                "keywords",
                "steps",
                "items",
                "pain_points",
                "impacts",
                "takeaway",
            ]
            dict_result: dict[str, Any] = {}
            for key in keep_order:
                if key in node:
                    dict_result[key] = _compact_node(node.get(key), depth=depth + 1)
            for key, value in node.items():
                if key in dict_result:
                    continue
                if key in {"source_refs", "claims", "asset_refs"}:
                    continue
                dict_result[str(key)] = _compact_node(value, depth=depth + 1)
            return dict_result
        return str(node)

    content = slide.get("content")
    content_summary: dict[str, Any] = {}
    if isinstance(content, dict):
        content_summary = _compact_node(content, depth=0)
    return {
        "title": str(slide.get("title") or ""),
        "layout_tag": str(slide.get("layout_tag") or ""),
        "narrative_intent": str(slide.get("narrative_intent") or ""),
        "page_type": str(slide.get("page_type") or ""),
        "content_density": str(slide.get("content_density") or ""),
        "content": content_summary,
    }


def _forbidden_from_plan(plan_slide: dict[str, Any]) -> list[str]:
    forbidden: list[str] = []
    for key in ("avoid", "forbidden", "forbidden_shortcuts"):
        value = plan_slide.get(key)
        if isinstance(value, list):
            forbidden.extend(str(item) for item in value if str(item).strip())
    contract = plan_slide.get("visual_contract")
    if isinstance(contract, dict):
        for key in ("anti_patterns", "must_avoid"):
            value = contract.get(key)
            if isinstance(value, list):
                forbidden.extend(str(item) for item in value if str(item).strip())
    return sorted(set(forbidden))


def _narrative_composition_from_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        return {}
    keep = (
        "relationship_model",
        "primary_message",
        "content_roles",
        "composition_candidates",
        "selected_composition",
        "selected_composition_reason",
        "hierarchy_rule",
        "executor_freedom",
    )
    return {key: contract.get(key) for key in keep if key in contract}


def _design_story_from_sources(plan_slide: dict[str, Any], story_slide: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for source in (story_slide, plan_slide):
        for key in (
            "memory_sentence",
            "headline_rewrite",
            "label_set",
            "takeaway_line",
            "compressed_blocks",
            "content_selection",
            "design_move",
            "visual_grammar_id",
            "primary_grammar_id",
            "secondary_grammar_ids",
            "composite_design_move",
            "evidence_artifact_plan",
            "section_rhythm_role",
            "rewrite_policy",
            "dominant_object",
            "accent_terms",
            "secondary_content_policy",
            "reference_case_ids",
            "avoid",
            "variation_note",
        ):
            if key in source and key not in result:
                result[key] = source[key]
        nested = source.get("design_story")
        if isinstance(nested, dict):
            for key, value in nested.items():
                result.setdefault(str(key), value)
    return result


def _layout_plan_from_slide_plan(slide_plan_row: dict[str, Any]) -> dict[str, Any]:
    blocks = slide_plan_row.get("blocks")
    return {
        "blocks": blocks if isinstance(blocks, list) else [],
        "layout_objective": str(slide_plan_row.get("layout_objective") or ""),
        "dominance_map": (
            slide_plan_row.get("dominance_map")
            if isinstance(slide_plan_row.get("dominance_map"), dict)
            else {}
        ),
    }


def _render_markdown(packet: dict[str, Any]) -> str:
    forbidden = packet.get("forbidden")
    forbidden_lines = "\n".join(f"- {item}" for item in forbidden) if isinstance(forbidden, list) else "- none"
    return (
        f"# Executor Packet: Slide {packet['slide_id']:02d}\n\n"
        f"- project: `{packet['project']}`\n"
        f"- target_svg: `{packet['target_svg']}`\n"
        f"- verify: `{packet['verify']}`\n\n"
        f"## Blueprint\n\n"
        f"- title: {packet['blueprint_summary'].get('title')}\n"
        f"- narrative_intent: {packet['blueprint_summary'].get('narrative_intent')}\n\n"
        f"## Budget (governance)\n\n"
        f"```json\n{json.dumps(packet.get('budget_policy', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Execution Policy\n\n"
        f"```json\n{json.dumps(packet.get('execution_policy', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Visual Contract\n\n"
        f"```json\n{json.dumps(packet.get('visual_contract', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Narrative Composition\n\n"
        f"```json\n{json.dumps(packet.get('narrative_composition', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Layout Plan\n\n"
        f"```json\n{json.dumps(packet.get('layout_plan', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Design Story\n\n"
        f"```json\n{json.dumps(packet.get('design_story', {}), ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Forbidden\n\n{forbidden_lines}\n"
    )


def build_executor_packet(project_dir: Path, *, slide_id: int) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    blueprint = _load_json(project_dir / "blueprint.json")
    plan = _load_json(project_dir / "slide_visual_plan.json")
    slide_plan = _load_json(project_dir / "slide_plan.json")
    story_plan = _load_json(project_dir / "design_story_plan.json")
    style_route = _load_json(project_dir / "style_route.json")
    blueprint_slide = _find_slide_by_id(list(blueprint.get("slides") or []), id_key="id", slide_id=slide_id)
    plan_slide = _find_slide_by_id(list(plan.get("slides") or []), id_key="slide_id", slide_id=slide_id)
    slide_plan_row = _find_slide_by_id(list(slide_plan.get("slides") or []), id_key="slide_id", slide_id=slide_id)
    story_slide = _find_slide_by_id(list(story_plan.get("slides") or []), id_key="slide_id", slide_id=slide_id)

    target_svg = f"svg_output/slide_{slide_id:02d}.svg"
    project_cli = _project_cli_path(project_dir)
    design_spec_summary = _parse_design_spec(project_dir / "design_spec.md")
    style_profile = str(style_route.get("style_profile") or design_spec_summary.get("style_profile") or "").lower()
    governance_profile = (
        "proposal_consulting"
        if any(token in style_profile for token in ("proposal", "consult", "tender", "bid"))
        else "presentation"
    )
    policy = resolve_profile_policy(governance_profile)
    raw_visual_contract = plan_slide.get("visual_contract")
    visual_contract: dict[str, Any]
    if isinstance(raw_visual_contract, dict):
        visual_contract = {str(key): value for key, value in raw_visual_contract.items()}
    else:
        visual_contract = {}
    packet = {
        "project": project_dir.name,
        "project_path": project_cli,
        "slide_id": slide_id,
        "target_svg": target_svg,
        "design_spec_summary": design_spec_summary,
        "blueprint_summary": _blueprint_summary(blueprint_slide),
        "style_profile": str(style_route.get("style_profile") or design_spec_summary.get("style_profile") or ""),
        "budget_policy": {
            "profile": policy.key,
            "max_chars_per_slide": policy.max_chars_per_slide,
            "max_text_nodes_per_slide": policy.max_text_nodes_per_slide,
            "min_heading_font_px": policy.min_heading_font_px,
            "notes": [
                "Keep <text> elements low; merging labels reduces export fragmentation.",
                "Prefer 3–5 modules; each module <=3 lines to stay bid-grade readable.",
            ],
        },
        "scene_route": plan_slide.get("scene_route") if isinstance(plan_slide.get("scene_route"), dict) else {},
        "execution_policy": plan_slide.get("execution_policy")
        if isinstance(plan_slide.get("execution_policy"), dict)
        else {},
        "visual_contract": visual_contract,
        "narrative_composition": _narrative_composition_from_contract(visual_contract),
        "layout_plan": _layout_plan_from_slide_plan(slide_plan_row),
        "design_story": _design_story_from_sources(plan_slide, story_slide),
        "template_reference_principles": [
            str(item)
            for item in plan_slide.get("template_reference_principles", [])
            if str(item).strip()
        ][:5]
        if isinstance(plan_slide.get("template_reference_principles"), list)
        else [],
        "forbidden": _forbidden_from_plan(plan_slide),
        "verify": f"python scripts/run_mode.py dev-fast {project_cli} --slide {slide_id}",
    }
    return packet


def generate_executor_packet(project_dir: Path, *, slide_id: int, write_markdown: bool = False) -> Path:
    project_dir = project_dir.resolve()
    packet = build_executor_packet(project_dir, slide_id=slide_id)

    out_dir = project_dir / "executor_packets"
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / f"slide_{slide_id:02d}.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if write_markdown:
        (out_dir / f"slide_{slide_id:02d}.md").write_text(_render_markdown(packet), encoding="utf-8")
    return packet_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a compact per-slide Executor packet.")
    parser.add_argument("project_dir", help="Project path, usually projects/<project_name> from my-ppt-skill/.")
    parser.add_argument("--slide", type=int, required=True, help="Slide id to package.")
    parser.add_argument("--markdown", action="store_true", help="Also write a compact Markdown packet.")
    args = parser.parse_args(argv)

    packet_path = generate_executor_packet(Path(args.project_dir), slide_id=args.slide, write_markdown=args.markdown)
    print(f"wrote executor packet: {packet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
