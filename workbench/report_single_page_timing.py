#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_DAYS = 30


@dataclass(frozen=True)
class Stats:
    count: int
    avg_sec: float | None
    median_sec: float | None
    p90_sec: float | None
    min_sec: float | None
    max_sec: float | None


def _parse_iso(ts: str) -> datetime | None:
    value = str(ts or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _stats_from_ms(values_ms: list[int]) -> Stats:
    values_sec = [ms / 1000.0 for ms in values_ms]
    if not values_sec:
        return Stats(0, None, None, None, None, None)
    return Stats(
        count=len(values_sec),
        avg_sec=round(sum(values_sec) / len(values_sec), 2),
        median_sec=round(statistics.median(values_sec), 2),
        p90_sec=round(float(_percentile(values_sec, 0.9) or 0.0), 2),
        min_sec=round(min(values_sec), 2),
        max_sec=round(max(values_sec), 2),
    )


def _in_window(ts: str, since_utc: datetime) -> bool:
    parsed = _parse_iso(ts)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) >= since_utc


def _dict_stats(stats: Stats) -> dict[str, Any]:
    return {
        "count": stats.count,
        "avg_sec": stats.avg_sec,
        "median_sec": stats.median_sec,
        "p90_sec": stats.p90_sec,
        "min_sec": stats.min_sec,
        "max_sec": stats.max_sec,
    }


def build_report(db_path: Path, days: int) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(days=days)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        task_rows = conn.execute(
            """
            SELECT id, project_name, workflow_mode, created_at, updated_at, status
            FROM workbench_tasks
            WHERE workflow_mode = 'single_page'
            ORDER BY created_at ASC
            """
        ).fetchall()

        recent_tasks = [row for row in task_rows if _in_window(str(row["created_at"]), since_utc)]
        recent_task_ids = {str(row["id"]) for row in recent_tasks}

        page_rows = conn.execute(
            """
            SELECT task_id, project_name, slide_id, event_type, started_at, ended_at, duration_ms, created_at
            FROM workbench_page_events
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    scoped_events = [
        row
        for row in page_rows
        if str(row["task_id"]) in recent_task_ids and _in_window(str(row["created_at"]), since_utc)
    ]

    generation_requested = [row for row in scoped_events if str(row["event_type"]) == "slide_generate_requested"]
    generation_completed = [
        row
        for row in scoped_events
        if str(row["event_type"]) == "slide_generate_completed" and row["duration_ms"] is not None
    ]
    generation_failed = [row for row in scoped_events if str(row["event_type"]) == "slide_generate_failed"]
    qa_completed = [
        row
        for row in scoped_events
        if str(row["event_type"]) == "slide_qa_completed" and row["duration_ms"] is not None
    ]

    gen_stats = _stats_from_ms([int(row["duration_ms"]) for row in generation_completed])
    qa_stats = _stats_from_ms([int(row["duration_ms"]) for row in qa_completed])
    task_ids_with_events = {str(row["task_id"]) for row in scoped_events}
    task_with_events = len(task_ids_with_events)
    task_without_events = max(0, len(recent_task_ids) - task_with_events)
    no_telemetry_projects: list[str] = []
    for row in recent_tasks:
        task_id = str(row["id"])
        if task_id in task_ids_with_events:
            continue
        project_name = str(row["project_name"] or "").strip()
        no_telemetry_projects.append(project_name or task_id)
    no_telemetry_projects = sorted(set(no_telemetry_projects))

    by_day: dict[str, list[int]] = {}
    for row in generation_completed:
        created = _parse_iso(str(row["created_at"]))
        if created is None:
            continue
        day = created.astimezone().strftime("%Y-%m-%d")
        by_day.setdefault(day, []).append(int(row["duration_ms"]))

    daily = []
    for day in sorted(by_day):
        stats = _stats_from_ms(by_day[day])
        daily.append(
            {
                "day": day,
                "count": stats.count,
                "avg_sec": stats.avg_sec,
                "p90_sec": stats.p90_sec,
            }
        )

    success_rate = None
    if generation_requested:
        success_rate = round((len(generation_completed) / len(generation_requested)) * 100, 2)

    return {
        "window": {
            "days": days,
            "since_utc": since_utc.isoformat(),
            "until_utc": now_utc.isoformat(),
        },
        "task_scope": {
            "single_page_tasks_recent": len(recent_tasks),
            "tasks_with_page_event_telemetry": task_with_events,
            "tasks_without_page_event_telemetry": task_without_events,
            "task_projects_without_page_event_telemetry": no_telemetry_projects,
        },
        "generation": {
            "requested": len(generation_requested),
            "completed": len(generation_completed),
            "failed": len(generation_failed),
            "success_rate_percent": success_rate,
            "duration": _dict_stats(gen_stats),
        },
        "qa": {
            "completed": len(qa_completed),
            "duration": _dict_stats(qa_stats),
        },
        "daily_generation": daily,
        "metric_definition": {
            "single_page_generation_time": "workbench_page_events.event_type = slide_generate_completed, duration_ms",
            "single_page_qa_time": "workbench_page_events.event_type = slide_qa_completed, duration_ms",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report recent single-page workbench generation timing metrics.")
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parent / "workbench.db")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = parser.parse_args()

    report = build_report(args.db, max(1, args.days))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
