from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DAYS = 30
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = REPO_ROOT / "my-ppt-skill" / "projects"


def _parse_recorded_at(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _in_window(record: dict[str, Any], start: datetime, end: datetime) -> bool:
    recorded_at = _parse_recorded_at(record.get("recorded_at"))
    return bool(recorded_at and start <= recorded_at <= end)


def load_issue_records(projects_root: Path, days: int = DEFAULT_DAYS, now: datetime | None = None) -> list[dict[str, Any]]:
    end = (now or datetime.now(UTC)).astimezone(UTC)
    start = end - timedelta(days=max(days, 1))
    records: list[dict[str, Any]] = []
    for log_path in sorted(projects_root.glob("*/qa/quality-issues.jsonl")):
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and _in_window(record, start, end):
                records.append(record)
    return records


def build_report(projects_root: Path = PROJECTS_ROOT, days: int = DEFAULT_DAYS, now: datetime | None = None) -> dict[str, Any]:
    end = (now or datetime.now(UTC)).astimezone(UTC)
    start = end - timedelta(days=max(days, 1))
    records = load_issue_records(projects_root, days=days, now=end)
    issue_codes: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    projects: dict[str, dict[str, int]] = defaultdict(lambda: {"records": 0, "issue_instances": 0})

    for record in records:
        project = str(record.get("project") or "unknown")
        source = str(record.get("source") or "unknown")
        issues = record.get("issues")
        if not isinstance(issues, list):
            issues = []
        issue_count = 0
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            code = issue.get("code")
            if isinstance(code, str) and code.strip():
                issue_codes[code.strip()] += 1
                issue_count += 1
            severity = issue.get("severity")
            if isinstance(severity, str) and severity.strip():
                severities[severity.strip()] += 1
        sources[source] += 1
        projects[project]["records"] += 1
        projects[project]["issue_instances"] += issue_count

    by_project = [
        {"project": project, **stats}
        for project, stats in sorted(
            projects.items(),
            key=lambda item: (-item[1]["issue_instances"], -item[1]["records"], item[0]),
        )
    ]
    return {
        "window": {
            "days": max(days, 1),
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "totals": {
            "records": len(records),
            "issue_instances": sum(issue_codes.values()),
        },
        "top_issue_codes": [{"code": code, "count": count} for code, count in issue_codes.most_common(20)],
        "by_project": by_project,
        "by_source": [{"source": source, "records": count} for source, count in sources.most_common()],
        "by_severity": [{"severity": severity, "count": count} for severity, count in severities.most_common()],
    }


def render_markdown(report: dict[str, Any]) -> str:
    window = report.get("window") if isinstance(report.get("window"), dict) else {}
    totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
    lines = [
        "# Workbench PPT 质量问题汇总",
        "",
        f"- 时间窗口：最近 {window.get('days', DEFAULT_DAYS)} 天",
        f"- 质量记录数：{totals.get('records', 0)}",
        f"- 问题实例数：{totals.get('issue_instances', 0)}",
        "",
        "## 高频问题",
        "",
        "| 问题码 | 次数 |",
        "| --- | ---: |",
    ]
    for item in report.get("top_issue_codes") or []:
        lines.append(f"| {item.get('code', 'unknown')} | {item.get('count', 0)} |")
    if not report.get("top_issue_codes"):
        lines.append("| 暂无 | 0 |")

    lines.extend(
        [
            "",
            "## 项目分布",
            "",
            "| 项目 | 记录数 | 问题实例数 |",
            "| --- | ---: | ---: |",
        ]
    )
    for item in report.get("by_project") or []:
        lines.append(f"| {item.get('project', 'unknown')} | {item.get('records', 0)} | {item.get('issue_instances', 0)} |")
    if not report.get("by_project"):
        lines.append("| 暂无 | 0 | 0 |")

    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本报告来自各项目 `qa/quality-issues.jsonl`。",
            "- 只用于后台定期分析和改进，不改变用户下载或现有交互。",
            "- 汇总只保留问题码、次数和分布，不展示用户原始内容。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize local Workbench PPT quality issue logs.")
    parser.add_argument("--projects-root", type=Path, default=PROJECTS_ROOT)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_report(args.projects_root, days=args.days)
    markdown = render_markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
