#!/usr/bin/env python3
"""Policy profiles for page budget/readability governance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfilePolicy:
    key: str
    label: str
    max_chars_per_slide: int
    max_text_nodes_per_slide: int
    max_items_per_primary_list: int
    min_heading_font_px: float
    min_theme_contrast: float
    visual_density_base_chars: int
    visual_density_base_nodes: int
    overflow_risk_low_ratio: float
    overflow_risk_medium_ratio: float
    overflow_risk_high_ratio: float


POLICIES: dict[str, ProfilePolicy] = {
    "presentation": ProfilePolicy(
        key="presentation",
        label="screen presentation",
        max_chars_per_slide=900,
        max_text_nodes_per_slide=28,
        max_items_per_primary_list=7,
        min_heading_font_px=34.0,
        min_theme_contrast=4.5,
        visual_density_base_chars=900,
        visual_density_base_nodes=28,
        overflow_risk_low_ratio=0.94,
        overflow_risk_medium_ratio=1.00,
        overflow_risk_high_ratio=1.08,
    ),
    "print_a4": ProfilePolicy(
        key="print_a4",
        label="A4 print/export",
        max_chars_per_slide=760,
        max_text_nodes_per_slide=22,
        max_items_per_primary_list=6,
        min_heading_font_px=36.0,
        min_theme_contrast=5.0,
        visual_density_base_chars=760,
        visual_density_base_nodes=22,
        overflow_risk_low_ratio=0.93,
        overflow_risk_medium_ratio=0.99,
        overflow_risk_high_ratio=1.06,
    ),
    "proposal_consulting": ProfilePolicy(
        key="proposal_consulting",
        label="proposal/consulting delivery",
        max_chars_per_slide=700,
        max_text_nodes_per_slide=20,
        max_items_per_primary_list=5,
        min_heading_font_px=38.0,
        min_theme_contrast=5.5,
        visual_density_base_chars=700,
        visual_density_base_nodes=20,
        overflow_risk_low_ratio=0.92,
        overflow_risk_medium_ratio=0.98,
        overflow_risk_high_ratio=1.05,
    ),
}


def resolve_profile_policy(profile: str | None) -> ProfilePolicy:
    key = (profile or "presentation").strip().lower()
    return POLICIES.get(key, POLICIES["presentation"])
