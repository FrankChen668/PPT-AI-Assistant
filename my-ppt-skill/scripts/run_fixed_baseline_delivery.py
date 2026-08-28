#!/usr/bin/env python3
"""One-command fixed-baseline delivery runner with evidence artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed baseline and emit timestamped JSON/MD plus execution note."
    )
    parser.add_argument("--tag", default="baseline-v5", help="Artifact tag prefix (default: baseline-v5).")
    parser.add_argument("--mode", choices=("dev-fast", "release-safe", "both"), default="both")
    parser.add_argument("--slide", type=int, default=1, help="Slide id for dev-fast mode (default: 1).")
    parser.add_argument(
        "--set",
        dest="set_path",
        default="docs/reports/fixed-baseline-set.json",
        help="Path to baseline set JSON (repo-root relative by default).",
    )
    parser.add_argument(
        "--output-dir",
        default="docs/reports",
        help="Output directory for artifacts (repo-root relative by default).",
    )
    parser.add_argument(
        "--trend-json",
        default="docs/reports/fixed-baseline-trend.json",
        help="Trend ledger JSON path (repo-root relative by default).",
    )
    parser.add_argument(
        "--trend-md",
        default="docs/reports/fixed-baseline-trend.md",
        help="Trend summary markdown path (repo-root relative by default).",
    )
    parser.add_argument(
        "--trend-limit",
        type=int,
        default=30,
        help="Show this many latest entries in trend markdown (default: 30).",
    )
    parser.add_argument(
        "--min-positive-delivery-rate",
        type=float,
        default=80.0,
        help="Threshold for positive delivery pass rate (default: 80).",
    )
    parser.add_argument(
        "--min-negative-detection-rate",
        type=float,
        default=100.0,
        help="Threshold for negative guardrail detection rate (default: 100).",
    )
    parser.add_argument(
        "--max-unexpected-pass",
        type=int,
        default=0,
        help="Threshold for unexpected pass count (default: 0).",
    )
    parser.add_argument(
        "--max-unexpected-fail",
        type=int,
        default=0,
        help="Threshold for unexpected fail count (default: 0).",
    )
    parser.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="Exit non-zero when threshold checks fail.",
    )
    return parser.parse_args(argv)


def _repo_root() -> Path:
    # .../my-ppt-skill/scripts -> repo root
    return Path(__file__).resolve().parents[2]


def _timestamp() -> str:
    # Include microseconds to avoid artifact filename collisions in fast repeated runs.
    return datetime.now().strftime("%Y-%m-%d-%H%M%S-%f")


def _resolve_from_repo(repo_root: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (repo_root / path).resolve()


def build_paths(repo_root: Path, *, output_dir: str, tag: str, stamp: str) -> tuple[Path, Path, Path]:
    base_dir = _resolve_from_repo(repo_root, output_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    output_json = base_dir / f"{tag}-{stamp}.results.json"
    output_md = base_dir / f"{tag}-{stamp}.summary.md"
    output_note = base_dir / f"{tag}-{stamp}.delivery-note.md"
    return output_json, output_md, output_note


def build_command(
    *,
    py: str,
    set_path: Path,
    output_json: Path,
    output_md: Path,
    mode: str,
    slide: int,
) -> list[str]:
    return [
        py,
        "my-ppt-skill/scripts/run_fixed_baseline.py",
        "--set",
        str(set_path),
        "--output-json",
        str(output_json),
        "--output-md",
        str(output_md),
        "--mode",
        mode,
        "--slide",
        str(max(1, int(slide))),
    ]


def load_result_payload(output_json: Path) -> dict[str, Any]:
    if not output_json.exists():
        return {}
    try:
        payload = json.loads(output_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _safe_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def evaluate_thresholds(
    payload: dict[str, Any],
    *,
    min_positive_delivery_rate: float,
    min_negative_detection_rate: float,
    max_unexpected_pass: int,
    max_unexpected_fail: int,
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        return {"status": "unavailable", "checks": [], "violations": ["missing summary payload"]}

    positive = summary.get("positive_delivery_pass_rate")
    negative = summary.get("negative_guardrail_detection_rate")
    expected = summary.get("expected")
    checks: list[dict[str, Any]] = []

    positive_rate = _safe_float((positive or {}).get("pass_rate_percent")) if isinstance(positive, dict) else 0.0
    checks.append(
        {
            "name": "positive_delivery_pass_rate",
            "actual": positive_rate,
            "rule": f">= {round(float(min_positive_delivery_rate), 2)}",
            "ok": positive_rate >= float(min_positive_delivery_rate),
        }
    )

    negative_rate = (
        _safe_float((negative or {}).get("detection_rate_percent")) if isinstance(negative, dict) else 0.0
    )
    checks.append(
        {
            "name": "negative_guardrail_detection_rate",
            "actual": negative_rate,
            "rule": f">= {round(float(min_negative_detection_rate), 2)}",
            "ok": negative_rate >= float(min_negative_detection_rate),
        }
    )

    unexpected_pass = _safe_int((expected or {}).get("unexpected_pass")) if isinstance(expected, dict) else 0
    checks.append(
        {
            "name": "unexpected_pass",
            "actual": unexpected_pass,
            "rule": f"<= {int(max_unexpected_pass)}",
            "ok": unexpected_pass <= int(max_unexpected_pass),
        }
    )

    unexpected_fail = _safe_int((expected or {}).get("unexpected_fail")) if isinstance(expected, dict) else 0
    checks.append(
        {
            "name": "unexpected_fail",
            "actual": unexpected_fail,
            "rule": f"<= {int(max_unexpected_fail)}",
            "ok": unexpected_fail <= int(max_unexpected_fail),
        }
    )

    violations = [f"{item['name']}: actual={item['actual']} rule={item['rule']}" for item in checks if not item["ok"]]
    return {
        "status": "pass" if not violations else "fail",
        "checks": checks,
        "violations": violations,
    }


def build_trend_entry(
    payload: dict[str, Any],
    *,
    tag: str,
    mode: str,
    slide: int,
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    by_mode = summary.get("by_mode") if isinstance(summary, dict) else {}
    expected = summary.get("expected") if isinstance(summary, dict) else {}
    positive = summary.get("positive_delivery_pass_rate") if isinstance(summary, dict) else {}
    negative = summary.get("negative_guardrail_detection_rate") if isinstance(summary, dict) else {}
    dev_fast = by_mode.get("dev-fast") if isinstance(by_mode, dict) else {}
    release_safe = by_mode.get("release-safe") if isinstance(by_mode, dict) else {}
    return {
        "generated_at": str(payload.get("generated_at") or datetime.now().isoformat(timespec="seconds")),
        "tag": tag,
        "set_name": str(payload.get("set_name") or ""),
        "mode": mode,
        "slide": max(1, int(slide)),
        "total_runs": _safe_int(summary.get("total_runs")) if isinstance(summary, dict) else 0,
        "dev_fast_pass_rate_percent": _safe_float((dev_fast or {}).get("pass_rate_percent")),
        "release_safe_pass_rate_percent": _safe_float((release_safe or {}).get("pass_rate_percent")),
        "positive_delivery_pass_rate_percent": _safe_float((positive or {}).get("pass_rate_percent")),
        "negative_guardrail_detection_rate_percent": _safe_float((negative or {}).get("detection_rate_percent")),
        "unexpected_pass": _safe_int((expected or {}).get("unexpected_pass")),
        "unexpected_fail": _safe_int((expected or {}).get("unexpected_fail")),
        "threshold_status": str(thresholds.get("status") or "unavailable"),
        "threshold_violations": list(thresholds.get("violations") or []),
    }


def append_trend_entry(trend_json_path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if trend_json_path.exists():
        try:
            candidate = json.loads(trend_json_path.read_text(encoding="utf-8-sig"))
            if isinstance(candidate, dict):
                existing = candidate
        except (OSError, json.JSONDecodeError):
            existing = {}
    entries = existing.get("entries")
    if not isinstance(entries, list):
        entries = []
    entries.append(entry)
    updated = {"updated_at": datetime.now().isoformat(timespec="seconds"), "entries": entries}
    trend_json_path.parent.mkdir(parents=True, exist_ok=True)
    trend_json_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return updated


def build_trend_markdown(ledger: dict[str, Any], *, limit: int) -> str:
    entries = ledger.get("entries")
    rows = entries if isinstance(entries, list) else []
    recent = rows[-max(1, int(limit)) :]
    lines = [
        f"# Fixed Baseline Trend ({datetime.now().strftime('%Y-%m-%d')})",
        "",
        f"- Updated at: `{ledger.get('updated_at', '')}`",
        f"- Total entries: `{len(rows)}`",
        f"- Showing latest: `{len(recent)}`",
        "",
        (
            "| Generated At | Tag | Mode | Positive Delivery % | Guardrail Detection % | "
            "Unexpected Pass | Unexpected Fail | Threshold Status |"
        ),
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for item in reversed(recent):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("generated_at", "")),
                    f"`{item.get('tag', '')}`",
                    f"`{item.get('mode', '')}`",
                    str(item.get("positive_delivery_pass_rate_percent", 0.0)),
                    str(item.get("negative_guardrail_detection_rate_percent", 0.0)),
                    str(item.get("unexpected_pass", 0)),
                    str(item.get("unexpected_fail", 0)),
                    f"`{item.get('threshold_status', 'unavailable')}`",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `threshold_status=fail` means at least one threshold rule was violated.",
            "- Always combine this trend with per-run JSON/MD for root-cause diagnosis.",
            "",
        ]
    )
    return "\n".join(lines)


def write_trend_markdown(trend_md_path: Path, *, ledger: dict[str, Any], limit: int) -> None:
    trend_md_path.parent.mkdir(parents=True, exist_ok=True)
    trend_md_path.write_text(build_trend_markdown(ledger, limit=limit), encoding="utf-8")


def write_note(
    note_path: Path,
    *,
    command: list[str],
    output_json: Path,
    output_md: Path,
    trend_json: Path,
    trend_md: Path,
    mode: str,
    slide: int,
    returncode: int,
    metric_snapshot: dict[str, str] | None = None,
    threshold_result: dict[str, Any] | None = None,
) -> None:
    snapshot = metric_snapshot or {}
    threshold = threshold_result or {"status": "unavailable", "violations": []}
    lines = [
        f"# Fixed Baseline Delivery Note ({datetime.now().strftime('%Y-%m-%d')})",
        "",
        "## Command",
        "",
        "```text",
        " ".join(command),
        "```",
        "",
        "## Run Parameters",
        "",
        f"- mode: `{mode}`",
        f"- dev-fast slide: `{max(1, int(slide))}`",
        f"- returncode: `{returncode}`",
        "",
        "## Artifacts",
        "",
        f"- json: `{output_json}`",
        f"- summary: `{output_md}`",
        f"- trend json: `{trend_json}`",
        f"- trend summary: `{trend_md}`",
        "",
        "## Metric Snapshot",
        "",
        f"- positive_delivery_pass_rate: `{snapshot.get('positive_delivery_pass_rate', 'n/a')}`",
        f"- negative_guardrail_detection_rate: `{snapshot.get('negative_guardrail_detection_rate', 'n/a')}`",
        f"- unexpected_pass: `{snapshot.get('unexpected_pass', 'n/a')}`",
        f"- unexpected_fail: `{snapshot.get('unexpected_fail', 'n/a')}`",
        "",
        "## Threshold Check",
        "",
        f"- status: `{threshold.get('status', 'unavailable')}`",
    ]
    for issue in list(threshold.get("violations") or []):
        lines.append(f"- violation: `{issue}`")
    lines.extend(
        [
            "",
        "## Required Follow-up",
        "",
        "Report these together:",
        "1. `positive_delivery_pass_rate`",
        "2. `negative_guardrail_detection_rate`",
        "3. `unexpected_pass`",
        "4. `unexpected_fail`",
        "",
        ]
    )
    note_path.write_text("\n".join(lines), encoding="utf-8")


def load_metric_snapshot(output_json: Path) -> dict[str, str]:
    if not output_json.exists():
        return {}
    try:
        payload = json.loads(output_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}

    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        return {}

    positive = summary.get("positive_delivery_pass_rate")
    negative = summary.get("negative_guardrail_detection_rate")
    expected = summary.get("expected")
    if not isinstance(positive, dict) or not isinstance(negative, dict) or not isinstance(expected, dict):
        return {}

    return {
        "positive_delivery_pass_rate": (
            f"{positive.get('passed', 0)}/{positive.get('total', 0)} "
            f"({positive.get('pass_rate_percent', 0.0)}%)"
        ),
        "negative_guardrail_detection_rate": (
            f"{negative.get('detected', 0)}/{negative.get('total', 0)} "
            f"({negative.get('detection_rate_percent', 0.0)}%)"
        ),
        "unexpected_pass": str(expected.get("unexpected_pass", "n/a")),
        "unexpected_fail": str(expected.get("unexpected_fail", "n/a")),
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = _repo_root()
    set_path = _resolve_from_repo(repo_root, args.set_path)
    trend_json = _resolve_from_repo(repo_root, args.trend_json)
    trend_md = _resolve_from_repo(repo_root, args.trend_md)
    if not set_path.exists():
        print(f"error: baseline set not found: {set_path}")
        return 2

    stamp = _timestamp()
    tag = str(args.tag).strip() or "baseline-v5"
    output_json, output_md, output_note = build_paths(
        repo_root,
        output_dir=args.output_dir,
        tag=tag,
        stamp=stamp,
    )
    command = build_command(
        py=sys.executable,
        set_path=set_path,
        output_json=output_json,
        output_md=output_md,
        mode=args.mode,
        slide=args.slide,
    )

    completed = subprocess.run(command, cwd=repo_root)
    payload = load_result_payload(output_json)
    metric_snapshot = load_metric_snapshot(output_json)
    threshold_result = evaluate_thresholds(
        payload,
        min_positive_delivery_rate=float(args.min_positive_delivery_rate),
        min_negative_detection_rate=float(args.min_negative_detection_rate),
        max_unexpected_pass=int(args.max_unexpected_pass),
        max_unexpected_fail=int(args.max_unexpected_fail),
    )
    trend_entry = build_trend_entry(
        payload,
        tag=tag,
        mode=args.mode,
        slide=args.slide,
        thresholds=threshold_result,
    )
    ledger = append_trend_entry(trend_json, trend_entry)
    write_trend_markdown(trend_md, ledger=ledger, limit=max(1, int(args.trend_limit)))

    write_note(
        output_note,
        command=command,
        output_json=output_json,
        output_md=output_md,
        trend_json=trend_json,
        trend_md=trend_md,
        mode=args.mode,
        slide=args.slide,
        returncode=completed.returncode,
        metric_snapshot=metric_snapshot,
        threshold_result=threshold_result,
    )

    print(f"wrote note: {output_note}")
    print(f"json: {output_json}")
    print(f"summary: {output_md}")
    print(f"trend json: {trend_json}")
    print(f"trend markdown: {trend_md}")
    print(f"threshold status: {threshold_result.get('status', 'unavailable')}")
    if completed.returncode != 0:
        return completed.returncode
    if bool(args.enforce_thresholds) and threshold_result.get("status") == "fail":
        print("error: threshold check failed and --enforce-thresholds is enabled.")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
