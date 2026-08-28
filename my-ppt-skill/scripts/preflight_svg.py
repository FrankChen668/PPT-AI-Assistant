#!/usr/bin/env python3
"""Fast preflight checks for SVG authoring stage.

Purpose:
- fail fast on encoding / XML integrity issues
- catch banned SVG features (foreignObject)
- flag likely mojibake before costly build/export steps
- do not judge copy style or language mix; generated SVG text may legitimately contain English
"""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CJK_CHAR_RE = re.compile(r"[\u3400-\u9FFF]")
SUSPICIOUS_QUESTION_BULLET_RE = re.compile(r"^\s*\?\s*[\u3400-\u9FFF]")
SHAPE_TAGS = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path"}
AI_DIVERSITY_MIN_SLIDES = 6
AI_DIVERSITY_ADJACENT_SIM_THRESHOLD = 0.92
AI_DIVERSITY_ADJACENT_DUP_RATIO = 0.55


@dataclass
class PreflightFinding:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class PreflightReport:
    project: str
    ok: bool
    errors: int
    warnings: int
    findings: list[PreflightFinding]
    scanned_files: int
    report_md: Path
    report_json: Path


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[1] if "}" in tag else tag


def _emit(findings: list[PreflightFinding], severity: str, code: str, path: Path, message: str) -> None:
    findings.append(PreflightFinding(severity=severity, code=code, path=str(path), message=message))


def _is_likely_mojibake(text: str) -> bool:
    if not text:
        return False

    # Strong indicators that are almost never legitimate copy.
    if "\ufffd" in text or "�" in text:
        return True
    if "锟斤拷" in text:
        return True

    # Common UTF-8/GBK mojibake fragments seen in Chinese business copy.
    weak_tokens = (
        "闂",
        "閿",
        "閳",
        "锟",
        "鈥",
        "鐨",
        "鏄",
        "璇",
        "浠",
        "杩",
        "濡",
        "鏈",
    )
    token_hits = sum(text.count(token) for token in weak_tokens)
    unique_hits = sum(1 for token in weak_tokens if token in text)

    # Latin punctuation mojibake (e.g. Ã©, â€”)
    latin_hits = len(re.findall(r"[ÃÂâ][\x80-\xBF]", text))

    total_hits = token_hits + latin_hits
    if total_hits == 0:
        return False

    # Require enough evidence to avoid false positives on valid rare characters.
    return (
        total_hits >= 5
        and unique_hits >= 2
        and (total_hits / max(1, len(text))) >= 0.008
    )


def _collect_text_nodes(root: ET.Element) -> str:
    chunks: list[str] = []
    for elem in root.iter():
        if elem.text:
            chunks.append(elem.text)
        if elem.tail:
            chunks.append(elem.tail)
    return " ".join(chunks)


