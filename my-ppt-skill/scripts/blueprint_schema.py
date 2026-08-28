from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BlueprintIssue:
    code: str
    path: str
    message: str


def validate_blueprint_schema(data: Any) -> list[BlueprintIssue]:
    issues: list[BlueprintIssue] = []

    if not isinstance(data, dict):
        return [BlueprintIssue("invalid-root", "blueprint.json", "Root must be an object.")]

    slides = data.get("slides")
    if not isinstance(slides, list):
        return [BlueprintIssue("missing-slides", "blueprint.json", "blueprint.json must contain a slides array.")]

    for idx, slide in enumerate(slides, start=1):
        path = f"blueprint.json/slides/{idx}"
        if not isinstance(slide, dict):
            issues.append(BlueprintIssue("invalid-slide", path, "Each slide must be an object."))
            continue

        for required in ("id", "title", "layout_tag", "content"):
            if required not in slide:
                issues.append(BlueprintIssue("missing-slide-key", path, f"Missing key: {required}."))

        slide_id = slide.get("id")
        if slide_id is not None and not isinstance(slide_id, int):
            issues.append(BlueprintIssue("invalid-slide-id", path, "id must be an integer."))

        title = slide.get("title")
        if title is not None and not isinstance(title, str):
            issues.append(BlueprintIssue("invalid-title", path, "title must be a string."))

        layout_tag = slide.get("layout_tag")
        if layout_tag is not None and not isinstance(layout_tag, str):
            issues.append(BlueprintIssue("invalid-layout-tag", path, "layout_tag must be a string."))

        content = slide.get("content")
        if content is not None and not isinstance(content, dict):
            issues.append(BlueprintIssue("invalid-content", path, "content must be an object."))

        narrative = slide.get("narrative_intent")
        if narrative is not None and not isinstance(narrative, str):
            issues.append(
                BlueprintIssue("invalid-narrative-intent", path, "narrative_intent must be a string when provided.")
            )

        source_refs = slide.get("source_refs")
        if source_refs is not None:
            if not isinstance(source_refs, list) or not all(isinstance(item, str) for item in source_refs):
                issues.append(
                    BlueprintIssue(
                        "invalid-source-refs",
                        path,
                        "source_refs must be an array of strings when provided.",
                    )
                )

        claims = slide.get("claims")
        if claims is not None:
            if not isinstance(claims, list) or not all(isinstance(item, str) for item in claims):
                issues.append(
                    BlueprintIssue(
                        "invalid-claims",
                        path,
                        "claims must be an array of strings when provided.",
                    )
                )

        asset_refs = slide.get("asset_refs")
        if asset_refs is not None:
            if not isinstance(asset_refs, list) or not all(isinstance(item, str) for item in asset_refs):
                issues.append(
                    BlueprintIssue(
                        "invalid-asset-refs",
                        path,
                        "asset_refs must be an array of strings when provided.",
                    )
                )

        visual_intent = slide.get("visual_intent")
        if visual_intent is not None and not isinstance(visual_intent, str):
            issues.append(
                BlueprintIssue(
                    "invalid-visual-intent",
                    path,
                    "visual_intent must be a string when provided.",
                )
            )

        acceptance_criteria = slide.get("acceptance_criteria")
        if acceptance_criteria is not None:
            if not isinstance(acceptance_criteria, list) or not all(
                isinstance(item, str) for item in acceptance_criteria
            ):
                issues.append(
                    BlueprintIssue(
                        "invalid-acceptance-criteria",
                        path,
                        "acceptance_criteria must be an array of strings when provided.",
                    )
                )

    return issues
