#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_DAYS = 30
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = REPO_ROOT / "my-ppt-skill" / "projects"


def _parse_iso(ts: str) -> datetime | None:
    value = str(ts or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _in_window(ts: str, since_utc: datetime) -> bool:
    parsed = _parse_iso(ts)
    if parsed is None:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) >= since_utc


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


def _sec_stats(values_ms: list[int]) -> dict[str, Any]:
    values_sec = [ms / 1000.0 for ms in values_ms if ms is not None]
    if not values_sec:
        return {
            "count": 0,
            "avg_sec": None,
            "median_sec": None,
            "p90_sec": None,
            "min_sec": None,
            "max_sec": None,
        }
    return {
        "count": len(values_sec),
        "avg_sec": round(sum(values_sec) / len(values_sec), 2),
        "median_sec": round(statistics.median(values_sec), 2),
        "p90_sec": round(float(_percentile(values_sec, 0.9) or 0.0), 2),
        "min_sec": round(min(values_sec), 2),
        "max_sec": round(max(values_sec), 2),
    }


def _parse_json_obj(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _slide_id_from_token(token: str) -> int | None:
    raw = str(token or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    value = int(digits)
    return value if value > 0 else None


def _load_page_type_map() -> dict[tuple[str, int], str]:
    mapping: dict[tuple[str, int], str] = {}
    if not PROJECTS_ROOT.exists():
        return mapping
    for project_dir in PROJECTS_ROOT.iterdir():
        if not project_dir.is_dir():
            continue
        blueprint_path = project_dir / "blueprint.json"
        if not blueprint_path.exists():
            continue
        try:
            blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slides = blueprint.get("slides")
        if not isinstance(slides, list):
            continue
        for idx, slide in enumerate(slides, start=1):
            if not isinstance(slide, dict):
                continue
            page_type = str(slide.get("page_type") or "content").strip() or "content"
            mapping[(project_dir.name, idx)] = page_type
    return mapping


def build_report(db_path: Path, days: int) -> dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(days=max(1, int(days)))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        task_rows = conn.execute(
            """
            SELECT id, project_name, workflow_mode, status, created_at, updated_at
            FROM workbench_tasks
            ORDER BY created_at ASC
            """
        ).fetchall()
        page_rows = conn.execute(
            """
            SELECT task_id, project_name, slide_id, event_type, status, duration_ms, payload_json, created_at
            FROM workbench_page_events
            ORDER BY id ASC
            """
        ).fetchall()
        review_rows = conn.execute(
            """
            SELECT task_id, project_name, slide_id, score, usable_for_next_edit, pptx_editable, issue_tags_json, updated_at, created_at
            FROM workbench_slide_reviews
            ORDER BY updated_at ASC
            """
        ).fetchall()
    finally:
        conn.close()

    recent_tasks = [row for row in task_rows if _in_window(str(row["created_at"]), since_utc)]
    recent_task_ids = {str(row["id"]) for row in recent_tasks}
    recent_page_events = [
        row
        for row in page_rows
        if str(row["task_id"]) in recent_task_ids and _in_window(str(row["created_at"]), since_utc)
    ]
    recent_reviews = [
        row
        for row in review_rows
        if str(row["task_id"]) in recent_task_ids and _in_window(str(row["updated_at"] or row["created_at"]), since_utc)
    ]

    generation_requested = [row for row in recent_page_events if str(row["event_type"]) == "slide_generate_requested"]
    generation_completed = [row for row in recent_page_events if str(row["event_type"]) == "slide_generate_completed"]
    generation_failed = [row for row in recent_page_events if str(row["event_type"]) == "slide_generate_failed"]
    qa_completed = [row for row in recent_page_events if str(row["event_type"]) == "slide_qa_completed"]
    qa_passed = [row for row in qa_completed if str(row["status"]) == "ok"]
    repair_completed = [row for row in recent_page_events if str(row["event_type"]) == "slide_repair_completed"]
    slide_export_completed = [row for row in recent_page_events if str(row["event_type"]) == "slide_export_completed"]
    slide_export_failed = [row for row in recent_page_events if str(row["event_type"]) == "slide_export_failed"]
    deck_export_completed = [row for row in recent_page_events if str(row["event_type"]) == "deck_export_completed"]
    deck_export_failed = [row for row in recent_page_events if str(row["event_type"]) == "deck_export_failed"]

    gen_durations = [int(row["duration_ms"]) for row in generation_completed if row["duration_ms"] is not None]
    qa_durations = [int(row["duration_ms"]) for row in qa_completed if row["duration_ms"] is not None]

    repair_counts_by_slide: dict[tuple[str, int], int] = defaultdict(int)
    for row in repair_completed:
        repair_counts_by_slide[(str(row["task_id"]), int(row["slide_id"]))] += 1
    repair_rounds = list(repair_counts_by_slide.values())

    review_scores = [int(row["score"]) for row in recent_reviews if row["score"] is not None]
    editable_flags = [int(row["pptx_editable"]) for row in recent_reviews if row["pptx_editable"] is not None]

    failure_reasons: Counter[str] = Counter()
    for row in recent_page_events:
        if str(row["status"] or "").lower() not in {"error", "failed"} and "failed" not in str(row["event_type"]):
            continue
        payload = _parse_json_obj(str(row["payload_json"] or "{}"))
        reason_code = str(payload.get("reason_code") or "").strip() or "unknown"
        failure_reasons[reason_code] += 1

    page_type_map = _load_page_type_map()
    page_type_scores: dict[str, list[int]] = defaultdict(list)
    page_type_repairs: dict[str, list[int]] = defaultdict(list)
    for row in recent_reviews:
        project_name = str(row["project_name"] or "")
        slide_id = int(row["slide_id"] or 0)
        if slide_id < 1:
            continue
        page_type = page_type_map.get((project_name, slide_id), "unknown")
        if row["score"] is not None:
            page_type_scores[page_type].append(int(row["score"]))
        repair_key = (str(row["task_id"]), slide_id)
        if repair_key in repair_counts_by_slide:
            page_type_repairs[page_type].append(repair_counts_by_slide[repair_key])

    page_type_summary = []
    page_types = sorted(set(page_type_scores) | set(page_type_repairs))
    for page_type in page_types:
        scores = page_type_scores.get(page_type, [])
        repairs = page_type_repairs.get(page_type, [])
        page_type_summary.append(
            {
                "page_type": page_type,
                "score_count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
                "repair_count": len(repairs),
                "avg_repair_rounds": round(sum(repairs) / len(repairs), 3) if repairs else None,
            }
        )

    review_by_task_slide: dict[tuple[str, int], sqlite3.Row] = {}
    for row in recent_reviews:
        review_by_task_slide[(str(row["task_id"]), int(row["slide_id"]))] = row
    qa_status_by_task_slide: dict[tuple[str, int], bool] = {}
    for row in qa_completed:
        qa_status_by_task_slide[(str(row["task_id"]), int(row["slide_id"]))] = str(row["status"]) == "ok"

    requested_count = len(generation_requested)
    generation_success_rate = (
        round((len(generation_completed) / requested_count) * 100, 2) if requested_count > 0 else None
    )
    qa_pass_rate = round((len(qa_passed) / len(qa_completed)) * 100, 2) if qa_completed else None

    export_total = len(deck_export_completed) + len(deck_export_failed)
    deck_export_success_rate = round((len(deck_export_completed) / export_total) * 100, 2) if export_total else None
    slide_export_total = len(slide_export_completed) + len(slide_export_failed)
    slide_export_success_rate = (
        round((len(slide_export_completed) / slide_export_total) * 100, 2) if slide_export_total else None
    )
    pptx_editable_pass_rate = (
        round((sum(1 for flag in editable_flags if flag == 1) / len(editable_flags)) * 100, 2)
        if editable_flags
        else None
    )

    return {
        "window": {
            "days": max(1, int(days)),
            "since_utc": since_utc.isoformat(),
            "until_utc": now_utc.isoformat(),
        },
        "task_scope": {
            "tasks_recent": len(recent_tasks),
        },
        "generation": {
            "requested": requested_count,
            "completed": len(generation_completed),
            "failed": len(generation_failed),
            "success_rate_percent": generation_success_rate,
            "duration": _sec_stats(gen_durations),
        },
        "qa": {
            "completed": len(qa_completed),
            "passed": len(qa_passed),
            "pass_rate_percent": qa_pass_rate,
            "duration": _sec_stats(qa_durations),
        },
        "repair": {
            "completed_events": len(repair_completed),
            "slide_count_with_repairs": len(repair_rounds),
            "avg_rounds": round(sum(repair_rounds) / len(repair_rounds), 3) if repair_rounds else None,
            "p90_rounds": round(float(_percentile([float(x) for x in repair_rounds], 0.9) or 0.0), 3) if repair_rounds else None,
        },
        "export": {
            "slide_export_success_rate_percent": slide_export_success_rate,
            "deck_export_success_rate_percent": deck_export_success_rate,
            "slide_export_completed": len(slide_export_completed),
            "slide_export_failed": len(slide_export_failed),
            "deck_export_completed": len(deck_export_completed),
            "deck_export_failed": len(deck_export_failed),
        },
        "manual_review": {
            "review_count": len(recent_reviews),
            "avg_score": round(sum(review_scores) / len(review_scores), 3) if review_scores else None,
            "pptx_editable_pass_rate_percent": pptx_editable_pass_rate,
        },
        "failure_reason_top5": [
            {"reason_code": reason, "count": count}
            for reason, count in failure_reasons.most_common(5)
        ],
        "by_page_type": page_type_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Workbench v0.2 production-loop metrics from SQLite.")
    parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parent / "workbench.db")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = parser.parse_args()
    report = build_report(args.db, args.days)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