def _collect_visible_text_nodes(root: ET.Element) -> list[str]:
    texts: list[str] = []
    for elem in root.iter():
        if _local_name(elem.tag) not in {"text", "tspan"}:
            continue
        if not elem.text:
            continue
        value = elem.text.strip()
        if value:
            texts.append(value)
    return texts


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("px", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _canvas_size(root: ET.Element) -> tuple[float, float]:
    view_box = str(root.get("viewBox") or "").strip().replace(",", " ")
    parts = [token for token in view_box.split() if token]
    if len(parts) == 4:
        try:
            width = float(parts[2])
            height = float(parts[3])
            if width > 0 and height > 0:
                return width, height
        except ValueError:
            pass

    width_value: float | None = _parse_number(root.get("width"))
    height_value: float | None = _parse_number(root.get("height"))
    if width_value and width_value > 0 and height_value and height_value > 0:
        return width_value, height_value
    return 1280.0, 720.0


def _grid_bucket(value: float, max_value: float) -> int:
    if max_value <= 0:
        return 0
    ratio = max(0.0, min(0.999999, value / max_value))
    return int(ratio * 3)


def _count_similarity(a: int, b: int) -> float:
    denom = max(a, b, 1)
    return max(0.0, 1.0 - (abs(a - b) / denom))


def _cosine_similarity(a: list[int], b: list[int]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    norm_a = math.sqrt(sum(float(x) ** 2 for x in a))
    norm_b = math.sqrt(sum(float(y) ** 2 for y in b))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def _slide_structure_signature(root: ET.Element) -> dict[str, Any]:
    width, height = _canvas_size(root)
    text_grid = [0] * 9
    shape_grid = [0] * 9
    shape_count = 0
    text_count = 0
    rect_count = 0
    card_count = 0
    headline_count = 0

    for elem in root.iter():
        name = _local_name(elem.tag)
        if name == "text":
            text_value = (elem.text or "").strip()
            if text_value:
                text_count += 1
            x = _parse_number(elem.get("x"))
            y = _parse_number(elem.get("y"))
            if x is not None and y is not None:
                gx = _grid_bucket(x, width)
                gy = _grid_bucket(y, height)
                text_grid[(gy * 3) + gx] += 1
            font_size = _parse_number(elem.get("font-size")) or 16.0
            if y is not None and y <= (height * 0.25) and font_size >= 28:
                headline_count += 1
            continue

        if name not in SHAPE_TAGS:
            continue
        shape_count += 1
        cx: float | None = None
        cy: float | None = None
        if name == "rect":
            rect_count += 1
            x = _parse_number(elem.get("x"))
            y = _parse_number(elem.get("y"))
            w = _parse_number(elem.get("width"))
            h = _parse_number(elem.get("height"))
            rx = _parse_number(elem.get("rx")) or 0.0
            fill = (elem.get("fill") or "").strip().lower()
            if x is not None and y is not None and w is not None and h is not None:
                cx = x + (w / 2.0)
                cy = y + (h / 2.0)
                if rx >= 6 and w >= 160 and h >= 80 and fill not in {"", "none", "transparent"}:
                    card_count += 1
        elif name in {"circle", "ellipse"}:
            cx = _parse_number(elem.get("cx"))
            cy = _parse_number(elem.get("cy"))
        elif name == "line":
            x1 = _parse_number(elem.get("x1"))
            x2 = _parse_number(elem.get("x2"))
            y1 = _parse_number(elem.get("y1"))
            y2 = _parse_number(elem.get("y2"))
            if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

        if cx is not None and cy is not None:
            gx = _grid_bucket(cx, width)
            gy = _grid_bucket(cy, height)
            shape_grid[(gy * 3) + gx] += 1

    return {
        "text_count": text_count,
        "shape_count": shape_count,
        "rect_count": rect_count,
        "card_count": card_count,
        "headline_count": headline_count,
        "text_grid": text_grid,
        "shape_grid": shape_grid,
    }


def _structure_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    return (
        (0.20 * _count_similarity(int(a["text_count"]), int(b["text_count"])))
        + (0.12 * _count_similarity(int(a["shape_count"]), int(b["shape_count"])))
        + (0.12 * _count_similarity(int(a["rect_count"]), int(b["rect_count"])))
        + (0.10 * _count_similarity(int(a["card_count"]), int(b["card_count"])))
        + (0.08 * _count_similarity(int(a["headline_count"]), int(b["headline_count"])))
        + (0.20 * _cosine_similarity(list(a["text_grid"]), list(b["text_grid"])))
        + (0.18 * _cosine_similarity(list(a["shape_grid"]), list(b["shape_grid"])))
    )


def _check_ai_diversity(
    findings: list[PreflightFinding],
    signatures: list[tuple[Path, dict[str, Any]]],
) -> None:
    if len(signatures) < AI_DIVERSITY_MIN_SLIDES:
        return

    adjacent_duplicates: list[tuple[int, int, float]] = []
    for index in range(len(signatures) - 1):
        left_sig = signatures[index][1]
        right_sig = signatures[index + 1][1]
        similarity = _structure_similarity(left_sig, right_sig)
        if similarity >= AI_DIVERSITY_ADJACENT_SIM_THRESHOLD:
            adjacent_duplicates.append((index, index + 1, similarity))

    if not adjacent_duplicates:
        return

    duplicate_ratio = len(adjacent_duplicates) / max(1, len(signatures) - 1)
    if duplicate_ratio >= AI_DIVERSITY_ADJACENT_DUP_RATIO:
        start_path = signatures[adjacent_duplicates[0][0]][0]
        _emit(
            findings,
            "error",
            "template-fill-adjacent-ratio",
            start_path,
            (
                f"Adjacent structural similarity ratio is {duplicate_ratio:.0%} "
                f"(threshold {AI_DIVERSITY_ADJACENT_DUP_RATIO:.0%}). "
                "Deck looks template-filled; rewrite slide composition per page."
            ),
        )

    run_start = adjacent_duplicates[0][0]
    previous_right = adjacent_duplicates[0][1]
    longest_run = (run_start, previous_right)

    for left_idx, right_idx, _score in adjacent_duplicates[1:]:
        if left_idx == previous_right:
            previous_right = right_idx
        else:
            if (previous_right - run_start) > (longest_run[1] - longest_run[0]):
                longest_run = (run_start, previous_right)
            run_start = left_idx
            previous_right = right_idx
    if (previous_right - run_start) > (longest_run[1] - longest_run[0]):
        longest_run = (run_start, previous_right)

    run_slide_count = longest_run[1] - longest_run[0] + 1
    if run_slide_count >= 3:
        begin_path = signatures[longest_run[0]][0]
        _emit(
            findings,
            "error",
            "template-fill-consecutive-run",
            begin_path,
            (
                f"Detected {run_slide_count} consecutive slides with near-identical structure "
                f"(similarity >= {AI_DIVERSITY_ADJACENT_SIM_THRESHOLD:.2f}). "
                "AI authoring must vary composition by narrative intent, not reuse one template skeleton."
            ),
        )


def _has_cjk_text(texts: list[str]) -> bool:
    if not texts:
        return False
    joined = " ".join(texts)
    return len(CJK_CHAR_RE.findall(joined)) >= 20


def _slide_id_from_name(path: Path) -> int | None:
    stem = path.stem
    if not stem.startswith("slide_"):
        return None
    raw = stem.replace("slide_", "", 1)
    try:
        return int(raw)
    except ValueError:
        return None


def _collect_svg_files(project_dir: Path, svg_dir_name: str) -> list[Path]:
    svg_dir = project_dir / svg_dir_name
    return sorted(svg_dir.glob("slide_*.svg"))


def run_preflight(
    project_dir: Path,
    svg_dir_name: str = "svg_output",
    slide_ids: set[int] | None = None,
    enforce_ai_diversity: bool = True,
) -> PreflightReport:
    project_dir = project_dir.resolve()
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_md = qa_dir / "preflight-report.md"
    report_json = qa_dir / "preflight-report.json"

    files = _collect_svg_files(project_dir, svg_dir_name)
    if slide_ids:
        files = [path for path in files if _slide_id_from_name(path) in slide_ids]
    findings: list[PreflightFinding] = []
    signatures: list[tuple[Path, dict[str, Any]]] = []

    if not files:
        _emit(findings, "error", "missing-svg", project_dir / svg_dir_name, "No slide_*.svg files found.")

    for svg_file in files:
        payload = svg_file.read_bytes()
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            _emit(
                findings,
                "error",
                "invalid-utf8",
                svg_file,
                f"Invalid UTF-8 at byte offset {exc.start}: {exc.reason}.",
            )
            continue

        try:
            root = ET.fromstring(decoded)
        except ET.ParseError as exc:
            _emit(findings, "error", "invalid-xml", svg_file, f"Could not parse SVG XML: {exc}.")
            continue

        if _is_likely_mojibake(_collect_text_nodes(root)):
            _emit(
                findings,
                "error",
                "likely-mojibake",
                svg_file,
                "Text appears garbled (likely encoding mojibake). Rewrite this slide in UTF-8.",
            )

        visible_text_nodes = _collect_visible_text_nodes(root)
        if _has_cjk_text(visible_text_nodes):
            for node_text in visible_text_nodes:
                if SUSPICIOUS_QUESTION_BULLET_RE.search(node_text):
                    _emit(
                        findings,
                        "error",
                        "suspicious-question-bullet",
                        svg_file,
                        (
                            "Detected '?'+CJK bullet pattern. This usually indicates "
                            "symbol/encoding degradation; use a real bullet like '-' "
                            "or full Chinese wording."
                        ),
                    )

        has_foreign_object = any(_local_name(elem.tag) == "foreignObject" for elem in root.iter())
        if has_foreign_object:
            _emit(
                findings,
                "error",
                "forbidden-foreignobject",
                svg_file,
                "foreignObject is not allowed; use native SVG text/tspan.",
            )

        signatures.append((svg_file, _slide_structure_signature(root)))

    if enforce_ai_diversity and not slide_ids:
        _check_ai_diversity(findings, signatures)

    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings if item.severity == "warning")
    ok = errors == 0

    report_payload = {
        "project": str(project_dir),
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "scanned_files": len(files),
        "findings": [asdict(item) for item in findings],
    }
    report_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Preflight Report",
        "",
        f"- project: `{project_dir}`",
        f"- ok: `{ok}`",
        f"- errors: `{errors}`",
        f"- warnings: `{warnings}`",
        f"- scanned_files: `{len(files)}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No findings.")
    else:
        for item in findings:
            lines.append(f"- **{item.severity}** `{item.code}` at `{item.path}`: {item.message}")
    report_md.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    return PreflightReport(
        project=str(project_dir),
        ok=ok,
        errors=errors,
        warnings=warnings,
        findings=findings,
        scanned_files=len(files),
        report_md=report_md,
        report_json=report_json,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fast SVG preflight checks before build/export.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--svg-dir-name", default="svg_output", help="SVG input directory name under project.")
    parser.add_argument(
        "--no-ai-diversity",
        action="store_true",
        help="Disable adjacent structural diversity gate (not recommended).",
    )
    args = parser.parse_args(argv)

    report = run_preflight(
        args.project_dir,
        svg_dir_name=args.svg_dir_name,
        enforce_ai_diversity=not args.no_ai_diversity,
    )
    print(
        f"Preflight {'passed' if report.ok else 'failed'}: "
        f"errors={report.errors}, warnings={report.warnings}, scanned_files={report.scanned_files}"
    )
    print(report.report_md)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
