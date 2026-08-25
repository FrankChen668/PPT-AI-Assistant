from __future__ import annotations

from pathlib import Path
from typing import Any


MOJIBAKE_TOKENS = ("????", "mojibake", "鈥", "銆", "锟", "�")
PLACEHOLDER_SVG_MARKERS = (
    "template_id=workbench-poc",
    "占位页，仅用于流程校验",
    "工作台流程校验页",
)


def _find_mojibake_tokens(text: str) -> list[str]:
    hits: list[str] = []
    for token in MOJIBAKE_TOKENS:
        if token and token in text:
            hits.append(token)
    return hits


def _is_placeholder_svg(svg_text: str) -> bool:
    folded = str(svg_text or "").lower()
    for marker in PLACEHOLDER_SVG_MARKERS:
        if marker and marker.lower() in folded:
            return True
    return False


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def collect_real_generation_risks(target: Path, status: dict[str, Any] | None = None) -> dict[str, Any]:
    status = status if isinstance(status, dict) else {}
    slide_entries = status.get("slides") if isinstance(status.get("slides"), list) else []
    slide_ids: list[int] = []
    for slide in slide_entries:
        if not isinstance(slide, dict):
            continue
        slide_id = int(slide.get("slide_id") or 0)
        if slide_id > 0:
            slide_ids.append(slide_id)
    if not slide_ids:
        slide_ids = sorted(
            int(path.stem.split("_")[-1])
            for path in (target / "svg_output").glob("slide_*.svg")
            if path.stem.split("_")[-1].isdigit()
        )

    placeholder_slides: list[int] = []
    mojibake_risks: list[dict[str, Any]] = []

    def record_mojibake(path: Path, text: str) -> None:
        tokens = _find_mojibake_tokens(text)
        if not tokens:
            return
        rel = str(path.relative_to(target)).replace("\\", "/")
        mojibake_risks.append({"path": rel, "tokens": tokens[:6]})

    for rel in ("outline.md", "blueprint.json", "slide_visual_plan.json"):
        file_path = target / rel
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        record_mojibake(file_path, content)

    for slide_id in slide_ids:
        svg_path = target / "svg_output" / f"slide_{slide_id:02d}.svg"
        if not svg_path.exists():
            continue
        try:
            svg_text = svg_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_placeholder_svg(svg_text):
            placeholder_slides.append(slide_id)
        record_mojibake(svg_path, svg_text)

    for risk in mojibake_risks:
        risk["tokens"] = _dedupe_keep_order([str(item) for item in risk.get("tokens") or []])[:6]
    return {
        "placeholder_slides": sorted({int(item) for item in placeholder_slides if int(item) > 0}),
        "mojibake_risks": mojibake_risks[:24],
    }


def apply_real_generation_guards(target: Path, status: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    guarded = dict(readiness or {})
    risks = collect_real_generation_risks(target, status)
    placeholder_slides = risks.get("placeholder_slides") or []
    export_placeholder_slides = [
        int(item)
        for item in guarded.get("placeholder_slides") or []
        if isinstance(item, int) or str(item).isdigit()
    ]
    mojibake_risks = risks.get("mojibake_risks") or []
    reason_codes = [str(code) for code in guarded.get("reason_codes") or [] if str(code).strip()]
    reasons = [str(item) for item in guarded.get("reasons") or [] if str(item).strip()]

    if placeholder_slides:
        reason_codes.append("placeholder_detected")
        reasons.append(
            "Placeholder SVG detected. placeholder is dry-run only; regenerate real AI-authored content before export."
        )
    if mojibake_risks:
        reason_codes.append("mojibake_detected")
        reasons.append("Text integrity check failed: mojibake markers found in project artifacts.")

    blocked = bool(placeholder_slides or mojibake_risks)
    if blocked:
        guarded["ready"] = False
        guarded["status"] = "not_ready"
        guarded["real_generation_blocked"] = True
    guarded["reason_codes"] = _dedupe_keep_order(reason_codes)
    guarded["reasons"] = _dedupe_keep_order(reasons)
    guarded["placeholder_slides"] = placeholder_slides or export_placeholder_slides
    if placeholder_slides:
        guarded["detected_placeholder_slides"] = placeholder_slides
    guarded["mojibake_risks"] = mojibake_risks
    return guarded
