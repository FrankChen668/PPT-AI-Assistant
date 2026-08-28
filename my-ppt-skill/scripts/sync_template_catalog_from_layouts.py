#!/usr/bin/env python3
"""Sync core template entries in template_catalog from layouts_index authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from check_template_ssot_consistency import ALLOWED_VARIANT_POLICIES

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = ROOT / "ppt-ai-core" / "templates" / "layouts" / "layouts_index.json"
DEFAULT_CATALOG = ROOT / "templates" / "template_catalog.json"


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be object: {path}")
    return payload


def _default_catalog_entry(template_id: str, detail: dict) -> dict:
    keywords = detail.get("keywords")
    use_cases = []
    if isinstance(keywords, list):
        use_cases = [str(k) for k in keywords if isinstance(k, str)][:3]
    if not use_cases:
        use_cases = ["General business presentation"]
    return {
        "template_key": template_id,
        "tier": "Silver",
        "use_cases": use_cases,
        "audiences": ["Business teams"],
        "style_tags": use_cases,
        "density": "medium",
        "visual_strengths": [str(detail.get("summary") or "Balanced reusable structure.")],
        "avoid_when": ["When domain-specific template is explicitly required."],
        "reference_pages": ["01_cover.svg", "02_toc.svg", "02_chapter.svg", "03_content.svg", "04_ending.svg"],
        "notes": "Auto-generated from layouts_index authority.",
        "source_path": f"ppt-ai-core/templates/layouts/{template_id}",
        "composition_patterns": ["hero headline + structured evidence blocks"],
        "avoid_copying": [
            f"Do not replicate {template_id} page geometry one-to-one; adapt to narrative.",
            "Reuse visual grammar, not pixel-level decoration.",
        ],
        "best_for": use_cases,
    }


def sync(index_path: Path, catalog_path: Path, *, write: bool) -> int:
    idx = _load_json(index_path)
    catalog = _load_json(catalog_path)

    layouts = idx.get("layouts")
    templates = catalog.get("templates")
    if not isinstance(layouts, dict):
        raise ValueError("layouts_index.json missing layouts object")
    if not isinstance(templates, list):
        raise ValueError("template_catalog.json missing templates array")

    core_map = {k: v for k, v in layouts.items() if isinstance(k, str) and isinstance(v, dict)}
    catalog_map: dict[str, dict] = {}
    for entry in templates:
        if isinstance(entry, dict):
            key = entry.get("template_key")
            if isinstance(key, str) and key.strip():
                catalog_map[key.strip()] = entry

    core_ids = set(core_map.keys())
    catalog_ids = set(catalog_map.keys())
    missing_core = sorted(core_ids - catalog_ids)
    catalog_only_extras = sorted(catalog_ids - core_ids)
    disallowed_extras = sorted(set(catalog_only_extras) - set(ALLOWED_VARIANT_POLICIES.keys()))
    stale_whitelist_entries = sorted(set(ALLOWED_VARIANT_POLICIES.keys()) - set(catalog_only_extras))

    variant_source_warnings: list[str] = []
    for key in catalog_only_extras:
        if key not in ALLOWED_VARIANT_POLICIES:
            continue
        entry = catalog_map.get(key, {})
        source_path = entry.get("source_path")
        if not isinstance(source_path, str) or not source_path.strip():
            variant_source_warnings.append(f"{key}: missing source_path")
            continue
        if not (ROOT / source_path).exists():
            variant_source_warnings.append(f"{key}: source_path not found -> {source_path}")

    updated = 0
    for key, detail in core_map.items():
        existing = catalog_map.get(key)
        if not isinstance(existing, dict):
            templates.append(_default_catalog_entry(key, detail))
            updated += 1
            continue
        source_path = existing.get("source_path")
        desired_source = f"ppt-ai-core/templates/layouts/{key}"
        if not isinstance(source_path, str) or source_path.strip() != desired_source:
            existing["source_path"] = desired_source
            updated += 1

    if write and updated:
        catalog["templates"] = sorted(
            [item for item in templates if isinstance(item, dict)],
            key=lambda item: str(item.get("template_key", "")),
        )
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"missing core entries: {len(missing_core)}")
    if missing_core:
        print("  - " + ", ".join(missing_core))
    print(f"catalog-only extras: {len(catalog_only_extras)}")
    if catalog_only_extras:
        print("  - " + ", ".join(catalog_only_extras))
    print(f"disallowed extras: {len(disallowed_extras)}")
    if disallowed_extras:
        print("  - " + ", ".join(disallowed_extras))
    print(f"variant source warnings: {len(variant_source_warnings)}")
    if variant_source_warnings:
        for issue in variant_source_warnings:
            print("  -", issue)
    print(f"stale whitelist entries: {len(stale_whitelist_entries)}")
    if stale_whitelist_entries:
        print("  - " + ", ".join(stale_whitelist_entries))
    print(f"catalog updates needed: {updated}")
    if write:
        print(f"write mode: {'updated' if updated else 'no changes'}")
    else:
        print("write mode: dry-run")
    if disallowed_extras:
        return 1
    return 1 if (missing_core or updated) and not write else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync template_catalog core entries from layouts_index.")
    parser.add_argument("--index-path", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--catalog-path", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--write", action="store_true", help="Apply updates to template_catalog.json.")
    args = parser.parse_args(argv)
    return sync(args.index_path, args.catalog_path, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
