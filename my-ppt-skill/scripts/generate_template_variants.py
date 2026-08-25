#!/usr/bin/env python3
"""Generate three reusable visual variants for each template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_LAYOUTS_INDEX = SKILL_DIR / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
DEFAULT_OUTPUT = SKILL_DIR / "templates" / "template_variants.json"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _profile_hint(template_id: str) -> str:
    tid = template_id.lower()
    if any(token in tid for token in ("government", "政", "国")):
        return "policy_institutional"
    if any(token in tid for token in ("bank", "finance", "招行", "cmb")):
        return "luxury_finance"
    if any(token in tid for token in ("anthropic", "google", "ai", "ops", "tech")):
        return "engineering_blueprint"
    if any(token in tid for token in ("exhibit", "mckinsey", "consulting")):
        return "executive_exhibit"
    return "editorial_report"


def _variant_pack(template_id: str) -> list[dict[str, Any]]:
    style_hint = _profile_hint(template_id)
    return [
        {
            "variant_name": "executive",
            "style_profile": "executive_exhibit" if style_hint != "policy_institutional" else "policy_institutional",
            "composition_grammar": "conclusion-first hero + takeaway bar + 2 evidence zones",
            "rhythm_grammar": "set-tone -> evidence-peak -> resolve",
            "density_profile": "balanced",
        },
        {
            "variant_name": "data_heavy",
            "style_profile": "engineering_blueprint" if style_hint != "luxury_finance" else "luxury_finance",
            "composition_grammar": "primary metric stage + structured evidence grid + concise annotations",
            "rhythm_grammar": "context -> analysis -> implication",
            "density_profile": "dense",
        },
        {
            "variant_name": "storytelling",
            "style_profile": "ai_product_keynote"
            if style_hint not in {"policy_institutional", "luxury_finance"}
            else style_hint,
            "composition_grammar": "hero promise + reveal steps + decisive summary",
            "rhythm_grammar": "problem -> reveal -> proof -> momentum close",
            "density_profile": "airy",
        },
    ]


def generate_template_variants(layouts_index_path: Path, output_path: Path) -> dict[str, Any]:
    index = _read_json(layouts_index_path)
    layouts = index.get("layouts")
    if not isinstance(layouts, dict) or not layouts:
        raise ValueError(f"Invalid layouts index (missing layouts object): {layouts_index_path}")

    template_variants: dict[str, list[dict[str, Any]]] = {}
    for template_id in sorted(layouts.keys()):
        template_variants[template_id] = _variant_pack(template_id)

    payload = {
        "version": 1,
        "source_index": str(layouts_index_path),
        "template_count": len(template_variants),
        "template_variants": template_variants,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate template variants (executive/data_heavy/storytelling).")
    parser.add_argument(
        "--layouts-index",
        type=Path,
        default=DEFAULT_LAYOUTS_INDEX,
        help="Path to layouts_index.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output template_variants.json path.",
    )
    args = parser.parse_args(argv)

    try:
        payload = generate_template_variants(args.layouts_index.resolve(), args.output.resolve())
    except Exception as exc:
        print(f"error: {exc}")
        return 1
    print(args.output.resolve())
    print(f"template_count={payload.get('template_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
