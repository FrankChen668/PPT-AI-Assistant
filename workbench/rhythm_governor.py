from __future__ import annotations

from typing import Any


ROLE_SEQUENCE = [
    "setup",
    "pressure",
    "proof",
    "extension",
    "standard",
    "business-complexity",
    "comparison",
    "governance",
]

PATTERN_TO_ROLE = {
    "capability_core_map": "setup",
    "pressure_to_upgrade": "pressure",
    "proof_chain_map": "proof",
    "lifecycle_extension_flow": "extension",
    "governance_columns": "standard",
    "dual_business_traceability_map": "business-complexity",
    "comparison_decision_matrix": "comparison",
    "responsibility_swimlane": "governance",
}


def _signature(slide: dict[str, Any]) -> str:
    return f"{slide.get('selected_archetype', '')}|{slide.get('rhythm_role', '')}"


def govern_deck_rhythm(slides: list[dict[str, Any]]) -> dict[str, Any]:
    """Return {'slides': adjusted_slides, 'deck_rhythm_map': ..., 'layout_exploration': ...}."""
    adjusted = [dict(item) for item in slides]
    rhythm_map: list[dict[str, Any]] = []

    previous_signature = ""
    repeat_count = 0
    for index, slide in enumerate(adjusted):
        signature = _signature(slide)
        if signature == previous_signature:
            repeat_count += 1
        else:
            previous_signature = signature
            repeat_count = 1

        original_role = str(slide.get("rhythm_role") or "")
        pattern_id = str((slide.get("page_prompt_pattern") or {}).get("pattern_id") or "")
        target_role = PATTERN_TO_ROLE.get(pattern_id, ROLE_SEQUENCE[index % len(ROLE_SEQUENCE)])
        changed = False

        if repeat_count > 2:
            slide["rhythm_role"] = target_role
            previous_pattern = str((adjusted[index - 1].get("page_prompt_pattern") or {}).get("pattern_id") or "")
            slide["variation_rule"] = f"Avoid repeating previous pattern `{previous_pattern}` on adjacent pages."
            signature = _signature(slide)
            previous_signature = signature
            repeat_count = 1
            changed = True
        elif not original_role:
            slide["rhythm_role"] = target_role
            changed = True

        rhythm_map.append(
            {
                "slide_id": int(slide.get("slide_id") or slide.get("id") or index + 1),
                "pattern_id": pattern_id,
                "original_rhythm_role": original_role,
                "final_rhythm_role": str(slide.get("rhythm_role") or ""),
                "signature": _signature(slide),
                "changed": changed,
            }
        )

    return {
        "slides": adjusted,
        "deck_rhythm_map": rhythm_map,
        "layout_exploration": {
            "enabled": len(adjusted) > 1,
            "candidate_count": 3 if len(adjusted) > 1 else 1,
            "anti_repeat_window": 2 if len(adjusted) > 1 else 0,
            "enforce_in_modes": ["prompt_deck", "document_deck"],
        },
    }
