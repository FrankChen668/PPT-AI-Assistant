#!/usr/bin/env python3
"""Check consistency between template_binding and art-direction artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ConsistencyFinding:
    severity: str
    code: str
    path: str
    message: str


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not parse JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "Expected JSON object."
    return payload, None


def _collect_reference_pack_template_ids(payload: dict[str, Any]) -> set[str]:
    template_ids: set[str] = set()
    for key in ("primary_template", "selected_template"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            template_ids.add(value.strip())
    secondary = payload.get("secondary_templates")
    if isinstance(secondary, list):
        for item in secondary:
            if isinstance(item, str) and item.strip():
                template_ids.add(item.strip())
    selected = payload.get("selected_templates")
    if isinstance(selected, list):
        for item in selected:
            if not isinstance(item, dict):
                continue
            for key in ("template_key", "template_id", "layout_id"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    template_ids.add(value.strip())
    return template_ids


def _collect_slide_plan_template_ids(payload: dict[str, Any]) -> tuple[set[str], list[int]]:
    template_ids: set[str] = set()
    conflict_slide_ids: list[int] = []
    slides = payload.get("slides")
    if not isinstance(slides, list):
        return template_ids, conflict_slide_ids
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = slide.get("slide_id")
        found_ids: set[str] = set()
        for key in ("template_id", "template_key", "primary_template", "reference_template", "selected_template"):
            value = slide.get(key)
            if isinstance(value, str) and value.strip():
                found_ids.add(value.strip())
        candidates = slide.get("template_candidates")
        if isinstance(candidates, list):
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                value = item.get("template_id") or item.get("template_key")
                if isinstance(value, str) and value.strip():
                    found_ids.add(value.strip())
        template_ids.update(found_ids)
        if isinstance(slide_id, int) and found_ids:
            # actual conflict decision is done by caller; here we keep template info by slide.
            # caller may append slide_id to conflict list when needed.
            pass
    return template_ids, conflict_slide_ids


def evaluate_template_binding_consistency(project_dir: Path) -> dict[str, Any]:
    project_dir = project_dir.resolve()
    findings: list[ConsistencyFinding] = []
    metrics: dict[str, Any] = {
        "binding_present": False,
        "binding_template_id": None,
        "reference_pack_present": False,
        "slide_visual_plan_present": False,
        "reference_pack_template_ids": [],
        "slide_visual_plan_template_ids": [],
        "override_reason": None,
    }

    binding_path = project_dir / "template_binding.json"
    binding_payload, binding_error = _load_json(binding_path)
    if binding_error is not None:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="invalid-template-binding-json",
                path=str(binding_path),
                message=binding_error,
            )
        )
        return {
            "ok": False,
            "project": str(project_dir),
            "findings": [asdict(item) for item in findings],
            "metrics": metrics,
        }
    if binding_payload is None:
        return {
            "ok": True,
            "project": str(project_dir),
            "findings": [],
            "metrics": metrics,
        }

    binding_id = str(binding_payload.get("template_id") or binding_payload.get("layout_id") or "").strip()
    metrics["binding_present"] = True
    metrics["binding_template_id"] = binding_id or None
    if not binding_id:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="template-binding-missing-layout-id",
                path=str(binding_path),
                message="template_binding.json exists but layout_id is empty.",
            )
        )
        return {
            "ok": False,
            "project": str(project_dir),
            "findings": [asdict(item) for item in findings],
            "metrics": metrics,
        }

    reference_pack_path = project_dir / "reference_pack.json"
    reference_pack_payload, reference_pack_error = _load_json(reference_pack_path)
    if reference_pack_error is not None:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="invalid-reference-pack-json",
                path=str(reference_pack_path),
                message=reference_pack_error,
            )
        )
    elif reference_pack_payload is None:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="missing-reference-pack-for-binding",
                path=str(reference_pack_path),
                message=f"template_binding layout_id={binding_id!r} exists but reference_pack.json is missing.",
            )
        )
    else:
        metrics["reference_pack_present"] = True
        ref_ids = _collect_reference_pack_template_ids(reference_pack_payload)
        metrics["reference_pack_template_ids"] = sorted(ref_ids)
        fallback = reference_pack_payload.get("fallback")
        override_reason = None
        if isinstance(fallback, dict):
            raw_reason = fallback.get("reason")
            if isinstance(raw_reason, str) and raw_reason.strip():
                override_reason = raw_reason.strip()
        metrics["override_reason"] = override_reason

        if binding_id not in ref_ids:
            mode = str(reference_pack_payload.get("mode") or "").strip()
            if mode == "free-design" and override_reason:
                findings.append(
                    ConsistencyFinding(
                        severity="warning",
                        code="template-binding-override-reason",
                        path=str(reference_pack_path),
                        message=(
                            f"template_binding layout_id={binding_id!r} is overridden by free-design mode; "
                            f"override_reason={override_reason!r}."
                        ),
                    )
                )
            else:
                findings.append(
                    ConsistencyFinding(
                        severity="warning",
                        code="template-binding-reference-pack-mismatch",
                        path=str(reference_pack_path),
                        message=(
                            f"template_binding layout_id={binding_id!r} is not referenced by "
                            f"reference_pack templates {sorted(ref_ids)}."
                        ),
                    )
                )

    slide_plan_path = project_dir / "slide_visual_plan.json"
    slide_plan_payload, slide_plan_error = _load_json(slide_plan_path)
    if slide_plan_error is not None:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="invalid-slide-visual-plan-json",
                path=str(slide_plan_path),
                message=slide_plan_error,
            )
        )
    elif slide_plan_payload is None:
        findings.append(
            ConsistencyFinding(
                severity="warning",
                code="missing-slide-visual-plan-for-binding",
                path=str(slide_plan_path),
                message=f"template_binding layout_id={binding_id!r} exists but slide_visual_plan.json is missing.",
            )
        )
    else:
        metrics["slide_visual_plan_present"] = True
        slide_ids, _ = _collect_slide_plan_template_ids(slide_plan_payload)
        metrics["slide_visual_plan_template_ids"] = sorted(slide_ids)
        if slide_ids and binding_id not in slide_ids:
            findings.append(
                ConsistencyFinding(
                    severity="warning",
                    code="template-binding-slide-visual-plan-mismatch",
                    path=str(slide_plan_path),
                    message=(
                        f"template_binding layout_id={binding_id!r} conflicts with slide_visual_plan "
                        f"template ids {sorted(slide_ids)}."
                    ),
                )
            )
        if not slide_ids:
            findings.append(
                ConsistencyFinding(
                    severity="warning",
                    code="template-binding-slide-visual-plan-unspecified",
                    path=str(slide_plan_path),
                    message=(
                        f"template_binding layout_id={binding_id!r} exists, but slide_visual_plan has no explicit "
                        "template id fields; keep this consistent by documenting template usage or override reason."
                    ),
                )
            )

    has_mismatch = any(
        item.code
        in {
            "template-binding-reference-pack-mismatch",
            "template-binding-slide-visual-plan-mismatch",
            "missing-reference-pack-for-binding",
            "missing-slide-visual-plan-for-binding",
        }
        for item in findings
    )
    return {
        "ok": not has_mismatch,
        "project": str(project_dir),
        "findings": [asdict(item) for item in findings],
        "metrics": metrics,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check template_binding consistency with reference_pack and slide_visual_plan."
    )
    parser.add_argument("project_dir", type=Path, help="Path to projects/<project_name>")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when any warning is found.")
    args = parser.parse_args(argv)

    result = evaluate_template_binding_consistency(args.project_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result.get("findings"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
