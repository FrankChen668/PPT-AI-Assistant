#!/usr/bin/env python3
"""Ingest an excellent PPTX into a reusable reference-case folder."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from visual_grammar_catalog import select_visual_grammars

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
}


def _slide_number(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_slide(zip_file: ZipFile, name: str) -> dict[str, Any]:
    root = ET.fromstring(zip_file.read(name))
    texts = [node.text or "" for node in root.findall(".//a:t", NS) if (node.text or "").strip()]
    title = texts[0] if texts else f"slide {_slide_number(name)}"
    joined = " ".join(texts)
    grammar_selection = select_visual_grammars(
        layout_tag="Reference-Case",
        narrative_intent=joined,
        title=title,
        content={"text": texts},
    )
    grammar = grammar_selection["primary"]
    secondary_ids = [
        str(item.get("grammar_id"))
        for item in grammar_selection.get("secondary", [])
        if str(item.get("grammar_id") or "").strip()
    ]
    shape_count = len(root.findall(".//p:sp", NS))
    picture_count = len(root.findall(".//p:pic", NS))
    design_actions = [
        f"Use visual grammar: {grammar['grammar_id']}",
        f"Treat first text as dominant message: {title}",
    ]
    if len(texts) >= 3:
        design_actions.append("Convert supporting lines into labels, chips, or muted evidence blocks.")
    return {
        "slide_id": _slide_number(name),
        "title": title,
        "text": texts,
        "text_count": len(texts),
        "shape_count": shape_count,
        "picture_count": picture_count,
        "visual_grammar_ids": [grammar["grammar_id"], *secondary_ids],
        "primary_grammar_id": grammar["grammar_id"],
        "secondary_grammar_ids": secondary_ids,
        "design_actions": design_actions,
        "reusable_moves": [
            str(grammar.get("skeleton")),
            str(grammar.get("dominant_object")),
            str(grammar.get("accent_strategy")),
        ],
        "failure_modes_to_avoid": list(grammar.get("failure_modes") or []),
    }


def intake_reference_pptx(pptx_path: Path, output_root: Path, *, case_id: str | None = None) -> Path:
    pptx_path = pptx_path.resolve()
    if not pptx_path.exists():
        raise FileNotFoundError(pptx_path)
    case_id = case_id or re.sub(r"[^0-9A-Za-z_-]+", "-", pptx_path.stem).strip("-").lower() or "reference-case"
    case_dir = output_root.resolve() / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    sources_dir = case_dir / "sources"
    sources_dir.mkdir(exist_ok=True)
    copied = sources_dir / pptx_path.name
    if copied.resolve() != pptx_path:
        shutil.copy2(pptx_path, copied)
    with ZipFile(pptx_path) as z:
        slide_names = sorted(
            [name for name in z.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")],
            key=_slide_number,
        )
        media = [name for name in z.namelist() if name.startswith("ppt/media/")]
        slides = [_extract_slide(z, name) for name in slide_names]
    payload = {
        "version": 1,
        "case_id": case_id,
        "source_pptx": str(copied),
        "slide_count": len(slides),
        "media_count": len(media),
        "status": "draft",
        "usage": "Use as design-memory reference for visual grammar, not as pixel-level template.",
        "slides": slides,
    }
    (case_dir / "reference_case.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (case_dir / "README.md").write_text(
        (
            f"# {case_id}\n\nGenerated from `{pptx_path.name}`. "
            "Use design actions and visual grammar ids as Executor guidance.\n"
        ),
        encoding="utf-8",
    )
    return case_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest a PPTX into reference_cases/<case_id>.")
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reference_cases"))
    parser.add_argument("--case-id")
    args = parser.parse_args(argv)
    print(intake_reference_pptx(args.pptx, args.out, case_id=args.case_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
