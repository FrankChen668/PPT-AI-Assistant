"""Core SVG -> DrawingML dispatcher, group handling, and main entry point."""

from __future__ import annotations

import re
from pathlib import Path
from xml.etree import ElementTree as ET

from .drawingml_context import ConvertContext
from .drawingml_elements import (
    convert_circle,
    convert_ellipse,
    convert_image,
    convert_line,
    convert_path,
    convert_polygon,
    convert_polyline,
    convert_rect,
    convert_text,
)
from .drawingml_styles import build_effect_xml
from .drawingml_utils import (
    SVG_NS,
    _extract_inheritable_styles,
    resolve_url_id,
)
from .native_conversion_report import conversion_issue, empty_slide_stats, finalize_slide_stats

# ---------------------------------------------------------------------------
# Transform & layout helpers
# ---------------------------------------------------------------------------

def parse_transform(transform_str: str) -> tuple[float, float, float, float]:
    """Parse SVG transform string, extract translate and scale.

    Returns:
        (dx, dy, sx, sy) tuple.
    """
    if not transform_str:
        return 0.0, 0.0, 1.0, 1.0

    dx, dy = 0.0, 0.0
    sx, sy = 1.0, 1.0

    m = re.search(r'translate\(\s*([-\d.]+)[\s,]+([-\d.]+)\s*\)', transform_str)
    if m:
        dx = float(m.group(1))
        dy = float(m.group(2))

    m = re.search(r'scale\(\s*([-\d.]+)(?:[\s,]+([-\d.]+))?\s*\)', transform_str)
    if m:
        sx = float(m.group(1))
        sy = float(m.group(2)) if m.group(2) else sx

    return dx, dy, sx, sy


def _extract_shape_bounds_emu(shape_xml: str) -> tuple[int, int, int, int] | None:
    """Extract bounds (x, y, x+cx, y+cy) in EMU from a shape XML string.

    Works for <p:sp>, <p:pic>, and <p:grpSp>.
    """
    off_match = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"', shape_xml)
    ext_match = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"', shape_xml)
    if off_match and ext_match:
        x = int(off_match.group(1))
        y = int(off_match.group(2))
        cx = int(ext_match.group(1))
        cy = int(ext_match.group(2))
        return (x, y, x + cx, y + cy)
    return None


# ---------------------------------------------------------------------------
# Group handling
# ---------------------------------------------------------------------------

def convert_g(elem: ET.Element, ctx: ConvertContext) -> str:
    """Convert SVG <g> to DrawingML group shape <p:grpSp>.

    Preserves group structure so elements can be selected and moved together
    in PowerPoint. Single-child groups are flattened to avoid unnecessary nesting.

    Uses identity coordinate mapping (chOff/chExt == off/ext) so child shapes
    keep their absolute slide coordinates unchanged.
    """
    transform = elem.get('transform', '')
    dx, dy, sx, sy = parse_transform(transform)

    filter_id = resolve_url_id(elem.get('filter', ''))
    style_overrides = _extract_inheritable_styles(elem)
    child_ctx = ctx.child(
        dx,
        dy,
        sx,
        sy,
        filter_id,
        style_overrides,
        critical_content=_is_critical_element(elem, ctx),
    )

    child_shapes: list[str] = []
    for child in elem:
        shape_xml = convert_element(child, child_ctx)
        if shape_xml:
            child_shapes.append(shape_xml)

    ctx.sync_from_child(child_ctx)

    if not child_shapes:
        return ''

    # Single child: flatten
    if len(child_shapes) == 1:
        return child_shapes[0]

    # Multiple children: wrap in <p:grpSp>
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')

    for shape_xml in child_shapes:
        bounds = _extract_shape_bounds_emu(shape_xml)
        if bounds:
            min_x = min(min_x, bounds[0])
            min_y = min(min_y, bounds[1])
            max_x = max(max_x, bounds[2])
            max_y = max(max_y, bounds[3])

    if min_x == float('inf'):
        return '\n'.join(child_shapes)

    group_x = int(min_x)
    group_y = int(min_y)
    group_w = max(int(max_x - min_x), 1)
    group_h = max(int(max_y - min_y), 1)

    shapes_xml = '\n'.join(child_shapes)
    group_id = ctx.next_id()

    group_effect = ''
    if filter_id and filter_id in ctx.defs:
        group_effect = build_effect_xml(ctx.defs[filter_id])

    return f'''<p:grpSp>
<p:nvGrpSpPr>
<p:cNvPr id="{group_id}" name="Group {group_id}"/>
<p:cNvGrpSpPr/>
<p:nvPr/>
</p:nvGrpSpPr>
<p:grpSpPr>
<a:xfrm>
<a:off x="{group_x}" y="{group_y}"/>
<a:ext cx="{group_w}" cy="{group_h}"/>
<a:chOff x="{group_x}" y="{group_y}"/>
<a:chExt cx="{group_w}" cy="{group_h}"/>
</a:xfrm>
{group_effect}
</p:grpSpPr>
{shapes_xml}
</p:grpSp>'''


