"""SVG to PNG conversion for Office compatibility mode."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# SVG to PNG library detection
# Prefer CairoSVG (better quality), fall back to svglib
PNG_RENDERER: str | None = None

try:
    import cairosvg
    PNG_RENDERER = 'cairosvg'
except (ImportError, OSError):
    try:
        from reportlab.graphics import renderPM
        from svglib.svglib import svg2rlg
        PNG_RENDERER = 'svglib'
    except (ImportError, OSError):
        pass


def get_png_renderer_info() -> tuple[str | None, str, str | None]:
    """Get PNG renderer status information.

    Returns:
        (renderer_name, status_text, install_hint) tuple.
    """
    if PNG_RENDERER == 'cairosvg':
        return ('cairosvg', '(full gradient/filter support)', None)
    elif PNG_RENDERER == 'svglib':
        return ('svglib', '(some gradients may be lost)',
                'Install cairosvg for better results: pip install cairosvg')
    else:
        if browser_candidates():
            return ('browser', '(headless browser fallback)', None)
        return (None, '(not installed)',
                'Install CairoSVG/svglib, or install Edge/Chrome for browser fallback')


def browser_candidates() -> list[Path]:
    candidates: list[Path] = []

    env_browser = os.environ.get("AI_PPT_BROWSER")
    if env_browser:
        candidates.append(Path(env_browser))

    for name in ("msedge", "chrome", "chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))

    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen and candidate.exists():
            unique.append(candidate)
            seen.add(key)
    return unique


def render_with_browser(
    svg_path: Path,
    png_path: Path,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    browsers = browser_candidates()
    if not browsers:
        return False

    pixel_width = width or 1280
    pixel_height = height or 720
    png_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image
    except Exception as exc:
        print(f"  Warning: Browser PNG fallback needs Pillow: {exc}")
        return False

    try:
        svg_markup = svg_path.read_text(encoding="utf-8-sig")
    except Exception as exc:
        print(f"  Warning: Unable to read SVG for browser PNG fallback ({svg_path.name}): {exc}")
        return False

    svg_markup = re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg_markup)
    with tempfile.TemporaryDirectory(prefix="ppt_core_svg_browser_") as tmp:
        tmp_dir = Path(tmp)
        wrapper = tmp_dir / "render.html"
        screenshot_path = tmp_dir / "screenshot.png"
        wrapper.write_text(
            "\n".join(
                [
                    "<!doctype html>",
                    "<html>",
                    "<head>",
                    "<meta charset=\"utf-8\">",
                    f"<base href=\"{svg_path.parent.resolve().as_uri()}/\">",
                    "<style>",
                    (
                        f"html, body {{ margin: 0; width: {pixel_width}px; "
                        f"height: {pixel_height}px; overflow: hidden; background: transparent; }}"
                    ),
                    f"svg {{ display: block; width: {pixel_width}px; height: {pixel_height}px; }}",
                    "</style>",
                    "</head>",
                    f"<body>{svg_markup}</body>",
                    "</html>",
                ]
            ),
            encoding="utf-8",
        )

        for browser in browsers:
            if screenshot_path.exists():
                screenshot_path.unlink()
            cmd = [
                str(browser),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-sandbox",
                "--allow-file-access-from-files",
                "--force-device-scale-factor=1",
                f"--window-size={pixel_width},{pixel_height + 120}",
                f"--screenshot={screenshot_path}",
                wrapper.resolve().as_uri(),
            ]
            try:
                result = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=45,
                )
            except Exception as exc:
                print(f"  Warning: Browser PNG fallback failed ({Path(browser).name}): {exc}")
                continue

            if result.returncode != 0 or not screenshot_path.exists() or screenshot_path.stat().st_size == 0:
                details = (result.stderr or result.stdout or "").strip()
                print(f"  Warning: Browser PNG fallback failed ({Path(browser).name}): {details}")
                continue

            try:
                image = Image.open(screenshot_path)
                image.crop((0, 0, pixel_width, pixel_height)).save(png_path)
                return True
            except Exception as exc:
                print(f"  Warning: Browser PNG fallback crop failed ({svg_path.name}): {exc}")
                return False

    return False


def convert_svg_to_png(
    svg_path: Path,
    png_path: Path,
    width: int | None = None,
    height: int | None = None,
) -> bool:
    """Convert SVG to PNG using the available renderer.

    Args:
        svg_path: SVG file path.
        png_path: Output PNG file path.
        width: Output width in pixels.
        height: Output height in pixels.

    Returns:
        Whether the conversion was successful.
    """
    if PNG_RENDERER is not None:
        try:
            if PNG_RENDERER == 'cairosvg':
                cairosvg.svg2png(
                    url=str(svg_path),
                    write_to=str(png_path),
                    output_width=width,
                    output_height=height,
                )
                return True

            elif PNG_RENDERER == 'svglib':
                drawing = svg2rlg(str(svg_path))
                if drawing is None:
                    print(f"  Warning: Unable to parse SVG ({svg_path.name})")
                else:
                    renderPM.drawToFile(
                        drawing,
                        str(png_path),
                        fmt="PNG",
                        configPIL={'quality': 95},
                    )
                    return True

        except Exception as e:
            print(f"  Warning: SVG to PNG conversion failed ({svg_path.name}): {e}")

    return render_with_browser(svg_path, png_path, width=width, height=height)
