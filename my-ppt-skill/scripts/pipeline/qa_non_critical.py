#!/usr/bin/env python3
"""Non-critical QA tasks orchestration."""

from __future__ import annotations

import concurrent.futures
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


def run_snapshot_and_visual_checks(
    *,
    snapshots: bool,
    enable_visual_qa: bool,
    svg_dir: Path,
    qa_dir: Path,
    project_dir: Path,
    slide_id: int | None,
    profile: str,
    canvas: Any,
    visual_metrics_default: Any,
    render_snapshots_fn: Callable[..., dict[str, Any]],
    validate_visual_quality_fn: Callable[..., Any],
) -> tuple[dict[str, Any], Any, list[Any], list[Any]]:
    """Run snapshot rendering and visual QA, parallelizing when both are enabled."""
    visual_metrics = visual_metrics_default
    snapshot_metrics: dict[str, Any] = {}
    snapshot_findings: list[Any] = []
    visual_findings_buffer: list[Any] = []

    def _timed(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, float]:
        started = perf_counter()
        result = fn(*args, **kwargs)
        return result, round(perf_counter() - started, 4)

    if snapshots and enable_visual_qa:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            snapshot_future = executor.submit(
                _timed,
                render_snapshots_fn,
                svg_dir,
                qa_dir,
                snapshot_findings,
                slide_id=slide_id,
            )
            visual_future = executor.submit(
                _timed,
                validate_visual_quality_fn,
                project_dir,
                svg_dir,
                visual_findings_buffer,
                slide_id=slide_id,
                profile=profile,
                canvas=canvas,
            )
            snapshot_metrics, snapshot_sec = snapshot_future.result()
            visual_metrics, visual_sec = visual_future.result()
            snapshot_metrics["snapshot_render_sec"] = snapshot_sec
            if isinstance(visual_metrics, dict):
                visual_metrics["visual_qa_sec"] = visual_sec
    else:
        if snapshots:
            snapshot_metrics, snapshot_sec = _timed(
                render_snapshots_fn,
                svg_dir,
                qa_dir,
                snapshot_findings,
                slide_id=slide_id,
            )
            snapshot_metrics["snapshot_render_sec"] = snapshot_sec
        if enable_visual_qa:
            visual_metrics, visual_sec = _timed(
                validate_visual_quality_fn,
                project_dir,
                svg_dir,
                visual_findings_buffer,
                slide_id=slide_id,
                profile=profile,
                canvas=canvas,
            )
            if isinstance(visual_metrics, dict):
                visual_metrics["visual_qa_sec"] = visual_sec

    return snapshot_metrics, visual_metrics, snapshot_findings, visual_findings_buffer