# ---------------------------------------------------------------------------
# Defs collection & element dispatch
# ---------------------------------------------------------------------------

_NON_VISUAL_TAGS = frozenset(('defs', 'title', 'desc', 'metadata', 'style'))

_CONVERTERS = {
    'rect': convert_rect,
    'circle': convert_circle,
    'ellipse': convert_ellipse,
    'line': convert_line,
    'path': convert_path,
    'polygon': convert_polygon,
    'polyline': convert_polyline,
    'text': convert_text,
    'image': convert_image,
    'g': convert_g,
}

_CRITICAL_ROLE_TOKENS = {
    'title', 'headline', 'core', 'conclusion', 'key-conclusion', 'key_conclusion',
    'takeaway', 'critical', 'hero', 'main', 'primary', 'metric', 'kpi',
}

_UNSUPPORTED_EFFECT_TAGS = {
    'clipPath', 'mask', 'pattern',
    'feBlend', 'feColorMatrix', 'feComposite', 'feConvolveMatrix',
    'feDisplacementMap', 'feImage', 'feMerge', 'feMorphology',
    'feSpecularLighting', 'feTile', 'feTurbulence',
}


def _local_tag(elem: ET.Element) -> str:
    return elem.tag.rsplit('}', 1)[-1]


def _is_common_triangle_marker(marker: ET.Element | None) -> bool:
    if marker is None or _local_tag(marker) != 'marker':
        return False
    children = [child for child in marker if _local_tag(child) not in _NON_VISUAL_TAGS]
    if len(children) != 1:
        return False
    child = children[0]
    tag = _local_tag(child)
    if tag == 'polygon':
        coordinates = re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)', str(child.get('points') or ''))
        return len(coordinates) == 6
    if tag != 'path':
        return False
    path_data = str(child.get('d') or '')
    commands = {command.upper() for command in re.findall(r'[A-Za-z]', path_data)}
    coordinates = re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)', path_data)
    return bool(commands) and commands <= {'M', 'L', 'H', 'V', 'Z'} and 'Z' in commands and len(coordinates) >= 6


def _apply_marker_end(elem: ET.Element, tag: str, result: str, ctx: ConvertContext) -> str:
    if not result or tag not in {'line', 'polyline', 'path'}:
        return result
    marker_id = resolve_url_id(elem.get('marker-end', ''))
    if not marker_id:
        return result

    stats = ctx.conversion_stats
    marker = ctx.defs.get(marker_id)
    if _is_common_triangle_marker(marker):
        updated = result.replace('</a:ln>', '<a:tailEnd type="triangle"/></a:ln>', 1)
        if updated != result and stats is not None:
            stats['markers_converted'] = int(stats.get('markers_converted') or 0) + 1
            events = stats.setdefault('marker_events', [])
            if isinstance(events, list):
                events.append(
                    conversion_issue(
                        slide_id=str(stats.get('slide_id') or f'slide_{ctx.slide_num:02d}'),
                        tag=tag,
                        element_id=elem.get('id'),
                        error_type='marker-converted',
                        message=f'SVG marker-end #{marker_id} was mapped to an editable DrawingML triangle arrow.',
                        hard_blocker=False,
                        code='native-marker-converted',
                    )
                )
        return updated

    if stats is not None:
        stats['unsupported_markers'] = int(stats.get('unsupported_markers') or 0) + 1
        stats['unsupported_elements'] = int(stats.get('unsupported_elements') or 0) + 1
        tags = stats.setdefault('unsupported_tags', [])
        if isinstance(tags, list):
            tags.append('marker')
    _record_issue(
        ctx,
        elem,
        'marker',
        error_type='unsupported-marker',
        message=f'SVG marker-end #{marker_id} is not a supported simple triangle marker.',
        hard_blocker=False,
        code='native-unsupported-marker',
    )
    return result


