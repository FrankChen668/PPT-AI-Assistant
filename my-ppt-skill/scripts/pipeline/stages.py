"""Stage-level option resolution for build_project CLI."""

from __future__ import annotations

from argparse import Namespace

from build_config.build_options import PhaseOptions


def resolve_phase_options(args: Namespace) -> PhaseOptions:
    auto_copyfit = args.auto_copyfit
    if auto_copyfit is None:
        auto_copyfit = False

    delivery_ready = args.delivery_ready
    if delivery_ready is None:
        delivery_ready = False

    enable_layout_lint = args.enable_layout_lint or args.phase == "authoring"
    safe_area_profile = args.safe_area_profile
    if args.phase == "authoring" and safe_area_profile == "legacy":
        safe_area_profile = "presentation"

    deterministic_repair = bool(args.deterministic_repair or args.auto_repair_failed_slides)
    used_legacy_repair_flag = bool(args.auto_repair_failed_slides and not args.deterministic_repair)

    return PhaseOptions(
        auto_copyfit=auto_copyfit,
        delivery_ready=delivery_ready,
        enable_layout_lint=enable_layout_lint,
        safe_area_profile=safe_area_profile,
        deterministic_repair=deterministic_repair,
        used_legacy_repair_flag=used_legacy_repair_flag,
    )
