#!/usr/bin/env python3
"""Generate page-level design briefs before Executor SVG authoring."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from generate_slide_plan import build_semantic_plan_row
from visual_grammar_catalog import select_visual_grammars


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(v) for v in value)
    return "" if value is None else str(value)


def _shorten(text: str, limit: int = 42) -> str:
    clean = re.sub(r"\s+", " ", str(text)).strip()
    if len(clean) <= limit:
        return clean
    for sep in ("：", "，", "；", "。", ":", ";", ","):
        if sep in clean[:limit]:
            part = clean.split(sep, 1)[0].strip()
            if 6 <= len(part) <= limit:
                return part
    return clean[:limit].rstrip() + "..."


def _extract_labels(content: Any, title: str) -> list[str]:
    labels: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key in ("title", "headline", "phase", "label", "name"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    labels.append(_shorten(value, 12))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, str):
            for chunk in re.split(r"[/、,，；;|]", node):
                clean = chunk.strip()
                if 2 <= len(clean) <= 8:
                    labels.append(clean)

    visit(content)
    if not labels:
        labels.extend([part.strip() for part in re.split(r"[：:，,]", title) if 2 <= len(part.strip()) <= 12])
    deduped: list[str] = []
    for label in labels:
        if label and label not in deduped:
            deduped.append(label)
    return deduped[:6]


def _compressed_blocks(content: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(content, dict):
        for key, value in content.items():
            if key in {"source_refs", "asset_refs", "claims"}:
                continue
            if isinstance(value, list):
                items = [_shorten(_flatten_text(item), 28) for item in value[:5]]
                blocks.append({"block": str(key), "items": [item for item in items if item]})
            elif isinstance(value, dict):
                title = str(value.get("title") or key)
                body = _shorten(_flatten_text(value), 60)
                blocks.append({"block": _shorten(title, 18), "summary": body})
            elif isinstance(value, str) and value.strip():
                blocks.append({"block": str(key), "summary": _shorten(value, 60)})
    return blocks[:5]


def _reference_case_ids(reference_pack: dict[str, Any], grammar: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    raw = reference_pack.get("reference_case_ids")
    if isinstance(raw, list):
        ids.extend(str(item) for item in raw if str(item).strip())
    grammar_ids = grammar.get("reference_case_ids")
    if isinstance(grammar_ids, list):
        ids.extend(str(item) for item in grammar_ids if str(item).strip())
    result: list[str] = []
    for item in ids:
        if item not in result:
            result.append(item)
    return result[:4]


def _evidence_artifact_plan(grammar_id: str, text: str) -> dict[str, Any]:
    lowered = text.lower()
    if grammar_id == "artifact-centered-proof":
        artifact_type = "prototype_or_demo_screen"
        if "console" in lowered or "build" in lowered:
            artifact_type = "demo_console"
        elif (
            "prototype" not in lowered
            and "wireframe" not in lowered
            and ("dashboard" in lowered or "interface" in lowered or "screen" in lowered)
        ):
            artifact_type = "interface_screen"
        return {
            "required": True,
            "artifact_type": artifact_type,
            "dominant_role": "central proof object that makes the claim inspectable",
            "minimum_visible_parts": ["window frame", "content area", "state/value signal"],
        }
    if grammar_id == "capability-equation-engine":
        return {
            "required": True,
            "artifact_type": "capability_engine_diagram",
            "dominant_role": "equation or engine object that turns components into reusable capability",
            "minimum_visible_parts": ["equation strip", "engine hub", "component modules"],
        }
    return {
        "required": False,
        "artifact_type": "none",
        "dominant_role": "",
        "minimum_visible_parts": [],
    }


def _section_rhythm_role(grammar_id: str, layout_tag: str, text: str) -> str:
    lowered = text.lower()
    if grammar_id == "artifact-centered-proof":
        if "demo" in lowered and ("可运行" in text or "runnable" in lowered or "console" in lowered):
            return "demo_proof"
        return "case_proof"
    if grammar_id == "maturity-ladder":
        return "maturity_ladder"
    if grammar_id == "capability-equation-engine":
        return "engine_model"
    if grammar_id == "composite-flow-responsibility" or grammar_id in {"workflow-chain", "input-process-output"}:
        return "chain_explain"
    if grammar_id in {"problem-labels", "myth-vs-reality"}:
        return "problem_scan"
    if grammar_id in {"responsibility-loop", "human-ai-division"}:
        return "closure_summary"
    if layout_tag == "Grid-Four-Cards":
        return "case_proof"
    return "chain_explain"


def build_design_story_plan(
    blueprint: dict[str, Any],
    *,
    art_direction: str = "",
    reference_pack: dict[str, Any] | None = None,
    grammar_catalog_path: Path | None = None,
) -> dict[str, Any]:
    slides = blueprint.get("slides")
    if not isinstance(slides, list):
        raise ValueError("blueprint.json must contain slides array.")
    reference_pack = reference_pack or {}
    plan_slides: list[dict[str, Any]] = []
    previous_grammar = ""
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        sid = slide.get("id")
        if not isinstance(sid, int):
            raise ValueError("Each slide must have integer id.")
        title = str(slide.get("title") or "")
        layout_tag = str(slide.get("layout_tag") or "")
        narrative_intent = str(slide.get("narrative_intent") or "")
        content = slide.get("content", {})
        semantic_plan = build_semantic_plan_row(slide)
        core_claim = (
            str(semantic_plan.get("conclusion") or "")
            if semantic_plan.get("conclusion_source") == "claims"
            else ""
        )
        grammar_selection = select_visual_grammars(
            layout_tag=layout_tag,
            narrative_intent=narrative_intent,
            title=title,
            content=content,
            catalog_path=grammar_catalog_path,
        )
        grammar = grammar_selection["primary"]
        secondary_grammars = [item for item in grammar_selection.get("secondary", []) if isinstance(item, dict)]
        secondary_ids = [
            str(item.get("grammar_id"))
            for item in secondary_grammars
            if str(item.get("grammar_id") or "").strip()
        ]
        labels = _extract_labels(content, title)
        headline = _shorten(title, 34)
        memory_sentence = _shorten(core_claim or narrative_intent or title, 54)
        if not memory_sentence:
            memory_sentence = headline
        flattened = _flatten_text({"title": title, "intent": narrative_intent, "content": content})
        primary_id = str(grammar.get("grammar_id"))
        accent_terms = labels[:3] or [headline]
        plan_slides.append(
            {
                "slide_id": sid,
                "layout_tag": layout_tag,
                "memory_sentence": memory_sentence,
                "content_selection": {
                    "keep": "core argument, named labels, final takeaway",
                    "compress": "supporting examples and long explanations",
                    "drop_or_weaken": "duplicate phrasing and equal-weight secondary bullets",
                },
                "visual_grammar_id": primary_id,
                "primary_grammar_id": primary_id,
                "secondary_grammar_ids": secondary_ids,
                "visual_grammar_name": str(grammar.get("name")),
                "design_move": str(grammar.get("skeleton")),
                "composite_design_move": " + ".join([primary_id, *secondary_ids]) or primary_id,
                "dominant_object": str(grammar.get("dominant_object")),
                "accent_terms": accent_terms,
                "secondary_content_policy": str(grammar.get("secondary_content_policy")),
                "evidence_artifact_plan": _evidence_artifact_plan(primary_id, flattened),
                "section_rhythm_role": _section_rhythm_role(primary_id, layout_tag, flattened),
                "avoid": list(grammar.get("failure_modes") or []),
                "rewrite_policy": (
                    "semantic_compression: preserve meaning, rename into short "
                    "labels, and avoid verbatim prompt transfer"
                ),
                "headline_rewrite": headline,
                "label_set": labels,
                "takeaway_line": _shorten(
                    core_claim
                    or str(semantic_plan.get("conclusion") or "")
                    or _flatten_text(content)
                    or title,
                    64,
                ),
                "supporting_claims": list(semantic_plan.get("supporting_claims") or []),
                "source_refs": list(semantic_plan.get("source_refs") or []),
                "visual_intent": str(semantic_plan.get("visual_intent") or ""),
                "acceptance_criteria": list(semantic_plan.get("acceptance_criteria") or []),
                "compressed_blocks": _compressed_blocks(content),
                "reference_case_ids": _reference_case_ids(reference_pack, grammar),
                "variation_note": (
                    "Change grammar or visual protagonist if the previous slide used the same design move."
                    if previous_grammar == str(grammar.get("grammar_id"))
                    else "Keep page rhythm distinct from adjacent slides."
                ),
            }
        )
        previous_grammar = str(grammar.get("grammar_id"))
    return {
        "version": 1,
        "generated_by": "generate_design_story_plan",
        "purpose": "Design Director handoff: turn structured content into page-level story and visual design brief.",
        "art_direction_digest": _shorten(art_direction, 120) if art_direction else "",
        "slides": plan_slides,
    }


def generate_design_story_plan(project_dir: Path, *, overwrite: bool = True) -> Path:
    project_dir = project_dir.resolve()
    out = project_dir / "design_story_plan.json"
    if out.exists() and not overwrite:
        raise FileExistsError(out)
    blueprint = _read_json(project_dir / "blueprint.json")
    reference_pack = _read_json(project_dir / "reference_pack.json")
    art_direction_path = project_dir / "art_direction.md"
    art_direction = art_direction_path.read_text(encoding="utf-8-sig") if art_direction_path.exists() else ""
    payload = build_design_story_plan(blueprint, art_direction=art_direction, reference_pack=reference_pack)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate design_story_plan.json for a PPT project.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args(argv)
    print(generate_design_story_plan(args.project_dir, overwrite=not args.no_overwrite))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
