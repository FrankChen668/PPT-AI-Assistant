#!/usr/bin/env python3
"""State 0 intake contract: normalize source documents into document_ir + parse report."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SOURCE_MANIFEST_NAME = "manifest.json"
SOURCE_DIR_NAME = "sources"
OUTPUT_SOURCE_MANIFEST = "source_manifest.json"
OUTPUT_DOCUMENT_IR = "document_ir.json"
OUTPUT_PARSE_REPORT = "parse_report.json"

SUPPORTED_EXTENSIONS = {
    ".docx": "document",
    ".doc": "document",
    ".odt": "document",
    ".pdf": "pdf",
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".csv": "spreadsheet",
}

PRIMARY_CONVERTERS = {
    "document": "doc_to_md",
    "pdf": "pdf_to_md",
    "text": "txt_to_md",
    "markdown": "markdown_passthrough",
    "spreadsheet": "xlsx_to_md",
    "url": "web_to_md",
    "file": "doc_to_md",
    "unknown": "doc_to_md",
}
FALLBACK_CONVERTERS = {
    "document": "doc_to_md_fallback",
    "pdf": "pdf_to_md_fallback",
    "text": "txt_to_md_fallback",
    "markdown": "markdown_passthrough",
    "spreadsheet": "xlsx_to_md_fallback",
    "url": "web_to_md_fallback",
    "file": "doc_to_md_fallback",
    "unknown": "doc_to_md_fallback",
}

CLAIM_CUES = (
    "must",
    "should",
    "need",
    "recommend",
    "conclusion",
    "risk",
    "decision",
    "结论",
    "建议",
    "必须",
    "风险",
)
EVIDENCE_CUES = (
    "source",
    "reference",
    "evidence",
    "table",
    "figure",
    "附件",
    "证据",
    "数据来源",
    "图",
    "表",
)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]\s+|\d+\.\s+)(\S.*)$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
THEMATIC_BREAK_RE = re.compile(r"^ {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")


@dataclass
class IntakeRecord:
    source_id: str
    source_type: str
    original: str
    markdown_rel: str
    primary_converter: str
    fallback_converter: str


@dataclass
class IntakeWarning:
    code: str
    source_id: str
    message: str


def _project_cli_path(project_dir: Path) -> str:
    parts_lower = [part.lower() for part in project_dir.parts]
    for idx, part in enumerate(parts_lower):
        if part == "projects" and idx + 1 < len(project_dir.parts):
            return Path(*project_dir.parts[idx:]).as_posix()
    return Path("projects", project_dir.name).as_posix()


def _resolve_source_type(raw_type: str, original: str, markdown: str) -> str:
    candidate = raw_type.strip().lower()
    if candidate in {"document", "pdf", "text", "markdown", "spreadsheet", "url", "file"}:
        return candidate
    original_suffix = Path(original).suffix.lower()
    markdown_suffix = Path(markdown).suffix.lower()
    if original_suffix in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[original_suffix]
    if markdown_suffix in {".md", ".markdown"}:
        return "markdown"
    return "unknown"


def _manifest_path(project_dir: Path) -> Path:
    return project_dir / SOURCE_DIR_NAME / SOURCE_MANIFEST_NAME


def _load_manifest_records(project_dir: Path) -> list[dict[str, Any]]:
    manifest_path = _manifest_path(project_dir)
    if not manifest_path.exists():
        return []
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    records = payload.get("records")
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _scan_sources_dir(project_dir: Path) -> list[dict[str, Any]]:
    sources_dir = project_dir / SOURCE_DIR_NAME
    if not sources_dir.exists():
        return []
    discovered: list[dict[str, Any]] = []
    for path in sorted(sources_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == SOURCE_MANIFEST_NAME:
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            continue
        rel = path.relative_to(project_dir).as_posix()
        discovered.append(
            {
                "id": f"file-{path.stem}",
                "type": SUPPORTED_EXTENSIONS.get(suffix, "file"),
                "original": str(path),
                "markdown": rel if suffix in {".md", ".markdown", ".txt"} else "",
            }
        )
    return discovered


def _normalize_records(project_dir: Path) -> list[IntakeRecord]:
    records = _load_manifest_records(project_dir)
    if not records:
        records = _scan_sources_dir(project_dir)
    normalized: list[IntakeRecord] = []
    for idx, row in enumerate(records, start=1):
        source_id = str(row.get("id") or f"source-{idx}").strip()
        original = str(row.get("original") or "").strip()
        markdown_rel = str(row.get("markdown") or "").strip()
        source_type = _resolve_source_type(str(row.get("type") or ""), original, markdown_rel)
        primary = PRIMARY_CONVERTERS.get(source_type, PRIMARY_CONVERTERS["unknown"])
        fallback = FALLBACK_CONVERTERS.get(source_type, FALLBACK_CONVERTERS["unknown"])
        normalized.append(
            IntakeRecord(
                source_id=source_id,
                source_type=source_type,
                original=original,
                markdown_rel=markdown_rel,
                primary_converter=primary,
                fallback_converter=fallback,
            )
        )
    return normalized


def _iter_lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]


def _extract_sections(text: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for line in _iter_lines(text):
        match = HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(1).strip()
        if heading:
            sections.append({"title": heading})
    return sections


def _count_list_items(text: str) -> int:
    count = 0
    fence_char = ""
    fence_length = 0
    in_fence = False
    for line in _iter_lines(text):
        if line.startswith("\t") or line.startswith("    "):
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            marker_char = marker[0]
            if in_fence:
                if (
                    marker_char == fence_char
                    and len(marker) >= fence_length
                    and not fence_match.group(2).strip()
                ):
                    in_fence = False
                    fence_char = ""
                    fence_length = 0
            else:
                in_fence = True
                fence_char = marker_char
                fence_length = len(marker)
            continue

        if in_fence or THEMATIC_BREAK_RE.match(line):
            continue
        if LIST_ITEM_RE.match(line):
            count += 1
    return count


def _extract_tables(text: str) -> list[dict[str, Any]]:
    table_lines = [line for line in _iter_lines(text) if line.count("|") >= 2]
    if not table_lines:
        return []
    return [{"line": idx + 1, "preview": line[:120]} for idx, line in enumerate(table_lines[:16])]


def _extract_claims(text: str) -> list[str]:
    claims: list[str] = []
    for line in _iter_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(cue in stripped for cue in CLAIM_CUES) or any(cue in lowered for cue in CLAIM_CUES):
            claims.append(stripped)
    return claims[:24]


def _extract_evidence_refs(text: str) -> list[str]:
    refs: list[str] = []
    for line in _iter_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(cue in stripped for cue in EVIDENCE_CUES) or any(cue in lowered for cue in EVIDENCE_CUES):
            refs.append(stripped)
    return refs[:24]


def _extract_key_numbers(text: str) -> list[str]:
    found = NUMBER_RE.findall(text)
    unique: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
        if len(unique) >= 40:
            break
    return unique


def _score_content(
    *,
    char_count: int,
    section_count: int,
    claim_count: int,
    evidence_count: int,
    table_count: int,
    list_item_count: int,
) -> int:
    score = 0
    if char_count >= 200:
        score += 35
    elif char_count >= 80:
        score += 20
    elif char_count > 0:
        score += 8
    score += min(20, section_count * 5)
    score += min(20, claim_count * 4)
    score += min(15, evidence_count * 3)
    score += min(10, table_count * 5)
    score += min(15, list_item_count * 3)
    return min(100, score)


def _read_markdown(project_dir: Path, rel_path: str) -> str | None:
    if not rel_path:
        return None
    markdown_path = (project_dir / rel_path).resolve()
    try:
        project_root = project_dir.resolve()
        markdown_path.relative_to(project_root)
    except Exception:
        return None
    if not markdown_path.exists() or not markdown_path.is_file():
        return None
    try:
        return markdown_path.read_text(encoding="utf-8-sig")
    except Exception:
        return markdown_path.read_text(encoding="utf-8", errors="replace")


def _build_document_ir(
    project_dir: Path,
    records: list[IntakeRecord],
    *,
    quality_threshold: int,
) -> tuple[dict[str, Any], dict[str, Any], list[IntakeWarning]]:
    warnings: list[IntakeWarning] = []
    ir_sources: list[dict[str, Any]] = []
    parse_rows: list[dict[str, Any]] = []
    scores: list[int] = []

    for record in records:
        markdown_text = _read_markdown(project_dir, record.markdown_rel)
        if markdown_text is None:
            warnings.append(
                IntakeWarning(
                    code="missing_markdown_artifact",
                    source_id=record.source_id,
                    message=(
                        f"Missing markdown artifact for source `{record.source_id}`; "
                        f"expected `{record.markdown_rel}`."
                    ),
                )
            )
            parse_rows.append(
                {
                    "source_id": record.source_id,
                    "source_type": record.source_type,
                    "primary_converter": record.primary_converter,
                    "fallback_converter": record.fallback_converter,
                    "used_converter": record.fallback_converter,
                    "fallback_triggered": True,
                    "quality_score": 0,
                    "status": "missing_markdown",
                    "warnings": ["missing markdown artifact"],
                }
            )
            continue

        sections = _extract_sections(markdown_text)
        tables = _extract_tables(markdown_text)
        claims = _extract_claims(markdown_text)
        evidence_refs = _extract_evidence_refs(markdown_text)
        key_numbers = _extract_key_numbers(markdown_text)
        list_item_count = _count_list_items(markdown_text)
        char_count = len(markdown_text.strip())
        score = _score_content(
            char_count=char_count,
            section_count=len(sections),
            claim_count=len(claims),
            evidence_count=len(evidence_refs),
            table_count=len(tables),
            list_item_count=list_item_count,
        )
        fallback_triggered = score < quality_threshold
        used_converter = record.fallback_converter if fallback_triggered else record.primary_converter
        scores.append(score)

        if fallback_triggered:
            warnings.append(
                IntakeWarning(
                    code="low_parse_quality",
                    source_id=record.source_id,
                    message=(
                        f"parse_quality_score={score} below threshold={quality_threshold}; "
                        f"fallback converter selected (`{record.fallback_converter}`)."
                    ),
                )
            )

        ir_sources.append(
            {
                "source_id": record.source_id,
                "source_type": record.source_type,
                "original": record.original,
                "markdown": record.markdown_rel,
                "sections": sections,
                "tables": tables,
                "claims": claims,
                "evidence_refs": evidence_refs,
                "key_numbers": key_numbers,
                "warnings": [
                    "low_parse_quality" if fallback_triggered else "",
                ],
                "quality_score": score,
            }
        )
        parse_rows.append(
            {
                "source_id": record.source_id,
                "source_type": record.source_type,
                "primary_converter": record.primary_converter,
                "fallback_converter": record.fallback_converter,
                "used_converter": used_converter,
                "fallback_triggered": fallback_triggered,
                "quality_score": score,
                "status": "ok" if not fallback_triggered else "fallback_selected",
                "warnings": ["low_parse_quality"] if fallback_triggered else [],
            }
        )

    deck_score = int(round(sum(scores) / len(scores))) if scores else 0
    gate_passed = deck_score >= quality_threshold and all(row["status"] != "missing_markdown" for row in parse_rows)

    ir_payload = {
        "schema_version": 1,
        "project": _project_cli_path(project_dir),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "quality_score": deck_score,
        "sections": [item for src in ir_sources for item in src.get("sections", [])][:120],
        "tables": [item for src in ir_sources for item in src.get("tables", [])][:120],
        "claims": [item for src in ir_sources for item in src.get("claims", [])][:120],
        "evidence_refs": [item for src in ir_sources for item in src.get("evidence_refs", [])][:120],
        "warnings": [asdict_warning.code for asdict_warning in warnings],
        "sources": ir_sources,
    }

    parse_report = {
        "schema_version": 1,
        "project": _project_cli_path(project_dir),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "quality_threshold": quality_threshold,
        "parse_quality_score": deck_score,
        "gate_passed": gate_passed,
        "requires_risk_confirmation": not gate_passed,
        "fallback_triggered": any(bool(row.get("fallback_triggered")) for row in parse_rows),
        "records": parse_rows,
        "warnings": [
            {"code": warning.code, "source_id": warning.source_id, "message": warning.message}
            for warning in warnings
        ],
    }
    return ir_payload, parse_report, warnings


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_document_intake(project_dir: Path, *, quality_threshold: int = 55, strict_gate: bool = False) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    records = _normalize_records(project_dir)
    source_manifest_payload = {
        "schema_version": 1,
        "project": _project_cli_path(project_dir),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "records": [
            {
                "source_id": record.source_id,
                "source_type": record.source_type,
                "original": record.original,
                "markdown": record.markdown_rel,
                "primary_converter": record.primary_converter,
                "fallback_converter": record.fallback_converter,
            }
            for record in records
        ],
    }

    document_ir, parse_report, _warnings = _build_document_ir(
        project_dir,
        records,
        quality_threshold=quality_threshold,
    )
    _write_json(project_dir / OUTPUT_SOURCE_MANIFEST, source_manifest_payload)
    _write_json(project_dir / OUTPUT_DOCUMENT_IR, document_ir)
    _write_json(project_dir / OUTPUT_PARSE_REPORT, parse_report)

    if strict_gate and not bool(parse_report.get("gate_passed")):
        raise RuntimeError(
            "State 0 intake gate failed: "
            f"parse_quality_score={parse_report.get('parse_quality_score')} "
            f"< threshold={quality_threshold}. "
            "补充源文档、修复转换质量，或在 clarification_brief.json 明确风险假设后再继续。"
        )
    return {
        "source_manifest_path": str(project_dir / OUTPUT_SOURCE_MANIFEST),
        "document_ir_path": str(project_dir / OUTPUT_DOCUMENT_IR),
        "parse_report_path": str(project_dir / OUTPUT_PARSE_REPORT),
        "parse_quality_score": int(parse_report.get("parse_quality_score", 0)),
        "gate_passed": bool(parse_report.get("gate_passed", False)),
        "record_count": len(records),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate State 0 intake artifacts for a project.")
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>.")
    parser.add_argument("--quality-threshold", type=int, default=55, help="Minimum parse quality score for gate pass.")
    parser.add_argument(
        "--strict-gate",
        action="store_true",
        help="Return non-zero when intake gate is not passed.",
    )
    args = parser.parse_args(argv)

    try:
        summary = run_document_intake(
            args.project_dir,
            quality_threshold=args.quality_threshold,
            strict_gate=args.strict_gate,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}")
        return 1

    print(
        "State 0 intake completed: "
        f"records={summary['record_count']} "
        f"parse_quality_score={summary['parse_quality_score']} "
        f"gate_passed={str(summary['gate_passed']).lower()}"
    )
    print(f"- {summary['source_manifest_path']}")
    print(f"- {summary['document_ir_path']}")
    print(f"- {summary['parse_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
