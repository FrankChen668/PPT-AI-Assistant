#!/usr/bin/env python3
"""Run exporter regression corpus across native/raster outputs."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from svg_to_pptx import convert

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
CORPUS_DIR = ROOT / "tests" / "fixtures" / "exporter_corpus"


@dataclass
class CorpusResult:
    case: str
    native_ok: bool
    raster_ok: bool
    native_output: str
    raster_output: str
    error: str = ""


def _write_project_stub(project_dir: Path, svg_content: str) -> None:
    (project_dir / "design_spec.md").write_text("# Design Spec\n", encoding="utf-8")
    (project_dir / "blueprint.json").write_text(
        json.dumps(
            {"slides": [{"id": 1, "title": "Corpus", "layout_tag": "Cover-Center", "content": {"headline": "h"}}]}
        ),
        encoding="utf-8",
    )
    svg_dir = project_dir / "svg_final"
    svg_dir.mkdir(parents=True, exist_ok=True)
    (svg_dir / "slide_01.svg").write_text(svg_content, encoding="utf-8")
    (project_dir / "exports").mkdir(parents=True, exist_ok=True)


def run() -> tuple[list[CorpusResult], Path, Path]:
    results: list[CorpusResult] = []
    for svg_file in sorted(CORPUS_DIR.glob("*.svg")):
        with tempfile.TemporaryDirectory(prefix=f"exporter_corpus_{svg_file.stem}_") as tmp:
            project_dir = Path(tmp)
            _write_project_stub(project_dir, svg_file.read_text(encoding="utf-8"))
            native_out = project_dir / "exports" / "output-native.pptx"
            raster_out = project_dir / "exports" / "output-raster.pptx"
            try:
                native_actual = convert(project_dir, "svg_final", native_out, mode="native")
                raster_actual = convert(project_dir, "svg_final", raster_out, mode="raster")
                results.append(
                    CorpusResult(
                        case=svg_file.name,
                        native_ok=native_actual.exists(),
                        raster_ok=raster_actual.exists(),
                        native_output=str(native_actual),
                        raster_output=str(raster_actual),
                    )
                )
            except Exception as exc:  # pragma: no cover - runtime failure path
                results.append(
                    CorpusResult(
                        case=svg_file.name,
                        native_ok=False,
                        raster_ok=False,
                        native_output="",
                        raster_output="",
                        error=str(exc),
                    )
                )

    reports_dir = REPO_ROOT / "docs" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    json_path = reports_dir / f"exporter-corpus-report-{stamp}.json"
    md_path = reports_dir / f"exporter-corpus-report-{stamp}.md"

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpus_dir": str(CORPUS_DIR),
        "results": [asdict(item) for item in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Exporter Corpus Report",
        "",
        f"- corpus_dir: `{CORPUS_DIR}`",
        f"- total_cases: `{len(results)}`",
        "",
        "| case | native_ok | raster_ok | error |",
        "|---|---:|---:|---|",
    ]
    for item in results:
        lines.append(f"| `{item.case}` | `{item.native_ok}` | `{item.raster_ok}` | `{item.error or '-'}` |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return results, md_path, json_path


def main() -> int:
    results, md_path, json_path = run()
    failed = [item for item in results if not item.native_ok or not item.raster_ok]
    print(md_path)
    print(json_path)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
