#!/usr/bin/env python3
"""Shared QA report read/write helpers for mainline QA and workbench adapters."""

from __future__ import annotations

import json
from pathlib import Path


def write_report_json(qa_dir: Path, payload: dict) -> Path:
    qa_dir.mkdir(parents=True, exist_ok=True)
    path = qa_dir / "report.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_report_markdown(qa_dir: Path, markdown: str) -> Path:
    qa_dir.mkdir(parents=True, exist_ok=True)
    path = qa_dir / "report.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def load_report_markdown_excerpt(project_dir: Path, limit: int = 2000) -> str:
    report_path = project_dir / "qa" / "report.md"
    if not report_path.is_file():
        return ""
    content = report_path.read_text(encoding="utf-8", errors="replace")
    return content[-limit:] if len(content) > limit else content