def _is_hidden(elem: ET.Element) -> bool:
    style = str(elem.get('style') or '').replace(' ', '').lower()
    return (
        str(elem.get('display') or '').strip().lower() == 'none'
        or str(elem.get('visibility') or '').strip().lower() in {'hidden', 'collapse'}
        or 'display:none' in style
        or 'visibility:hidden' in style
        or 'visibility:collapse' in style
    )


def _positive_attr(elem: ET.Element, name: str) -> bool:
    try:
        return float(str(elem.get(name) or '0').replace('px', '')) > 0
    except ValueError:
        return False


def _is_visible_element(elem: ET.Element, tag: str) -> bool:
    if _is_hidden(elem) or tag in _NON_VISUAL_TAGS or tag == 'g':
        return False
    if tag == 'text':
        return bool(''.join(elem.itertext()).strip())
    if tag == 'image':
        href = elem.get('href') or elem.get('{http://www.w3.org/1999/xlink}href')
        return bool(href) and _positive_attr(elem, 'width') and _positive_attr(elem, 'height')
    if tag == 'rect':
        return _positive_attr(elem, 'width') and _positive_attr(elem, 'height')
    if tag == 'circle':
        return _positive_attr(elem, 'r')
    if tag == 'ellipse':
        return _positive_attr(elem, 'rx') and _positive_attr(elem, 'ry')
    if tag == 'path':
        return bool(str(elem.get('d') or '').strip())
    if tag in {'polygon', 'polyline'}:
        return bool(str(elem.get('points') or '').strip())
    return True


def _is_critical_element(elem: ET.Element, ctx: ConvertContext) -> bool:
    if ctx.critical_content:
        return True
    values = [
        elem.get('id'), elem.get('class'), elem.get('data-role'), elem.get('data-content-role'),
        elem.get('content-role'), elem.get('data-block'), elem.get('aria-label'),
    ]
    semantic = ' '.join(str(value).lower() for value in values if value)
    tokens = {token for token in re.split(r'[^a-z0-9]+', semantic) if token}
    explicit_critical = bool(tokens & _CRITICAL_ROLE_TOKENS) or any(
        marker in semantic for marker in ('key conclusion', 'key-conclusion', 'key_conclusion')
    )
    if explicit_critical:
        return True
    if _local_tag(elem) == 'image' and ctx.canvas_area > 0:
        try:
            image_area = (
                float(str(elem.get('width') or 0).replace('px', ''))
                * float(str(elem.get('height') or 0).replace('px', ''))
            )
        except ValueError:
            image_area = 0.0
        return image_area / ctx.canvas_area >= 0.2
    return False


def _record_issue(
    ctx: ConvertContext,
    elem: ET.Element,
    tag: str,
    *,
    error_type: str,
    message: str,
    hard_blocker: bool,
    code: str,
) -> None:
    stats = ctx.conversion_stats
    if stats is None:
        return
    issues = stats.setdefault('issues', [])
    if isinstance(issues, list):
        issues.append(
            conversion_issue(
                slide_id=str(stats.get('slide_id') or f'slide_{ctx.slide_num:02d}'),
                tag=tag,
                element_id=elem.get('id'),
                error_type=error_type,
                message=message,
                hard_blocker=hard_blocker,
                code=code,
            )
        )


def _scan_source_children(root: ET.Element, ctx: ConvertContext, stats: dict[str, object]) -> None:
    for elem in root:
        tag = _local_tag(elem)
        if tag in _NON_VISUAL_TAGS:
            continue
        if tag == 'g':
            child_ctx = ctx.child(critical_content=_is_critical_element(elem, ctx))
            _scan_source_children(elem, child_ctx, stats)
            continue
        if not _is_visible_element(elem, tag):
            continue
        stats['visible_elements'] = int(stats.get('visible_elements') or 0) + 1
        critical = _is_critical_element(elem, ctx)
        if critical:
            stats['critical_elements'] = int(stats.get('critical_elements') or 0) + 1
        if tag == 'text':
            stats['source_text_nodes'] = int(stats.get('source_text_nodes') or 0) + 1
            if critical:
                stats['critical_text_nodes'] = int(stats.get('critical_text_nodes') or 0) + 1
        elif tag == 'image' and critical:
            stats['critical_images'] = int(stats.get('critical_images') or 0) + 1


