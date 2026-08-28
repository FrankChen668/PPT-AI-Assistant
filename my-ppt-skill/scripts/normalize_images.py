#!/usr/bin/env python3
"""Normalize PNG images with alpha channel to fixed white background."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class NormalizeStats:
    scanned: int
    converted: int
    skipped: int


def _iter_pngs(images_dir: Path) -> Iterable[Path]:
    for path in sorted(images_dir.rglob("*.png")):
        if path.is_file():
            yield path


def normalize_images_white_bg(images_dir: Path) -> NormalizeStats:
    if not images_dir.exists():
        return NormalizeStats(scanned=0, converted=0, skipped=0)

    try:
        from PIL import Image
    except Exception as exc:  # pragma: no cover - dependency/runtime guard
        raise RuntimeError(f"Pillow is required for image normalization: {exc}") from exc

    scanned = 0
    converted = 0
    skipped = 0

    for path in _iter_pngs(images_dir):
        scanned += 1
        image = Image.open(path)
        has_alpha = "A" in image.getbands()
        if not has_alpha:
            skipped += 1
            image.close()
            continue
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        out = Image.alpha_composite(bg, rgba).convert("RGB")
        out.save(path, format="PNG", optimize=True)
        rgba.close()
        image.close()
        converted += 1

    return NormalizeStats(scanned=scanned, converted=converted, skipped=skipped)


def normalize_project_images_white_bg(project_dir: Path) -> NormalizeStats:
    return normalize_images_white_bg(project_dir / "images")

