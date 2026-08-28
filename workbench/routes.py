from __future__ import annotations

from typing import TypedDict


class RouteSpec(TypedDict):
    route_id: str
    label: str
    deck_type: str
    style_profile: str
    template_mode: str
    template_required: bool
    generation_strategy: str
    qa_profile: str
    allowed_actions: list[str]
    forbidden_actions: list[str]


STYLE_ID_ALIAS = {
    "consulting_blue": "consulting",
    "consulting_classic": "consulting",
    "tech_dark": "tech",
    "minimal_white": "minimal",
}

STYLE_LABEL_ALIAS = {
    "consulting_blue": "咨询风",
    "consulting_classic": "咨询风格",
    "tech_dark": "科技风",
    "minimal_white": "极简风",
}

TEMPLATE_MODE_LABEL = {
    "free": "自由设计",
    "reference": "参考模板",
    "reuse": "沿用风格",
    "strict_template": "严格模板",
}

_BASE_ROUTES: dict[tuple[str, str], dict[str, str | list[str]]] = {
    ("single", "consulting"): {
        "deck_label": "单页",
        "style_label": STYLE_LABEL_ALIAS["consulting_blue"],
        "generation_strategy": "single_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
    ("single", "tech"): {
        "deck_label": "单页",
        "style_label": STYLE_LABEL_ALIAS["tech_dark"],
        "generation_strategy": "single_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
    ("single", "minimal"): {
        "deck_label": "单页",
        "style_label": STYLE_LABEL_ALIAS["minimal_white"],
        "generation_strategy": "single_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
    ("multi", "consulting"): {
        "deck_label": "多页",
        "style_label": STYLE_LABEL_ALIAS["consulting_blue"],
        "generation_strategy": "multi_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
    ("multi", "tech"): {
        "deck_label": "多页",
        "style_label": STYLE_LABEL_ALIAS["tech_dark"],
        "generation_strategy": "multi_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
    ("multi", "minimal"): {
        "deck_label": "多页",
        "style_label": STYLE_LABEL_ALIAS["minimal_white"],
        "generation_strategy": "multi_page_svg_authoring",
        "qa_profile": "presentation",
        "allowed_actions": ["author_svg", "qa_slide", "finalize_export"],
        "forbidden_actions": [
            "render_svg",
            "pptxgenjs",
            "temporary_python_pptx_export",
            "modify_unrequested_slides",
        ],
    },
}


def resolve_route(
    deck_type: str,
    style_profile: str,
    template_mode: str,
    *,
    template_bound: bool = False,
) -> RouteSpec:
    style_id = STYLE_ID_ALIAS.get(style_profile)
    mode_label = TEMPLATE_MODE_LABEL.get(template_mode)
    if not style_id or not mode_label:
        raise ValueError(f"Unsupported style_profile/template_mode combination: {style_profile}/{template_mode}")

    key = (deck_type, style_id)
    if key not in _BASE_ROUTES:
        raise ValueError(f"No route configured for deck_type={deck_type}, style_profile={style_profile}.")

    base = _BASE_ROUTES[key]

    template_required = template_mode == "strict_template"
    if template_required and not template_bound:
        raise ValueError("strict_template requires a bound template. Please bind template first.")

    route_id = f"{deck_type}_{style_id}_{template_mode}"
    style_label = STYLE_LABEL_ALIAS.get(style_profile, str(base["style_label"]))
    route_label = f"{base['deck_label']}{style_label}{mode_label}路径"

    return {
        "route_id": route_id,
        "label": route_label,
        "deck_type": deck_type,
        "style_profile": style_profile,
        "template_mode": template_mode,
        "template_required": template_required,
        "generation_strategy": str(base["generation_strategy"]),
        "qa_profile": str(base["qa_profile"]),
        "allowed_actions": list(base["allowed_actions"]),
        "forbidden_actions": list(base["forbidden_actions"]),
    }