def _record_unsupported_effects(root: ET.Element, ctx: ConvertContext, stats: dict[str, object]) -> None:
    for elem in root.iter():
        tag = _local_tag(elem)
        if tag not in _UNSUPPORTED_EFFECT_TAGS:
            continue
        stats['unsupported_elements'] = int(stats.get('unsupported_elements') or 0) + 1
        tags = stats.setdefault('unsupported_tags', [])
        if isinstance(tags, list):
            tags.append(tag)
        _record_issue(
            ctx,
            elem,
            tag,
            error_type='unsupported-effect',
            message=f'SVG effect <{tag}> is not preserved exactly in native DrawingML.',
            hard_blocker=False,
            code='native-unsupported-effect',
        )


def _canvas_area(root: ET.Element) -> float:
    view_box = str(root.get('viewBox') or '').replace(',', ' ').split()
    try:
        return float(view_box[2]) * float(view_box[3]) if len(view_box) == 4 else 1280.0 * 720.0
    except ValueError:
        return 1280.0 * 720.0


def scan_svg_source_stats(svg_path: Path, slide_num: int = 1) -> dict[str, object]:
    """Count source-visible and text elements without attempting conversion."""
    root = ET.parse(str(svg_path)).getroot()
    stats = empty_slide_stats(f'slide_{slide_num:02d}', Path(svg_path).name)
    ctx = ConvertContext(
        slide_num=slide_num,
        svg_dir=Path(svg_path).parent,
        conversion_stats=stats,
        canvas_area=_canvas_area(root),
    )
    _scan_source_children(root, ctx, stats)
    _record_unsupported_effects(root, ctx, stats)
    return stats


def collect_defs(root: ET.Element) -> dict[str, ET.Element]:
    """Collect all <defs> children into an {id: element} dictionary."""
    defs: dict[str, ET.Element] = {}
    for defs_elem in root.iter(f'{{{SVG_NS}}}defs'):
        for child in defs_elem:
            elem_id = child.get('id')
            if elem_id:
                defs[elem_id] = child
    # Also check for defs without namespace
    for defs_elem in root.iter('defs'):
        for child in defs_elem:
            elem_id = child.get('id')
            if elem_id:
                defs[elem_id] = child
    return defs


