#!/usr/bin/env python3
"""Convenience runner for fast iteration and release-safe builds."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from generate_executor_packet import generate_executor_packet
from pipeline.style_draft_gate import validate_style_draft_selection

DEFAULT_LAYOUT_EXPLORATION = {
    "enabled": True,
    "candidate_count": 2,
    "anti_repeat_window": 1,
    "enforce_in_modes": ["release-safe", "premium"],
}


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode


def _project_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def _missing_release_safe_artifacts(project_dir: Path) -> list[str]:
    required = ["art_direction.md", "reference_pack.json", "slide_visual_plan.json", "style_route.json"]
    missing = [name for name in required if not (project_dir / name).exists()]
    return missing


def _load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resolve_layout_exploration_enabled(mode: str, requested: str) -> bool:
    normalized = requested.strip().lower()
    if normalized == "on":
        return True
    if normalized == "off":
        return False
    return mode in {"release-safe", "premium"}


def _inject_layout_exploration_defaults(project_dir: Path, *, enabled: bool) -> None:
    style_route_path = project_dir / "style_route.json"
    if style_route_path.exists():
        try:
            route_payload = _load_json(style_route_path)
        except Exception:
            route_payload = {}
        if isinstance(route_payload, dict):
            block = route_payload.get("layout_exploration")
            merged = dict(DEFAULT_LAYOUT_EXPLORATION)
            if isinstance(block, dict):
                merged.update(block)
            merged["enabled"] = bool(enabled)
            merged["candidate_count"] = 2
            route_payload["layout_exploration"] = merged
            _write_json(style_route_path, route_payload)

    plan_path = project_dir / "slide_visual_plan.json"
    if plan_path.exists():
        try:
            plan_payload = _load_json(plan_path)
        except Exception:
            plan_payload = {}
        if isinstance(plan_payload, dict):
            block = plan_payload.get("layout_exploration")
            merged = dict(DEFAULT_LAYOUT_EXPLORATION)
            if isinstance(block, dict):
                merged.update(block)
            merged["enabled"] = bool(enabled)
            merged["candidate_count"] = 2
            plan_payload["layout_exploration"] = merged
            _write_json(plan_path, plan_payload)


def _missing_premium_artifacts(project_dir: Path) -> list[str]:
    return _missing_release_safe_artifacts(project_dir)


def _resolve_quality_profile(mode: str, project_dir: Path, requested: str) -> str:
    normalized = requested.strip().lower()
    if normalized and normalized != "auto":
        return normalized
    if mode == "dev-fast":
        return "presentation"
    style_route_path = project_dir / "style_route.json"
    if style_route_path.exists():
        try:
            route_payload = _load_json(style_route_path)
        except Exception:
            route_payload = {}
        style_profile = str(route_payload.get("style_profile") or "").lower()
        if any(token in style_profile for token in ("proposal", "consult", "strategy", "tender", "bid")):
            return "proposal_consulting"
    name = project_dir.name.lower()
    if any(token in name for token in ("proposal", "consult", "strategy", "tender", "bid", "rfp")):
        return "proposal_consulting"
    return "proposal_consulting"


def _write_dev_fast_slo_report(
    project_dir: Path,
    *,
    elapsed_sec: float,
    threshold_sec: float,
    exceeded: bool,
    slide: int | None,
) -> Path:
    qa_dir = project_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    report_path = qa_dir / "dev-fast-last-run.json"
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project": str(project_dir),
        "mode": "dev-fast",
        "slide": slide,
        "elapsed_sec": round(elapsed_sec, 4),
        "slo_threshold_sec": round(threshold_sec, 4),
        "slo_exceeded": exceeded,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run public pipeline modes: dev-fast, release-safe, premium.")
    parser.add_argument("mode", choices=["dev-fast", "release-safe", "premium"])
    parser.add_argument(
        "project_dir",
        help="Project path, usually projects/<project_name> from my-ppt-skill/.",
    )
    parser.add_argument(
        "--slide",
        type=int,
        help="Single-slide QA check in dev-fast mode.",
    )
    parser.add_argument(
        "--snapshots",
        action="store_true",
        help="Enable snapshots (dev-fast: off by default for speed; release-safe/premium: optional).",
    )
    parser.add_argument(
        "--no-snapshots",
        action="store_true",
        help="Disable snapshots even in release-safe/premium modes (faster, less visual review surface).",
    )
    parser.add_argument(
        "--ab-profiles",
        default="",
        help="Optional comma-separated style profiles for A/B style-lab comparison (release-safe/premium only).",
    )
    parser.add_argument(
        "--ab-out-root",
        default="",
        help="Optional output root for A/B style-lab reports.",
    )
    parser.add_argument(
        "--profile",
        choices=("auto", "presentation", "print_a4", "proposal_consulting"),
        default="auto",
        help="Governance profile. auto => dev-fast uses presentation; release-safe/premium uses proposal_consulting.",
    )
    parser.add_argument(
        "--slo-seconds",
        type=float,
        default=5.0,
        help="Target SLO for dev-fast end-to-end runtime.",
    )
    parser.add_argument(
        "--enforce-slo",
        action="store_true",
        help="Fail dev-fast when elapsed time exceeds --slo-seconds.",
    )
    parser.add_argument(
        "--layout-exploration",
        choices=("auto", "on", "off"),
        default="auto",
        help="Inject layout exploration defaults (auto: on for release-safe/premium, off for dev-fast).",
    )
    parser.add_argument(
        "--executor-packet",
        choices=("auto", "off", "only"),
        default="auto",
        help="For dev-fast --slide: auto writes an Executor packet, off skips it, only writes packet and exits.",
    )
    args = parser.parse_args(argv)

    project_dir = _project_path(args.project_dir)
    if not project_dir.exists():
        print(f"error: project_dir not found: {project_dir}")
        return 2

    if args.mode in {"release-safe", "premium"} and not args.snapshots and not args.no_snapshots:
        args.snapshots = True

    py = sys.executable
    layout_exploration_enabled = _resolve_layout_exploration_enabled(args.mode, args.layout_exploration)
    _inject_layout_exploration_defaults(project_dir, enabled=layout_exploration_enabled)

    if args.mode == "dev-fast":
        if args.ab_profiles.strip():
            print("error: --ab-profiles is only supported in release-safe/premium modes.")
            return 2
        if args.executor_packet == "only" and args.slide is None:
            print("error: --executor-packet only requires --slide.")
            return 2
        if args.slide is not None and args.executor_packet in {"auto", "only"}:
            packet_path = generate_executor_packet(
                project_dir,
                slide_id=int(args.slide),
                write_markdown=args.executor_packet == "only",
            )
            print(f"executor packet: {packet_path}")
            if args.executor_packet == "only":
                return 0
        selected_profile = _resolve_quality_profile(args.mode, project_dir, args.profile)
        started = perf_counter()
        build_cmd = [
            py,
            "scripts/build_project.py",
            str(project_dir),
            "--phase",
            "authoring",
            "--skip-render",
            "--enable-layout-lint",
            "--safe-area-profile",
            "presentation",
            "--profile",
            selected_profile,
            "--incremental",
        ]
        if args.slide is not None:
            build_cmd += ["--changed-slide", str(args.slide)]
        code = _run(build_cmd)
        if code != 0:
            return code

        qa_cmd = [
            py,
            "scripts/qa_project.py",
            str(project_dir),
            "--svg-dir",
            "svg_output",
            "--safe-area-profile",
            "presentation",
            "--profile",
            selected_profile,
            "--quality-mode",
            "dev-fast",
        ]
        if args.slide is not None:
            qa_cmd += ["--slide", str(args.slide)]
        if args.snapshots and not args.no_snapshots:
            qa_cmd.append("--snapshots")
        code = _run(qa_cmd)
        elapsed = perf_counter() - started
        exceeded = elapsed > max(0.0, float(args.slo_seconds))
        report_path = _write_dev_fast_slo_report(
            project_dir,
            elapsed_sec=elapsed,
            threshold_sec=max(0.0, float(args.slo_seconds)),
            exceeded=exceeded,
            slide=args.slide,
        )
        if exceeded:
            print(
                "warning: dev-fast runtime exceeded SLO "
                f"({elapsed:.2f}s > {float(args.slo_seconds):.2f}s). report: {report_path}"
            )
            if args.enforce_slo:
                return 1
        return code

    selected_profile = _resolve_quality_profile(args.mode, project_dir, args.profile)
    release_cmd = [
        py,
        "scripts/build_project.py",
        str(project_dir),
        "--phase",
        "finalize",
        "--skip-render",
        "--auto-slide-plan",
        "--auto-slide-plan-overwrite",
        "--enable-layout-lint",
        "--safe-area-profile",
        "presentation",
        "--enable-visual-qa",
        "--strict",
        "--quality-mode",
        "premium" if args.mode == "premium" else "release-safe",
        "--profile",
        selected_profile,
        "--incremental",
    ]
    if args.slide is not None:
        release_cmd += ["--changed-slide", str(args.slide)]
    if args.snapshots and not args.no_snapshots:
        release_cmd.append("--snapshots")
    missing = (
        _missing_premium_artifacts(project_dir)
        if args.mode == "premium"
        else _missing_release_safe_artifacts(project_dir)
    )
    if missing:
        print(f"error: {args.mode} requires required Art Direction artifacts before finalize build.")
        for name in missing:
            print(f"- missing: {project_dir / name}")
        return 1

    style_gate_issues = validate_style_draft_selection(project_dir)
    if style_gate_issues:
        print(f"error: {args.mode} mode requires style-drafts/style-route strategy to be valid before finalize.")
        for issue in style_gate_issues:
            print(f"- {issue}")
        return 1

    raw_ab_profiles = args.ab_profiles.strip()
    profiles: list[str] = []
    if raw_ab_profiles:
        profiles = [item.strip() for item in raw_ab_profiles.split(",") if item.strip()]
        if len(profiles) < 2:
            print("error: --ab-profiles requires at least two profiles.")
            return 2

    code = _run(release_cmd)
    if code != 0:
        return code

    if not profiles:
        return 0

    ab_cmd = [
        py,
        "scripts/run_style_lab.py",
        str(project_dir),
        "--profiles",
        ",".join(profiles),
        "--quality-mode",
        "premium" if args.mode == "premium" else "release-safe",
    ]
    if args.ab_out_root.strip():
        ab_cmd += ["--out-root", args.ab_out_root.strip()]
    return _run(ab_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
