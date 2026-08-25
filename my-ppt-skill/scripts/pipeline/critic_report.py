#!/usr/bin/env python3
"""Pure helpers for slide critic sidecar reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPAIR_ACTIONS = {
    "text-outside-canvas": "Move text inside canvas or reduce the text block size.",
    "text-overlap": "Separate overlapping text blocks or switch to a looser layout.",
    "contrast-too-low": "Use darker text or a richer background for the affected text.",
    "theme-low-contrast-background": "Adjust design_spec.md text/background tokens.",
    "theme-low-contrast-card": "Adjust design_spec.md text/card tokens.",
    "visual-density-high": "Reduce secondary copy or split this slide.",
    "visual-hierarchy-flat": "Make the main conclusion visually dominant.",
}

DEFAULT_REPAIR_ORDER = [
    "Fix blocking layout errors.",
    "Fix low contrast text.",
    "Reduce density or split page if needed.",
    "Re-run critic and then single-slide QA.",
]


def repair_action_for_code(code: str) -> str:
    return REPAIR_ACTIONS.get(
        (code or "").strip(),
        "Review this finding and repair the slide before delivery.",
    )


def normalize_severity(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"error", "err", "fatal"}:
        return "error"
    if lowered in {"warning", "warn"}:
        return "warning"
    if lowered in {"advisory", "info", "note"}:
        return "advisory"
    return "advisory"


def build_critic_report(project_dir: Path, slide: int, findings: list[dict[str, Any]]) -> dict[str, Any]:
    normalized: list[dict[str, str]] = []
    summary = {"errors": 0, "warnings": 0, "advisories": 0}

    for finding in findings:
        severity = normalize_severity(str(finding.get("severity", "")))
        code = str(finding.get("code", "unknown")).strip() or "unknown"
        source = str(finding.get("source", "unknown")).strip() or "unknown"
        message = str(finding.get("message", "")).strip() or "No message provided."
        repair_action = repair_action_for_code(code)
        normalized.append(
            {
                "severity": severity,
                "code": code,
                "source": source,
                "message": message,
                "repair_action": repair_action,
            }
        )
        if severity == "error":
            summary["errors"] += 1
        elif severity == "warning":
            summary["warnings"] += 1
        else:
            summary["advisories"] += 1

    return {
        "project": project_dir.name,
        "slide": int(slide),
        "ok": summary["errors"] == 0,
        "summary": summary,
        "findings": normalized,
        "repair_order": list(DEFAULT_REPAIR_ORDER),
    }


def write_critic_reports(report: dict[str, Any], qa_dir: Path) -> tuple[Path, Path]:
    qa_dir.mkdir(parents=True, exist_ok=True)
    slide = int(report["slide"])
    json_path = qa_dir / f"critic_slide_{slide:02d}.json"
    md_path = qa_dir / f"critic_slide_{slide:02d}.md"

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    status = "PASS" if bool(report.get("ok")) else "BLOCKED"
    summary = report.get("summary", {})
    findings = report.get("findings", [])
    repair_order = report.get("repair_order", [])

    lines = [
        f"# Critic Report: slide_{slide:02d}.svg",
        "",
        f"Status: {status}",
        "",
        "## Summary",
        "",
        f"- Errors: {int(summary.get('errors', 0))}",
        f"- Warnings: {int(summary.get('warnings', 0))}",
        f"- Advisories: {int(summary.get('advisories', 0))}",
        "",
        "## Findings",
        "",
    ]

    if not findings:
        lines.append("No findings.")
    else:
        for index, item in enumerate(findings, start=1):
            severity = str(item.get("severity", "advisory"))
            code = str(item.get("code", "unknown"))
            source = str(item.get("source", "unknown"))
            message = str(item.get("message", ""))
            repair = str(item.get("repair_action", ""))
            lines.extend(
                [
                    f"{index}. [{severity}] {code}",
                    f"   Source: {source}",
                    f"   Message: {message}",
                    f"   Repair: {repair}",
                ]
            )

    lines.extend(["", "## Recommended Repair Order", ""])
    for index, step in enumerate(repair_order, start=1):
        lines.append(f"{index}. {step}")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path