def convert_element(elem: ET.Element, ctx: ConvertContext) -> str:
    """Dispatch an SVG element to the appropriate converter."""
    tag = _local_tag(elem)

    converter = _CONVERTERS.get(tag)
    if converter:
        if tag == 'g':
            try:
                return converter(elem, ctx)
            except Exception as e:
                if ctx.conversion_stats is not None:
                    ctx.conversion_stats['conversion_errors'] = int(
                        ctx.conversion_stats.get('conversion_errors') or 0
                    ) + 1
                _record_issue(
                    ctx, elem, tag,
                    error_type='group-conversion-exception',
                    message=str(e),
                    hard_blocker=True,
                    code='native-conversion-failed',
                )
                print(f'  Warning: Failed to convert <{tag}>: {e}')
                return ''

        visible = _is_visible_element(elem, tag)
        stats = ctx.conversion_stats
        critical = _is_critical_element(elem, ctx)
        try:
            result = converter(elem, ctx)
        except Exception as e:
            if visible and stats is not None:
                stats['conversion_errors'] = int(stats.get('conversion_errors') or 0) + 1
                if tag == 'image':
                    stats['images_failed'] = int(stats.get('images_failed') or 0) + 1
            _record_issue(
                ctx, elem, tag,
                error_type='conversion-exception',
                message=str(e),
                hard_blocker=critical,
                code='native-content-loss' if critical else 'native-conversion-element-loss',
            )
            print(f'  Warning: Failed to convert <{tag}>: {e}')
            return ''

        result = _apply_marker_end(elem, tag, result, ctx)

        if visible and stats is not None:
            if result:
                stats['converted_elements'] = int(stats.get('converted_elements') or 0) + 1
                if critical:
                    stats['converted_critical_elements'] = int(
                        stats.get('converted_critical_elements') or 0
                    ) + 1
                if tag == 'text':
                    stats['converted_text_nodes'] = int(stats.get('converted_text_nodes') or 0) + 1
                    if critical:
                        stats['converted_critical_text_nodes'] = int(
                            stats.get('converted_critical_text_nodes') or 0
                        ) + 1
                elif tag == 'image':
                    stats['images_succeeded'] = int(stats.get('images_succeeded') or 0) + 1
                    if critical:
                        stats['converted_critical_images'] = int(
                            stats.get('converted_critical_images') or 0
                        ) + 1
            else:
                stats['conversion_errors'] = int(stats.get('conversion_errors') or 0) + 1
                if tag == 'image':
                    stats['images_failed'] = int(stats.get('images_failed') or 0) + 1
                _record_issue(
                    ctx, elem, tag,
                    error_type='empty-conversion-result',
                    message=f'Visible <{tag}> element produced no native DrawingML object.',
                    hard_blocker=critical,
                    code='native-content-loss' if critical else 'native-conversion-element-loss',
                )
        return result

    if tag in _NON_VISUAL_TAGS:
        return ''

    if _is_visible_element(elem, tag):
        stats = ctx.conversion_stats
        critical = _is_critical_element(elem, ctx)
        if stats is not None:
            stats['unsupported_elements'] = int(stats.get('unsupported_elements') or 0) + 1
            tags = stats.setdefault('unsupported_tags', [])
            if isinstance(tags, list):
                tags.append(tag)
        _record_issue(
            ctx, elem, tag,
            error_type='unsupported-tag',
            message=f'Visible SVG <{tag}> is not supported by the native DrawingML converter.',
            hard_blocker=critical,
            code='native-content-loss' if critical else 'native-unsupported-element',
        )
    return ''


def convert_svg_to_slide_shapes(
    svg_path: Path,
    slide_num: int = 1,
    verbose: bool = False,
) -> tuple[str, dict[str, bytes], list[dict[str, str]], dict[str, object]]:
    """Convert an SVG file to a complete DrawingML slide XML.

    Args:
        svg_path: Path to the SVG file.
        slide_num: Slide number (for naming).
        verbose: Print progress info.

    Returns:
        (slide_xml, media_files, rel_entries, conversion_stats) where:
        - slide_xml: Complete slide XML string.
        - media_files: Dict of {filename: bytes} for media to write.
        - rel_entries: List of relationship entries to add.
    """
    tree = ET.parse(str(svg_path))
    root = tree.getroot()

    defs = collect_defs(root)
    slide_id = f'slide_{slide_num:02d}'
    stats = empty_slide_stats(slide_id, Path(svg_path).name)
    canvas_area = _canvas_area(root)
    ctx = ConvertContext(
        defs=defs,
        slide_num=slide_num,
        svg_dir=Path(svg_path).parent,
        conversion_stats=stats,
        canvas_area=canvas_area,
    )
    _scan_source_children(root, ctx, stats)
    _record_unsupported_effects(root, ctx, stats)

    shapes: list[str] = []
    for child in root:
        tag = _local_tag(child)
        if tag == 'defs':
            continue
        result = convert_element(child, ctx)
        if result:
            shapes.append(result)

    finalize_slide_stats(stats)

    if verbose:
        print(
            f"  Converted {stats['converted_elements']} of {stats['visible_elements']} visible elements; "
            f"errors={stats['conversion_errors']}, unsupported={stats['unsupported_elements']}"
        )

    shapes_xml = '\n'.join(shapes)

    slide_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:cSld>
<p:spTree>
<p:nvGrpSpPr>
<p:cNvPr id="1" name=""/>
<p:cNvGrpSpPr/><p:nvPr/>
</p:nvGrpSpPr>
<p:grpSpPr>
<a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>
<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm>
</p:grpSpPr>
{shapes_xml}
</p:spTree>
</p:cSld>
<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''

    return slide_xml, ctx.media_files, ctx.rel_entries, stats
