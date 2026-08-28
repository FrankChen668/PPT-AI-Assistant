#!/usr/bin/env python3
"""Compare SVG vs native PPTX text wrapping snapshots on real project copy."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from path_bootstrap import ensure_scripts_path  # noqa: E402

SCRIPT_DIR = ensure_scripts_path(Path(__file__))
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent

from render_theme import Theme  # noqa: E402
from svg_canvas import SvgCanvas  # noqa: E402
from svg_to_pptx import convert  # noqa: E402

REAL_SAMPLE_PROJECTS = (
    ROOT / "projects" / "style-lab",
    ROOT / "projects" / "sie-why-onepager",
)
FALLBACK_TEXT_CANDIDATES = (
    "Executive teams need a short decision memo before committing to an AI workflow rollout.",
    "The operating model shifts from tool assistance to accountable task closure across systems.",
    "Template references should guide the first composition pass without replacing judgment.",
    "Visual quality gates must separate engineering readiness from presentation readiness.",
    "A single-slide repair loop keeps iteration fast while protecting the rest of the deck.",
    "Source evidence, design intent, and slide status should stay visible in the workbench.",
    "The default delivery path preserves AI-authored SVG and exports through the stable pipeline.",
    "A compact handoff packet reduces context loss between authoring, repair, QA, and export.",
    "Warnings about hierarchy, balance, or broken text should block consulting-grade bid pages.",
    "Generated project artifacts are useful evidence, but they should not be required test fixtures.",
    "Native text export needs predictable paragraph structure so PowerPoint remains editable.",
    "Repository hygiene checks help future reviews distinguish current evidence from stale reports.",
)
PPTX_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


@dataclass
class WrapSample:
    id: str
    source_project: str
    text: str
    width: float
    font_size: float
    max_lines: int
    min_font_size: float


@dataclass
class WrapSnapshot:
    id: str
    source_project: str
    text_preview: str
    width: float
    font_size: float
    max_lines: int
    min_font_size: float
    fitted_font_size: float
    svg_lines: int
    pptx_lines: int
    match: bool


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _collect_strings(value: Any, results: list[str]) -> None:
    if isinstance(value, str):
        text = " ".join(value.split())
        if len(text) >= 10:
            results.append(text)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_strings(item, results)
        return
    if isinstance(value, list):
        for item in value:
            _collect_strings(item, results)


def _sample_project_dirs() -> list[Path]:
    seen: set[Path] = set()
    project_dirs: list[Path] = []
    for project_dir in (*REAL_SAMPLE_PROJECTS, *sorted((ROOT / "projects").glob("*"))):
        if not project_dir.is_dir():
            continue
        resolved = project_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        project_dirs.append(project_dir)
    return project_dirs


def _build_real_samples(min_samples: int = 10) -> list[WrapSample]:
    collected: list[tuple[str, str]] = []
    for project_dir in _sample_project_dirs():
        blueprint = project_dir / "blueprint.json"
        if not blueprint.exists():
            continue
        payload = _load_json(blueprint)
        strings: list[str] = []
        _collect_strings(payload, strings)
        seen: set[str] = set()
        for text in strings:
            if text in seen:
                continue
            seen.add(text)
            collected.append((project_dir.name, text))

    fallback_idx = 0
    while len(collected) < min_samples and fallback_idx < len(FALLBACK_TEXT_CANDIDATES):
        collected.append(("bundled-fallback", FALLBACK_TEXT_CANDIDATES[fallback_idx]))
        fallback_idx += 1

    if len(collected) < min_samples:
        raise RuntimeError(
            f"Not enough real text candidates for wrap snapshots: need {min_samples}, got {len(collected)}."
        )

    width_cycle = [190.0, 220.0, 260.0, 300.0, 340.0]
    max_lines_cycle = [1, 2, 2, 3, 3]
    font_cycle = [14.0, 15.0, 16.0, 17.0, 18.0]

    samples: list[WrapSample] = []
    for idx, (project_name, text) in enumerate(collected[: max(min_samples, 10)], start=1):
        width = width_cycle[(idx - 1) % len(width_cycle)]
        font_size = font_cycle[(idx - 1) % len(font_cycle)]
        max_lines = max_lines_cycle[(idx - 1) % len(max_lines_cycle)]
        min_font_size = max(10.0, font_size - 4.0)
        samples.append(
            WrapSample(
                id=f"S{idx:02d}",
                source_project=project_name,
                text=text,
                width=width,
                font_size=font_size,
                max_lines=max_lines,
                min_font_size=min_font_size,
            )
        )
    return samples


def _render_svg_for_sample(sample: WrapSample, target: Path) -> tuple[int, float]:
    canvas = SvgCanvas(f"wrap-{sample.id}", Theme())
    canvas.wrapped_text(
        100,
        170,
        sample.text,
        width=sample.width,
        size=sample.font_size,
        max_lines=sample.max_lines,
        min_size=sample.min_font_size,
    )
    target.write_text(canvas.output(), encoding="utf-8")

    root = ET.fromstring(target.read_text(encoding="utf-8"))
    ns = {"svg": "http://www.w3.org/2000/svg"}
    text_nodes = root.findall(".//svg:text", ns)
    if not text_nodes:
        raise RuntimeError(f"No <text> nodes found in generated SVG for {sample.id}.")
    node = text_nodes[-1]
    tspans = node.findall("svg:tspan", ns)
    fitted_size = float(node.attrib.get("font-size", sample.font_size))
    return len(tspans), fitted_size


def _pptx_paragraph_count(pptx_path: Path) -> int:
    with zipfile.ZipFile(pptx_path, "r") as zf:
        slide_xml = zf.read("ppt/slides/slide1.xml")
    root = ET.fromstring(slide_xml)
    ns = {
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
        "a": PPTX_A_NS,
    }
    paragraphs = root.findall(".//p:txBody/a:p", ns)
    if paragraphs:
        return sum(1 for para in paragraphs if para.findall(".//a:t", ns))

    # Fallback: count text-bearing paragraphs globally if the structure differs.
    all_paragraphs = root.findall(".//a:p", ns)
    return sum(1 for para in all_paragraphs if para.findall(".//a:t", ns))


def _compare_one(sample: WrapSample, work_dir: Path) -> WrapSnapshot:
    project_dir = work_dir / sample.id
    svg_dir = project_dir / "svg_final"
    exports_dir = project_dir / "exports"
    svg_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)

    svg_path = svg_dir / "slide_01.svg"
    svg_lines, fitted_size = _render_svg_for_sample(sample, svg_path)

    pptx_path = exports_dir / "output-native.pptx"
    convert(project_dir, "svg_final", pptx_path, mode="native")
    pptx_lines = _pptx_paragraph_count(pptx_path)

    return WrapSnapshot(
        id=sample.id,
        source_project=sample.source_project,
        text_preview=(sample.text[:72] + "...") if len(sample.text) > 75 else sample.text,
        width=sample.width,
        font_size=sample.font_size,
        max_lines=sample.max_lines,
        min_font_size=sample.min_font_size,
        fitted_font_size=fitted_size,
        svg_lines=svg_lines,
        pptx_lines=pptx_lines,
        match=svg_lines == pptx_lines,
    )


def write_reports(snapshots: list[WrapSnapshot], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "text-wrap-snapshot-report.json"
    md_path = out_dir / "text-wrap-snapshot-report.md"

    payload = {
        "samples": len(snapshots),
        "matches": sum(1 for item in snapshots if item.match),
        "mismatches": sum(1 for item in snapshots if not item.match),
        "snapshots": [asdict(item) for item in snapshots],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Text Wrap Snapshot Compare",
        "",
        f"- samples: `{payload['samples']}`",
        f"- matches: `{payload['matches']}`",
        f"- mismatches: `{payload['mismatches']}`",
        "",
        "| id | source | width | max_lines | fitted_size | svg_lines | pptx_lines | match | preview |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in snapshots:
        lines.append(
            f"| {item.id} | {item.source_project} | {item.width:.0f} | {item.max_lines} | "
            f"{item.fitted_font_size:.1f} | {item.svg_lines} | {item.pptx_lines} | "
            f"{'yes' if item.match else 'no'} | {item.text_preview.replace('|', '/')} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def run(out_dir: Path, min_samples: int = 10) -> int:
    samples = _build_real_samples(min_samples=min_samples)
    with tempfile.TemporaryDirectory(prefix="wrap_snapshots_") as tmp:
        work_dir = Path(tmp)
        snapshots = [_compare_one(sample, work_dir) for sample in samples]

    json_path, md_path = write_reports(snapshots, out_dir)
    mismatches = [item for item in snapshots if not item.match]
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if len(snapshots) < min_samples:
        print(f"error: snapshot sample count too low ({len(snapshots)} < {min_samples})", file=sys.stderr)
        return 1
    if mismatches:
        print(
            "error: wrap mismatches detected: "
            + ", ".join(f"{item.id}(svg={item.svg_lines},pptx={item.pptx_lines})" for item in mismatches),
            file=sys.stderr,
        )
        return 1
    print(f"Wrap snapshots matched for {len(snapshots)} real samples.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare SVG and native PPTX text wrapping snapshots.")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "qa",
        help="Output directory for snapshot compare reports.",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=10,
        help="Minimum number of real samples required.",
    )
    args = parser.parse_args(argv)
    return run(args.out_dir, min_samples=args.min_samples)


if __name__ == "__main__":
    raise SystemExit(main())
