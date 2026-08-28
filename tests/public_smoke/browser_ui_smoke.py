#!/usr/bin/env python3
"""Browser UI surface smoke for the Workbench frontend.

Proves the real user entry surface, not just an SVG API response:
  1. GET /            -> 200 and real Workbench HTML (not a 404 page or placeholder)
  2. every CSS/JS asset referenced by that HTML -> HTTP 200
  3. the HTML contains recognizable Workbench main-view content
  4. optional: /api/projects/<id>/slides/1/svg -> 200 for a given project id

Usage:
  python tests/public_smoke/browser_ui_smoke.py --base-url http://127.0.0.1:8765
  python tests/public_smoke/browser_ui_smoke.py --base-url http://127.0.0.1:8765 --project-id my-project
"""

import argparse
import re
import sys
import urllib.request


def _fetch(base_url: str, path: str) -> tuple[int, str]:
    url = base_url.rstrip('/') + path
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as exc:
        return exc.code, ''
    except urllib.error.URLError as exc:
        print(f"FAIL connection {url}: {exc.reason}")
        raise SystemExit(2)


def check_browser_surface(base_url: str, project_id: str | None = None) -> bool:
    ok = True

    status, html = _fetch(base_url, '/')
    if status != 200:
        print(f"FAIL GET / -> {status}")
        return False
    print(f"PASS GET / -> 200 ({len(html)} bytes)")

    if '404' in html[:200] or not re.search(r'<html[\s>]', html, re.IGNORECASE):
        print("FAIL / did not return real HTML")
        return False

    markers = ['Workbench', '工作台']
    if not any(marker.lower() in html.lower() for marker in markers):
        print("FAIL no recognizable Workbench main-view content in /")
        ok = False
    else:
        print("PASS / contains Workbench main-view content")

    asset_paths = set()
    for match in re.finditer(r'(?:src|href)="(/static/[^"?]+)', html):
        asset_paths.add(match.group(1))
    if not asset_paths:
        print("FAIL / references no /static/ assets")
        return False

    failed_assets = []
    for asset in sorted(asset_paths):
        asset_status, _ = _fetch(base_url, asset)
        if asset_status != 200:
            failed_assets.append((asset, asset_status))
    if failed_assets:
        for asset, asset_status in failed_assets:
            print(f"FAIL static asset {asset} -> {asset_status}")
        ok = False
    else:
        css_count = sum(1 for a in asset_paths if a.endswith('.css'))
        js_count = sum(1 for a in asset_paths if a.endswith('.js'))
        print(f"PASS all {len(asset_paths)} referenced static assets -> 200 "
              f"(css={css_count}, js={js_count}, other={len(asset_paths) - css_count - js_count})")

    if project_id:
        svg_path = f"/api/projects/{project_id}/slides/1/svg"
        svg_status, _ = _fetch(base_url, svg_path)
        if svg_status != 200:
            print(f"FAIL {svg_path} -> {svg_status}")
            ok = False
        else:
            print(f"PASS {svg_path} -> 200")

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description='Workbench browser UI smoke')
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--project-id', default=None,
                        help='optional project id to verify slide 1 SVG preview API')
    args = parser.parse_args()
    return 0 if check_browser_surface(args.base_url, args.project_id) else 1


if __name__ == '__main__':
    sys.exit(main())
