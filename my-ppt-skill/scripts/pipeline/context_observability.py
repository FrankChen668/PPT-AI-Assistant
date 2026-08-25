#!/usr/bin/env python3
"""Context observability helpers for build/QA orchestration."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_stage_metrics(
    *,
    phase: str,
    stage_timing: dict[str, Any],
    build_duration_sec: float,
) -> dict[str, float]:
    """Return standardized, additive stage timing metrics for manifest/report consumers."""

    render_sec = round(max(0.0, _safe_float(stage_timing.get("render_sec", 0.0), 0.0)), 4)
    finalize_sec = round(max(0.0, _safe_float(stage_timing.get("finalize_sec", 0.0), 0.0)), 4)
    export_sec = round(max(0.0, _safe_float(stage_timing.get("export_sec", 0.0), 0.0)), 4)
    qa_sec = round(max(0.0, _safe_float(stage_timing.get("qa_sec", 0.0), 0.0)), 4)
    total_sec = round(max(0.0, _safe_float(build_duration_sec, 0.0)), 4)

    if phase != "finalize":
        finalize_sec = 0.0
        export_sec = 0.0
        qa_sec = 0.0

    parse_sec = round(max(0.0, total_sec - render_sec - finalize_sec - export_sec - qa_sec), 4)
    return {
        "stage_parse_sec": parse_sec,
        "stage_render_sec": render_sec,
        "stage_finalize_sec": finalize_sec,
        "stage_export_sec": export_sec,
        "stage_qa_sec": qa_sec,
        "stage_total_sec": total_sec,
    }


def infer_stage_failure(
    *,
    delivery_approved: bool,
    delivery_status: str,
    delivery_failure_reasons: list[str],
) -> dict[str, str]:
    """Normalize stage failure code/source for manifest/report summaries."""

    if delivery_approved:
        return {
            "stage_failure_code": "none",
            "stage_failure_source": "none",
        }

    code = "none"
    if delivery_failure_reasons:
        first = delivery_failure_reasons[0]
        code = str(first).strip() or "none"
    if code == "none":
        code = str(delivery_status or "unknown").strip() or "unknown"

    source = "unknown"
    lowered = code.lower()
    status_lowered = str(delivery_status or "").lower()
    if lowered.startswith("qa_") or lowered.startswith("qa:") or "qa" in lowered or "qa" in status_lowered:
        source = "qa"
    elif "finalize" in lowered:
        source = "finalize"
    elif "export" in lowered or "artifact" in lowered:
        source = "export"
    elif any(token in lowered for token in ("preflight", "layout_lint", "budget", "copyfit", "doctor", "style")):
        source = "parse"

    return {
        "stage_failure_code": code,
        "stage_failure_source": source,
    }


def template_lookup_metrics(project_dir: Path) -> dict[str, Any]:
    defaults = {
        "template_lookup_mode": "unknown",
        "template_reference_files_loaded": 0,
        "template_reference_files_skipped": 0,
        "template_lazy_load_hit_ratio": 0.0,
    }
    path = project_dir / "reference_pack.json"
    if not path.exists():
        return defaults
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return defaults
    if not isinstance(payload, dict):
        return defaults
    loaded_default = _safe_int(payload.get("template_reference_files_loaded", 0), 0)
    mode = payload.get("template_lookup_mode")
    return {
        "template_lookup_mode": str(mode).strip() if isinstance(mode, str) and mode.strip() else "unknown",
        "template_reference_files_loaded": loaded_default,
        "template_reference_files_skipped": _safe_int(payload.get("template_reference_files_skipped", 0), 0),
        "template_lazy_load_hit_ratio": _safe_float(
            payload.get("template_lazy_load_hit_ratio", 1.0 if loaded_default > 0 else 0.0),
            1.0 if loaded_default > 0 else 0.0,
        ),
    }


def incremental_context_profile(
    project_dir: Path,
    changed_slides: list[int] | None,
    *,
    project_relative_path_fn: Callable[[Path, Path], str],
) -> dict[str, Any]:
    files: list[Path] = [
        project_dir / "design_spec.md",
        project_dir / "blueprint.json",
    ]
    optional = [
        project_dir / "style_route.json",
        project_dir / "slide_visual_plan.json",
        project_dir / "art_direction.md",
    ]
    files.extend(path for path in optional if path.exists())
    if changed_slides:
        files.extend(
            (project_dir / "svg_output" / f"slide_{slide_id:02d}.svg") for slide_id in sorted(set(changed_slides))
        )
    total_bytes = 0
    existing_files: list[str] = []
    for path in files:
        if not path.exists() or not path.is_file():
            continue
        total_bytes += path.stat().st_size
        existing_files.append(project_relative_path_fn(project_dir, path))
    return {
        "context_file_count": len(existing_files),
        "context_bytes_estimate": total_bytes,
        "context_files": existing_files,
    }


def evaluate_token_budget(
    *,
    phase: str,
    changed_slides: list[int],
    context_profile: dict[str, Any],
    policy: str,
    caps: dict[str, int],
) -> dict[str, Any]:
    if phase == "authoring":
        stage = "executor_per_slide" if len(changed_slides) == 1 else "designer"
    else:
        stage = "checks"
    limit = int(caps.get(stage, caps["checks"]))
    estimate = max(0, int(round(int(context_profile.get("context_bytes_estimate", 0)) / 4.0)))
    overflow = max(0, estimate - limit)
    return {
        "token_budget_policy": policy,
        "token_budget_stage": stage,
        "token_budget_limit": limit,
        "context_token_estimate": estimate,
        "token_budget_overflow": overflow,
        "token_budget_warning": overflow > 0,
    }


def _page_summary_cache_path(project_dir: Path) -> Path:
    return project_dir / "exports" / "page_summary_cache.json"


def _read_page_summary_cache(project_dir: Path, *, version: int) -> dict[str, Any]:
    path = _page_summary_cache_path(project_dir)
    if not path.exists():
        return {"version": version, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": version, "entries": {}}
    if not isinstance(payload, dict):
        return {"version": version, "entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        entries = {}
    payload["version"] = version
    payload["entries"] = entries
    return payload


def _slide_plan_by_id(project_dir: Path) -> dict[int, dict[str, Any]]:
    plan_path = project_dir / "slide_visual_plan.json"
    if not plan_path.exists():
        return {}
    try:
        payload = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return {}
    by_id: dict[int, dict[str, Any]] = {}
    for item in slides:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("slide_id", item.get("id"))
        if not isinstance(raw_id, int) or raw_id <= 0:
            continue
        by_id[raw_id] = item
    return by_id


def _hash_json(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _slide_svg_hash(project_dir: Path, slide_id: int, *, sha256_file_fn: Callable[[Path], str | None]) -> str | None:
    for folder in ("svg_output", "svg_final"):
        path = project_dir / folder / f"slide_{slide_id:02d}.svg"
        digest = sha256_file_fn(path)
        if digest:
            return digest
    return None


def update_page_summary_cache(
    project_dir: Path,
    changed_slides: list[int],
    *,
    project_relative_path_fn: Callable[[Path, Path], str],
    sha256_file_fn: Callable[[Path], str | None],
    page_summary_cache_version: int,
) -> dict[str, Any]:
    blueprint_path = project_dir / "blueprint.json"
    if not blueprint_path.exists():
        return {
            "page_summary_cache_scope": "changed" if changed_slides else "all",
            "page_summary_cache_entries_updated": 0,
            "page_summary_cache_hit_count": 0,
            "page_summary_cache_miss_count": 0,
            "page_summary_cache_hit_ratio": 0.0,
        }

    try:
        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {
            "page_summary_cache_scope": "changed" if changed_slides else "all",
            "page_summary_cache_entries_updated": 0,
            "page_summary_cache_hit_count": 0,
            "page_summary_cache_miss_count": 0,
            "page_summary_cache_hit_ratio": 0.0,
        }

    slides = blueprint.get("slides") if isinstance(blueprint, dict) else None
    if not isinstance(slides, list):
        return {
            "page_summary_cache_scope": "changed" if changed_slides else "all",
            "page_summary_cache_entries_updated": 0,
            "page_summary_cache_hit_count": 0,
            "page_summary_cache_miss_count": 0,
            "page_summary_cache_hit_ratio": 0.0,
        }

    selected = set(changed_slides)
    scoped_slides: list[dict[str, Any]] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        slide_id = item.get("id")
        if not isinstance(slide_id, int) or slide_id <= 0:
            continue
        if selected and slide_id not in selected:
            continue
        scoped_slides.append(item)

    cache_payload = _read_page_summary_cache(project_dir, version=page_summary_cache_version)
    entries = cache_payload.get("entries", {})
    if not isinstance(entries, dict):
        entries = {}
    plan_by_id = _slide_plan_by_id(project_dir)

    hits = 0
    misses = 0
    now = datetime.now().isoformat(timespec="seconds")
    for slide in scoped_slides:
        slide_id = int(slide["id"])
        content = slide.get("content", {})
        narrative_intent = str(slide.get("narrative_intent", "")).strip()
        visual_intent = str(slide.get("visual_intent", "")).strip()
        plan = plan_by_id.get(slide_id, {})
        visual_decisions = {
            "visual_archetype": str(plan.get("visual_archetype", "")).strip(),
            "composition_intent": str(plan.get("composition_intent", "")).strip(),
            "variation_rule": str(plan.get("variation_rule", "")).strip(),
            "avoid": plan.get("avoid", []),
        }
        summary = {
            "slide_id": slide_id,
            "layout_tag": str(slide.get("layout_tag", "")).strip(),
            "narrative_intent": narrative_intent,
            "visual_intent": visual_intent,
            "content_hash": _hash_json(content if isinstance(content, dict) else {}),
            "visual_decisions": visual_decisions,
            "visual_decisions_hash": _hash_json(visual_decisions),
            "svg_hash": _slide_svg_hash(project_dir, slide_id, sha256_file_fn=sha256_file_fn),
            "updated_at": now,
        }
        key = str(slide_id)
        existing = entries.get(key)
        is_hit = False
        if isinstance(existing, dict):
            is_hit = (
                existing.get("content_hash") == summary["content_hash"]
                and existing.get("narrative_intent") == summary["narrative_intent"]
                and existing.get("visual_intent") == summary["visual_intent"]
                and existing.get("visual_decisions_hash") == summary["visual_decisions_hash"]
                and existing.get("svg_hash") == summary["svg_hash"]
            )
        if is_hit:
            hits += 1
            created_at = now
            if isinstance(existing, dict):
                created_at = str(existing.get("created_at", now))
            summary["created_at"] = created_at
        else:
            misses += 1
            summary["created_at"] = now
        entries[key] = summary

    cache_payload["version"] = page_summary_cache_version
    cache_payload["entries"] = entries
    cache_payload["updated_at"] = now
    cache_path = _page_summary_cache_path(project_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    updated = len(scoped_slides)
    ratio = round(hits / updated, 4) if updated > 0 else 0.0
    return {
        "page_summary_cache_path": project_relative_path_fn(project_dir, cache_path),
        "page_summary_cache_scope": "changed" if changed_slides else "all",
        "page_summary_cache_entries_updated": updated,
        "page_summary_cache_hit_count": hits,
        "page_summary_cache_miss_count": misses,
        "page_summary_cache_hit_ratio": ratio,
    }


def _session_checkpoints_path(project_dir: Path) -> Path:
    return project_dir / "exports" / "session_checkpoints.jsonl"


def _load_blueprint_slides(project_dir: Path) -> list[dict[str, Any]]:
    blueprint_path = project_dir / "blueprint.json"
    if not blueprint_path.exists():
        return []
    try:
        payload = json.loads(blueprint_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        slide_id = item.get("id")
        if not isinstance(slide_id, int) or slide_id <= 0:
            continue
        normalized.append(item)
    return sorted(normalized, key=lambda entry: int(entry.get("id", 0)))


def _extract_numbers(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except Exception:
            text = str(value)
    matches = re.findall(r"\d+(?:\.\d+)?%?", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for token in matches:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _style_route_payload(project_dir: Path) -> dict[str, Any] | None:
    path = project_dir / "style_route.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_page_range(page_range: str) -> tuple[int, int]:
    if "-" not in page_range:
        return (0, 0)
    left, right = page_range.split("-", 1)
    try:
        return (int(left), int(right))
    except ValueError:
        return (0, 0)


def _read_session_checkpoints(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        page_range = payload.get("page_range")
        if isinstance(page_range, str) and page_range:
            records[page_range] = payload
    return records


def _write_session_checkpoints(path: Path, records: dict[str, dict[str, Any]]) -> None:
    sorted_items = sorted(records.items(), key=lambda item: _parse_page_range(item[0]))
    lines = [json.dumps(value, ensure_ascii=False) for _, value in sorted_items]
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def _find_checkpoint_range_for_slide(records: dict[str, dict[str, Any]], slide_id: int) -> str | None:
    for page_range in sorted(records.keys(), key=_parse_page_range):
        start, end = _parse_page_range(page_range)
        if start <= slide_id <= end:
            return page_range
    return None


def update_session_checkpoints(
    project_dir: Path,
    *,
    changed_slides: list[int],
    token_budget_assessment: dict[str, Any],
    project_relative_path_fn: Callable[[Path, Path], str],
    page_summary_cache_version: int,
    session_checkpoint_version: int,
    pages_per_chunk_default: int,
    pages_per_chunk_min: int,
    pages_per_chunk_max: int,
) -> dict[str, Any]:
    raw = os.environ.get("PPT_SESSION_CHECKPOINT_PAGES", "").strip()
    if not raw:
        pages_per_chunk = pages_per_chunk_default
    else:
        try:
            parsed = int(raw)
        except ValueError:
            parsed = pages_per_chunk_default
        pages_per_chunk = max(pages_per_chunk_min, min(pages_per_chunk_max, parsed))

    slides = _load_blueprint_slides(project_dir)
    checkpoint_path = _session_checkpoints_path(project_dir)
    if not slides:
        return {
            "session_checkpoints_path": project_relative_path_fn(project_dir, checkpoint_path),
            "checkpoint_count": 0,
            "checkpoint_pages_per_chunk": pages_per_chunk,
            "checkpoint_bytes": 0,
            "checkpoint_last_range": None,
            "context_restore_mode": "checkpoint-plus-delta" if len(changed_slides) == 1 else "checkpoint-batch",
            "context_restore_checkpoint_range": None,
            "context_restore_delta_slides": changed_slides,
        }

    chunks: list[list[dict[str, Any]]] = []
    for idx in range(0, len(slides), pages_per_chunk):
        chunks.append(slides[idx : idx + pages_per_chunk])

    touched_chunk_indexes: set[int] = set(range(len(chunks)))
    if changed_slides:
        changed_set = set(changed_slides)
        touched_chunk_indexes = set()
        for idx, chunk in enumerate(chunks):
            chunk_ids = {int(item["id"]) for item in chunk if isinstance(item.get("id"), int)}
            if chunk_ids.intersection(changed_set):
                touched_chunk_indexes.add(idx)
        if not touched_chunk_indexes:
            touched_chunk_indexes = set(range(len(chunks)))

    cache_payload = _read_page_summary_cache(project_dir, version=page_summary_cache_version)
    entries = cache_payload.get("entries") if isinstance(cache_payload, dict) else {}
    if not isinstance(entries, dict):
        entries = {}

    style_route = _style_route_payload(project_dir)
    style_route_digest = _hash_json(style_route) if isinstance(style_route, dict) else None
    style_risks = style_route.get("risk_flags", []) if isinstance(style_route, dict) else []
    risk_flags = [str(item) for item in style_risks if isinstance(item, str) and item.strip()]

    existing = _read_session_checkpoints(checkpoint_path)
    now = datetime.now().isoformat(timespec="seconds")

    for idx in sorted(touched_chunk_indexes):
        chunk = chunks[idx]
        if not chunk:
            continue
        slide_ids = [int(item["id"]) for item in chunk if isinstance(item.get("id"), int)]
        start_id = min(slide_ids)
        end_id = max(slide_ids)
        page_range = f"{start_id}-{end_id}"

        key_claims: list[str] = []
        numbers: list[str] = []
        visual_decisions: list[dict[str, Any]] = []
        missing_summary: list[int] = []
        seen_numbers: set[str] = set()

        for slide in chunk:
            slide_id = int(slide["id"])
            title = str(slide.get("title", "")).strip()
            intent = str(slide.get("narrative_intent", "")).strip()
            if title or intent:
                claim_parts = [f"S{slide_id}"]
                if title:
                    claim_parts.append(title)
                if intent:
                    claim_parts.append(intent)
                key_claims.append(" | ".join(claim_parts))

            for token in _extract_numbers(slide.get("content", {})):
                if token in seen_numbers:
                    continue
                seen_numbers.add(token)
                numbers.append(token)

            summary = entries.get(str(slide_id))
            if not isinstance(summary, dict):
                missing_summary.append(slide_id)
                continue
            raw_visual = summary.get("visual_decisions", {})
            visual = raw_visual if isinstance(raw_visual, dict) else {}
            visual_decisions.append(
                {
                    "slide_id": slide_id,
                    "layout_tag": str(summary.get("layout_tag", "")).strip(),
                    "visual_archetype": str(visual.get("visual_archetype", "")).strip(),
                    "composition_intent": str(visual.get("composition_intent", "")).strip(),
                    "variation_rule": str(visual.get("variation_rule", "")).strip(),
                }
            )

        open_risks = list(risk_flags)
        if bool(token_budget_assessment.get("token_budget_warning")):
            overflow = int(token_budget_assessment.get("token_budget_overflow", 0))
            open_risks.append(f"token_budget_overflow:{overflow}")
        if missing_summary:
            joined = ",".join(str(item) for item in missing_summary)
            open_risks.append(f"missing_page_summary:{joined}")

        next_slides: list[int] = []
        if idx + 1 < len(chunks):
            for item in chunks[idx + 1][:2]:
                next_slide_id = item.get("id")
                if isinstance(next_slide_id, int):
                    next_slides.append(next_slide_id)

        focus_slides = changed_slides if changed_slides else slide_ids
        record = {
            "version": session_checkpoint_version,
            "generated_at": now,
            "page_range": page_range,
            "key_claims": key_claims[:12],
            "numbers": numbers[:24],
            "visual_decisions": visual_decisions,
            "style_route_digest": style_route_digest,
            "open_risks": open_risks,
            "next_page_context_minset": {
                "focus_slides": focus_slides,
                "required_files": ["design_spec.md", "blueprint.json", "style_route.json", "slide_visual_plan.json"],
                "next_hint_slides": next_slides,
                "context_strategy": "checkpoint-plus-delta" if len(changed_slides) == 1 else "checkpoint-batch",
            },
        }
        existing[page_range] = record

    _write_session_checkpoints(checkpoint_path, existing)

    sorted_ranges = sorted(existing.keys(), key=_parse_page_range)
    last_range = sorted_ranges[-1] if sorted_ranges else None
    matched_range: str | None = None
    if len(changed_slides) == 1:
        matched_range = _find_checkpoint_range_for_slide(existing, changed_slides[0])

    return {
        "session_checkpoints_path": project_relative_path_fn(project_dir, checkpoint_path),
        "checkpoint_count": len(existing),
        "checkpoint_pages_per_chunk": pages_per_chunk,
        "checkpoint_bytes": checkpoint_path.stat().st_size if checkpoint_path.exists() else 0,
        "checkpoint_last_range": last_range,
        "context_restore_mode": "checkpoint-plus-delta" if len(changed_slides) == 1 else "checkpoint-batch",
        "context_restore_checkpoint_range": matched_range or last_range,
        "context_restore_delta_slides": changed_slides,
    }
