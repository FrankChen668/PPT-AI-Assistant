#!/usr/bin/env python3
"""Export blind holdout manual-review queue from set/results artifacts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_review_queue(
    *,
    set_config: dict[str, Any],
    results_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    blind_projects: list[dict[str, Any]] = []
    result_rows = []
    if isinstance(results_payload, dict):
        rows = results_payload.get("results")
        if isinstance(rows, list):
            result_rows = [row for row in rows if isinstance(row, dict)]
    result_map = {
        (str(row.get("project") or ""), str(row.get("mode") or "")): row for row in result_rows
    }

    projects = set_config.get("projects")
    if not isinstance(projects, list):
        projects = []

    for item in projects:
        if not isinstance(item, dict):
            continue
        if str(item.get("baseline_role") or "").strip() != "blind_holdout":
            continue
        project_name = str(item.get("project") or "").strip()
        if not project_name:
            continue
        manual = item.get("manual_visual_review")
        manual_map = manual if isinstance(manual, dict) else {}
        status = str(manual_map.get("status") or "pending").strip().lower() or "pending"
        reviewer = str(manual_map.get("reviewer") or "").strip()
        score = manual_map.get("score")
        note = str(item.get("sample_note") or "").strip()
        release_row = result_map.get((project_name, "release-safe"), {})
        blind_projects.append(
            {
                "project": project_name,
                "manual_visual_review": {
                    "status": status,
                    "reviewer": reviewer,
                    "score": score,
                },
                "sample_note": note,
                "latest_release_safe": {
                    "status": str(release_row.get("status") or ""),
                    "admission_status": str(release_row.get("admission_status") or ""),
                    "failure_category": str(release_row.get("failure_category") or ""),
                },
                "needs_manual_review": status != "complete",
            }
        )

    pending = [row for row in blind_projects if bool(row.get("needs_manual_review"))]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "blind_holdout_total": len(blind_projects),
        "pending_total": len(pending),
        "pending_projects": [str(row.get("project") or "") for row in pending],
        "items": blind_projects,
    }


def build_markdown(queue: dict[str, Any], *, set_path: Path, results_path: Path | None) -> str:
    lines: list[str] = []
    lines.append(f"# Blind Manual Review Queue ({datetime.now().strftime('%Y-%m-%d')})")
    lines.append("")
    lines.append(f"- Set: `{set_path}`")
    lines.append(f"- Results: `{results_path}`" if results_path else "- Results: `(none)`")
    lines.append(f"- Blind holdout total: `{queue.get('blind_holdout_total', 0)}`")
    lines.append(f"- Pending total: `{queue.get('pending_total', 0)}`")
    lines.append("")
    lines.append("## Pending Projects")
    lines.append("")
    pending = queue.get("pending_projects")
    if isinstance(pending, list) and pending:
        for name in pending:
            lines.append(f"- `{name}`")
    else:
        lines.append("- `(none)`")
    lines.append("")
    lines.append("## Items")
    lines.append("")
    lines.append("| Project | Manual Status | Reviewer | Score | Release-safe Status | Admission | Note |")
    lines.append("|---|---|---|---:|---|---|---|")
    for row in queue.get("items", []):
        if not isinstance(row, dict):
            continue
        manual = row.get("manual_visual_review") or {}
        latest = row.get("latest_release_safe") or {}
        note_text = str(row.get("sample_note") or "").replace("|", "\\|")
        lines.append(
            f"| `{row.get('project')}` | `{manual.get('status', '')}` | `{manual.get('reviewer', '')}` | "
            f"{manual.get('score') if manual.get('score') is not None else '-'} | "
            f"`{latest.get('status', '')}` | `{latest.get('admission_status', '')}` | "
            f"{note_text} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `visual_score` is not treated as manual visual approval.")
    lines.append("- `manual_visual_review.status=complete/reject` should include non-empty reviewer.")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export blind holdout manual-review queue.")
    parser.add_argument("--set", dest="set_path", required=True, help="Path to blind eval set JSON.")
    parser.add_argument("--results", dest="results_path", default="", help="Optional results JSON path.")
    parser.add_argument("--output-json", required=True, help="Queue JSON output path.")
    parser.add_argument("--output-md", required=True, help="Queue markdown output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    set_path = Path(args.set_path).resolve()
    results_path = Path(args.results_path).resolve() if args.results_path else None
    out_json = Path(args.output_json).resolve()
    out_md = Path(args.output_md).resolve()

    if not set_path.exists():
        print(f"error: set file not found: {set_path}")
        return 2
    if results_path and not results_path.exists():
        print(f"error: results file not found: {results_path}")
        return 2

    set_config = _load_json(set_path)
    results_payload = _load_json(results_path) if results_path else None
    queue = build_review_queue(set_config=set_config, results_payload=results_payload)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(build_markdown(queue, set_path=set_path, results_path=results_path), encoding="utf-8")

    print(f"wrote queue json: {out_json}")
    print(f"wrote queue markdown: {out_md}")
    print(f"pending manual review: {queue.get('pending_total', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
