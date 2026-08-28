#!/usr/bin/env python3
"""Generate a local rule-based source_brief.md from project sources."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
MAX_THEMES = 8
MAX_CLAIMS = 12
MAX_CLAIMS_PER_SOURCE = 4
MAX_ASSUMPTIONS = 8
MAX_SAMPLE_LINES = 2

CLAIM_CUES = (
    "must",
    "need",
    "should",
    "recommend",
    "conclusion",
    "risk",
    "approved",
    "delivery_status",
    "errors=0",
    "warnings=0",
    "必须",
    "需要",
    "建议",
    "结论",
    "风险",
    "通过",
)
ASSUMPTION_CUES = ("assumption", "assumptions", "assume", "assuming", "假设")
HEADING_RE = re.compile(r"^\s{0,3}#{1,4}\s+(.+?)\s*$")
MOJIBAKE_MARKERS = ("Ã", "Â", "Ð", "Ñ", "â€", "ï»¿")


@dataclass
class SourceRecord:
    source_id: str
    source_type: str
    original: str
    markdown_rel: str
    file_path: Path


@dataclass
class SourceQuality:
    source_id: str
    markdown_rel: str
    status: str
    warning: str | None = None


def _project_cli_path(project_dir: Path) -> str:
    parts_lower = [part.lower() for part in project_dir.parts]
    for index, part in enumerate(parts_lower):
        if part == "projects" and index + 1 < len(project_dir.parts):
            return Path(*project_dir.parts[index:]).as_posix()
    return Path("projects", project_dir.name).as_posix()


def _load_manifest(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    gaps: list[str] = []
    if not path.exists():
        gaps.append("sources/manifest.json is missing; inventory falls back to file scan.")
        return [], gaps
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"sources/manifest.json is not valid JSON: {exc}. Inventory falls back to file scan.")
        return [], gaps
    if not isinstance(payload, dict):
        gaps.append("sources/manifest.json root is not an object; inventory falls back to file scan.")
        return [], gaps
    records = payload.get("records")
    if not isinstance(records, list):
        gaps.append("sources/manifest.json has no records[] list; inventory falls back to file scan.")
        return [], gaps
    return records, gaps


def _normalize_manifest_records(
    project_dir: Path,
    records: list[dict[str, Any]],
) -> tuple[list[SourceRecord], list[str]]:
    normalized: list[SourceRecord] = []
    gaps: list[str] = []
    for idx, item in enumerate(records, start=1):
        if not isinstance(item, dict):
            gaps.append(f"manifest record #{idx} is not an object.")
            continue
        source_id = str(item.get("id") or f"source-{idx}").strip()
        source_type = str(item.get("type") or "unknown").strip()
        original = str(item.get("original") or "").strip()
        markdown_rel = str(item.get("markdown") or "").strip()
        if not markdown_rel:
            gaps.append(f"manifest record {source_id} has empty markdown path.")
            continue
        file_path = (project_dir / markdown_rel).resolve()
        if not file_path.exists():
            gaps.append(f"manifest record {source_id} points to missing file: {markdown_rel}.")
            continue
        normalized.append(
            SourceRecord(
                source_id=source_id,
                source_type=source_type or "unknown",
                original=original,
                markdown_rel=markdown_rel,
                file_path=file_path,
            )
        )
    return normalized, gaps


def _discover_source_files(project_dir: Path) -> list[SourceRecord]:
    sources_dir = project_dir / "sources"
    if not sources_dir.exists():
        return []
    records: list[SourceRecord] = []
    for path in sorted(sources_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == "manifest.json":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(project_dir).as_posix()
        records.append(
            SourceRecord(
                source_id=f"file-{path.stem}",
                source_type="text",
                original=str(path),
                markdown_rel=rel,
                file_path=path.resolve(),
            )
        )
    return records


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_headings(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        match = HEADING_RE.match(line)
        if match:
            items.append(match.group(1).strip())
    return items


def _split_sentences(text: str) -> list[str]:
    pieces = re.split(r"[。！？!?;\n]+", text)
    return [piece.strip() for piece in pieces if piece and piece.strip()]


def _extract_claims(text: str) -> list[str]:
    claims: list[str] = []
    for sentence in _split_sentences(text):
        lowered = sentence.lower()
        if any(cue in sentence for cue in CLAIM_CUES) or any(cue in lowered for cue in CLAIM_CUES):
            claims.append(sentence)
    return claims


def _extract_assumptions(text: str) -> list[str]:
    assumptions: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(cue in stripped for cue in ASSUMPTION_CUES) or any(cue in lowered for cue in ASSUMPTION_CUES):
            assumptions.append(stripped)
    return assumptions


def _suggested_angles(themes: list[str], claims: list[str]) -> list[str]:
    theme_blob = " ".join(themes).lower()
    claim_blob = " ".join(claims).lower()
    angles: list[str] = []
    if "risk" in theme_blob or "risk" in claim_blob or "风险" in theme_blob:
        angles.append("Risk closure angle: quantify top risks first, then map controls and timeline.")
    if "roadmap" in theme_blob or "timeline" in theme_blob or "milestone" in claim_blob:
        angles.append("Implementation path angle: stage by milestone and define acceptance at each phase.")
    if "template" in theme_blob or "consistency" in theme_blob or "style" in claim_blob:
        angles.append("Delivery consistency angle: make template/style constraints and audit posture explicit.")
    if not angles:
        angles.append("Conclusion-first angle: answer why now and what decision is needed on slide 1.")
        angles.append("Evidence-chain angle: center slides on verifiable facts, boundaries, and dependencies.")
        angles.append("Decision-closure angle: end with value, residual risk, and next-step decision requests.")
    return angles[:4]


def _is_likely_binary(raw: bytes) -> bool:
    if not raw:
        return False
    if b"\x00" in raw:
        return True
    control_count = sum(1 for byte in raw if byte < 9 or (13 < byte < 32))
    ratio = control_count / len(raw)
    return ratio > 0.18


def _looks_garbled(text: str) -> bool:
    if not text.strip():
        return False
    if "\ufffd" in text:
        return True
    if any(marker in text for marker in MOJIBAKE_MARKERS):
        return True
    non_printable = 0
    for ch in text:
        if ch in {"\n", "\r", "\t"}:
            continue
        if unicodedata.category(ch).startswith("C"):
            non_printable += 1
    return (non_printable / max(len(text), 1)) > 0.08


def _decode_source_bytes(raw: bytes) -> tuple[str | None, str | None]:
    for encoding in ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "gb18030"):
        try:
            return raw.decode(encoding), None
        except UnicodeDecodeError:
            continue
    return None, "unable to decode source bytes with utf-8/utf-16/gb18030"


def _read_source_text(record: SourceRecord) -> tuple[str | None, SourceQuality]:
    try:
        raw = record.file_path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return None, SourceQuality(
            source_id=record.source_id,
            markdown_rel=record.markdown_rel,
            status="read_error",
            warning=f"failed to read: {exc}",
        )
    if len(raw) == 0:
        return None, SourceQuality(
            source_id=record.source_id,
            markdown_rel=record.markdown_rel,
            status="empty",
            warning="source file is empty",
        )
    if _is_likely_binary(raw):
        return None, SourceQuality(
            source_id=record.source_id,
            markdown_rel=record.markdown_rel,
            status="binary_like",
            warning="source appears binary or non-text; skipped for extraction",
        )
    text, decode_error = _decode_source_bytes(raw)
    if text is None:
        return None, SourceQuality(
            source_id=record.source_id,
            markdown_rel=record.markdown_rel,
            status="decode_error",
            warning=decode_error,
        )
    if _looks_garbled(text):
        sample_lines = [line.strip() for line in text.splitlines() if line.strip()][:MAX_SAMPLE_LINES]
        sample = " | ".join(sample_lines)
        return None, SourceQuality(
            source_id=record.source_id,
            markdown_rel=record.markdown_rel,
            status="garbled",
            warning=f"source text looks garbled; sample={sample[:120]}",
        )
    return text, SourceQuality(source_id=record.source_id, markdown_rel=record.markdown_rel, status="ok")


def _render_brief(
    project_dir: Path,
    records: list[SourceRecord],
    source_quality: list[SourceQuality],
    themes: list[str],
    claims: list[tuple[str, str]],
    assumptions: list[str],
    gaps: list[str],
    warnings: list[str],
    angles: list[str],
) -> str:
    project_cli = _project_cli_path(project_dir)
    lines: list[str] = [
        "# Source Brief",
        "",
        f"- project: `{project_cli}`",
        f"- source_count: `{len(records)}`",
        "",
        "## Source Inventory",
    ]
    if records:
        for record in records:
            original = record.original or "n/a"
            lines.append(
                f"- id=`{record.source_id}` type=`{record.source_type}` "
                f"markdown=`{record.markdown_rel}` original=`{original}`"
            )
    else:
        lines.append("- No source files found in `sources/`.")

    lines.extend(["", "## Source Quality / Warnings"])
    if source_quality:
        for quality_item in source_quality:
            summary = f"- [{quality_item.status}] `{quality_item.source_id}` `{quality_item.markdown_rel}`"
            if quality_item.warning:
                summary += f": {quality_item.warning}"
            lines.append(summary)
    else:
        lines.append("- No source quality records generated.")
    if warnings:
        for warning in _dedupe_keep_order(warnings):
            lines.append(f"- [pipeline-warning] {warning}")

    lines.extend(["", "## Key Themes"])
    if themes:
        for theme in themes:
            lines.append(f"- {theme}")
    else:
        lines.append("- No clear themes extracted from usable source text.")

    lines.extend(["", "## Usable Claims"])
    if claims:
        for source_id, claim in claims:
            lines.append(f"- [{source_id}] {claim}")
    else:
        lines.append("- No high-confidence claims extracted; manual review required.")

    lines.extend(["", "## Assumptions"])
    if assumptions:
        for assumption in assumptions:
            lines.append(f"- {assumption}")
    else:
        lines.append(
            "- No explicit assumptions found in usable source text; "
            "add them in clarification_brief/design_spec."
        )

    lines.extend(["", "## Gaps / Unknowns"])
    merged_gaps = _dedupe_keep_order(gaps)
    if not merged_gaps:
        merged_gaps = ["No structural ingestion gap detected. Validate factual accuracy manually before delivery."]
    for gap in merged_gaps:
        lines.append(f"- {gap}")

    lines.extend(["", "## Suggested Deck Angles"])
    for angle in angles:
        lines.append(f"- {angle}")
    lines.append("")
    return "\n".join(lines)


def generate_source_brief(project_dir: Path, output_path: Path | None = None) -> Path:
    project_dir = project_dir.resolve()
    if not project_dir.exists():
        raise FileNotFoundError(f"project directory not found: {project_dir}")

    sources_dir = project_dir / "sources"
    manifest_path = sources_dir / "manifest.json"
    manifest_records, gaps = _load_manifest(manifest_path)
    records: list[SourceRecord] = []
    warnings: list[str] = []

    if manifest_records:
        records, normalize_gaps = _normalize_manifest_records(project_dir, manifest_records)
        gaps.extend(normalize_gaps)
    if not records:
        fallback_records = _discover_source_files(project_dir)
        records = fallback_records
        if manifest_records and not fallback_records:
            gaps.append("Manifest exists but no usable markdown/text files were found.")
    if not records:
        gaps.append("No source material is currently available under sources/.")

    themes_raw: list[str] = []
    claims_raw: list[tuple[str, str]] = []
    assumptions_raw: list[str] = []
    source_quality: list[SourceQuality] = []

    for record in records:
        text, quality = _read_source_text(record)
        source_quality.append(quality)
        if quality.warning:
            warnings.append(f"{record.markdown_rel}: {quality.warning}")
            if quality.status in {"empty", "binary_like", "decode_error", "garbled", "read_error"}:
                gaps.append(f"Source {record.markdown_rel} is unusable for structured extraction ({quality.status}).")
        if text is None:
            continue

        headings = _extract_headings(text)
        if headings:
            themes_raw.extend(headings[:3])
        else:
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            if first_line:
                themes_raw.append(first_line[:120])

        record_claims = _extract_claims(text)[:MAX_CLAIMS_PER_SOURCE]
        for claim in record_claims:
            claims_raw.append((record.source_id, claim))
        assumptions_raw.extend(_extract_assumptions(text))

    themes = _dedupe_keep_order(themes_raw)[:MAX_THEMES]
    assumptions = _dedupe_keep_order(assumptions_raw)[:MAX_ASSUMPTIONS]

    seen_claims: set[tuple[str, str]] = set()
    claims: list[tuple[str, str]] = []
    for source_id, claim in claims_raw:
        key = (source_id, claim.strip())
        if not key[1]:
            continue
        if key in seen_claims:
            continue
        seen_claims.add(key)
        claims.append((source_id, key[1]))
        if len(claims) >= MAX_CLAIMS:
            break

    if not claims:
        gaps.append("No explicit usable claims were extracted from usable source text.")
    if not assumptions:
        gaps.append("No explicit assumptions were extracted; clarify assumptions before strategy/final review.")

    angles = _suggested_angles(themes, [claim for _, claim in claims])
    rendered = _render_brief(project_dir, records, source_quality, themes, claims, assumptions, gaps, warnings, angles)

    destination = output_path.resolve() if output_path is not None else (project_dir / "source_brief.md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered, encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate rule-based source_brief.md from project sources.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>")
    parser.add_argument("--output", type=Path, help="Optional output path (default: <project>/source_brief.md)")
    args = parser.parse_args(argv)
    output_path = generate_source_brief(args.project_dir, args.output)
    print(f"[OK] Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
