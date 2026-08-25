#!/usr/bin/env python3
"""Build visual quality trend dashboard from project manifest records."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent


@dataclass
class TrendRow:
    project_name: str
    timestamp: str
    quality_blocking: int
    quality_warning: int
    quality_advisory: int
    qa_errors: int
    qa_warnings: int
    qa_advisories: int
    qa_visual_score: float | None
    output_files: list[str]
    git_sha: str | None
    build_duration_sec: float | None
    context_bytes_estimate: int
    context_file_count: int
    context_token_estimate: int
    token_budget_limit: int
    token_budget_warning: bool
    incremental_mode: bool
    incremental_cache_hit: bool
    page_summary_cache_entries_updated: int
    page_summary_cache_hit_count: int
    page_summary_cache_miss_count: int
    page_summary_cache_hit_ratio: float


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def collect_trend_rows(projects_dir: Path) -> list[TrendRow]:
    rows: list[TrendRow] = []
    if not projects_dir.exists():
        return rows

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        manifest = project_dir / "exports" / "manifest.json"
        if not manifest.exists():
            continue
        try:
            payload = _read_json(manifest)
        except Exception:
            continue
        records = payload.get("records")
        if not isinstance(records, list):
            continue

        for record in records:
            if not isinstance(record, dict):
                continue
            tiers = record.get("quality_tiers")
            if not isinstance(tiers, dict):
                tiers = {}
            rows.append(
                TrendRow(
                    project_name=str(record.get("project_name") or project_dir.name),
                    timestamp=str(record.get("timestamp") or ""),
                    quality_blocking=_as_int(tiers.get("blocking"), _as_int(record.get("qa_errors"), 0)),
                    quality_warning=_as_int(tiers.get("warning"), _as_int(record.get("qa_warnings"), 0)),
                    quality_advisory=_as_int(tiers.get("advisory"), _as_int(record.get("qa_advisories"), 0)),
                    qa_errors=_as_int(record.get("qa_errors"), 0),
                    qa_warnings=_as_int(record.get("qa_warnings"), 0),
                    qa_advisories=_as_int(record.get("qa_advisories"), 0),
                    qa_visual_score=_as_float(record.get("qa_visual_score")),
                    output_files=[str(item) for item in (record.get("output_files") or []) if isinstance(item, str)],
                    git_sha=str(record.get("git_sha")) if record.get("git_sha") else None,
                    build_duration_sec=_as_float(record.get("build_duration_sec")),
                    context_bytes_estimate=_as_int(record.get("context_bytes_estimate"), 0),
                    context_file_count=_as_int(record.get("context_file_count"), 0),
                    context_token_estimate=_as_int(record.get("context_token_estimate"), 0),
                    token_budget_limit=_as_int(record.get("token_budget_limit"), 0),
                    token_budget_warning=bool(record.get("token_budget_warning", False)),
                    incremental_mode=bool(record.get("incremental_mode", False)),
                    incremental_cache_hit=bool(record.get("incremental_cache_hit", False)),
                    page_summary_cache_entries_updated=_as_int(record.get("page_summary_cache_entries_updated"), 0),
                    page_summary_cache_hit_count=_as_int(record.get("page_summary_cache_hit_count"), 0),
                    page_summary_cache_miss_count=_as_int(record.get("page_summary_cache_miss_count"), 0),
                    page_summary_cache_hit_ratio=float(record.get("page_summary_cache_hit_ratio") or 0.0),
                )
            )

    rows.sort(key=lambda item: (item.timestamp, item.project_name))
    return rows


def _render_html(rows: list[TrendRow]) -> str:
    visual_values = [row.qa_visual_score for row in rows if row.qa_visual_score is not None]
    avg_visual = round(sum(visual_values) / len(visual_values), 2) if visual_values else None
    duration_values = [row.build_duration_sec for row in rows if row.build_duration_sec is not None]
    avg_duration = round(sum(duration_values) / len(duration_values), 2) if duration_values else None
    avg_context_kb = (
        round(sum(row.context_bytes_estimate for row in rows) / max(1, len(rows)) / 1024.0, 2) if rows else 0.0
    )
    cache_hit_ratio = round(
        sum(1 for row in rows if row.incremental_mode and row.incremental_cache_hit) / max(1, len(rows)),
        3,
    )
    latest = rows[-1] if rows else None
    latest_timestamp = latest.timestamp if latest else "-"
    latest_blocking = latest.quality_blocking if latest else 0
    latest_warning = latest.quality_warning if latest else 0
    latest_advisory = latest.quality_advisory if latest else 0

    lines = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '  <meta charset="UTF-8" />',
        '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
        "  <title>Visual Quality Trend Dashboard</title>",
        "  <style>",
        (
            "    body{font:14px/1.6 'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;"
            "background:#f6f8fb;color:#1f2937;margin:0}"
        ),
        "    .wrap{max-width:1180px;margin:24px auto;padding:0 16px}",
        "    .card{background:#fff;border:1px solid #e5e7eb;border-radius:12px;padding:16px 18px;margin-bottom:12px}",
        "    h1{margin:0 0 8px;font-size:22px} h2{margin:0 0 8px;font-size:17px}",
        "    .muted{color:#6b7280}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}",
        "    .k{font-size:12px;color:#6b7280}.v{font-size:20px;font-weight:700}",
        (
            "    table{width:100%;border-collapse:collapse} "
            "th,td{border:1px solid #e5e7eb;padding:8px 10px;text-align:left;vertical-align:top}"
        ),
        "    th{background:#f9fafb} .ok{color:#0f766e;font-weight:600} .warn{color:#b45309;font-weight:600}",
        "  </style>",
        "</head>",
        "<body>",
        '  <div class="wrap">',
        '    <div class="card">',
        "      <h1>Visual Quality Trend Dashboard</h1>",
        f'      <div class="muted">records: {len(rows)} | generated from projects/*/exports/manifest.json</div>',
        "    </div>",
        '    <div class="card"><div class="grid">',
        f'      <div><div class="k">Latest Build</div><div class="v">{latest_timestamp}</div></div>',
        f'      <div><div class="k">Latest Blocking</div><div class="v">{latest_blocking}</div></div>',
        f'      <div><div class="k">Latest Warning</div><div class="v">{latest_warning}</div></div>',
        f'      <div><div class="k">Latest Advisory</div><div class="v">{latest_advisory}</div></div>',
        "    </div></div>",
        '    <div class="card">',
        "      <h2>Score Summary</h2>",
        (
            f'      <div class="muted">average visual score: '
            f'{avg_visual if avg_visual is not None else "n/a"} '
            "(visual QA enabled records only)</div>"
        ),
        (
            f'      <div class="muted">avg build duration: '
            f'{avg_duration if avg_duration is not None else "n/a"} sec | '
            f"avg context size: {avg_context_kb} KB | "
            f"incremental cache-hit ratio: {cache_hit_ratio}</div>"
        ),
        "    </div>",
        '    <div class="card">',
        "      <h2>Trend Records</h2>",
        "      <table>",
        (
            "        <thead><tr><th>timestamp</th><th>project</th><th>blocking/warning/advisory</th>"
            "<th>qa errors/warnings/advisories</th><th>visual score</th><th>build sec</th>"
            "<th>context KB/files/tokens</th><th>token budget</th><th>incremental</th>"
            "<th>page cache</th><th>output files</th></tr></thead>"
        ),
        "        <tbody>",
    ]
    if not rows:
        lines.append('          <tr><td colspan="11">No manifest records found.</td></tr>')
    for row in rows:
        tier_text = f"{row.quality_blocking}/{row.quality_warning}/{row.quality_advisory}"
        qa_text = f"{row.qa_errors}/{row.qa_warnings}/{row.qa_advisories}"
        visual = f"{row.qa_visual_score:.2f}" if row.qa_visual_score is not None else "n/a"
        build_sec = f"{row.build_duration_sec:.2f}" if row.build_duration_sec is not None else "n/a"
        context = (
            f"{round(row.context_bytes_estimate / 1024.0, 2)} KB / "
            f"{row.context_file_count} / {row.context_token_estimate}"
        )
        budget = f"{row.context_token_estimate}/{row.token_budget_limit}" if row.token_budget_limit > 0 else "n/a"
        if row.token_budget_warning and row.token_budget_limit > 0:
            budget += " (warn)"
        incremental = (
            "hit" if row.incremental_mode and row.incremental_cache_hit else ("on" if row.incremental_mode else "off")
        )
        page_cache = (
            f"{row.page_summary_cache_hit_count}/{row.page_summary_cache_entries_updated}"
            if row.page_summary_cache_entries_updated > 0
            else "0/0"
        )
        if row.page_summary_cache_entries_updated > 0:
            page_cache += f" ({row.page_summary_cache_hit_ratio:.2f})"
        files = "<br/>".join(row.output_files) if row.output_files else "-"
        lines.append(
            "          <tr>"
            f"<td>{row.timestamp}</td>"
            f"<td>{row.project_name}</td>"
            f"<td>{tier_text}</td>"
            f"<td>{qa_text}</td>"
            f"<td>{visual}</td>"
            f"<td>{build_sec}</td>"
            f"<td>{context}</td>"
            f"<td>{budget}</td>"
            f"<td>{incremental}</td>"
            f"<td>{page_cache}</td>"
            f"<td>{files}</td>"
            "</tr>"
        )
    lines.extend(
        [
            "        </tbody>",
            "      </table>",
            "    </div>",
            "  </div>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines) + "\n"


def write_dashboard(rows: list[TrendRow], output_html: Path, output_json: Path) -> None:
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(_render_html(rows), encoding="utf-8")
    payload = {"records": [asdict(item) for item in rows]}
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(projects_dir: Path, output_html: Path, output_json: Path) -> int:
    rows = collect_trend_rows(projects_dir)
    write_dashboard(rows, output_html, output_json)
    print(f"Wrote {output_html}")
    print(f"Wrote {output_json}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build visual quality trend dashboard from manifest records.")
    parser.add_argument("--projects-dir", type=Path, default=ROOT / "projects", help="Projects directory.")
    parser.add_argument(
        "--output-html",
        type=Path,
        default=REPO_ROOT / "docs" / "visual-quality-trend-dashboard.html",
        help="Output dashboard HTML path.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=REPO_ROOT / "docs" / "visual-quality-trend-data.json",
        help="Output trend JSON path.",
    )
    args = parser.parse_args(argv)
    return run(args.projects_dir, args.output_html, args.output_json)


if __name__ == "__main__":
    raise SystemExit(main())
