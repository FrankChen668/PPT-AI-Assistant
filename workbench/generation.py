from __future__ import annotations

import json
import http.client
import re
import time
import urllib.error
import urllib.request
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree as ET

from workbench.state import add_event, backup_slide_revision, load_status, merge_slide_status, now_iso, save_status, slide_svg_path


from workbench.generation_settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_GENERATION_PROVIDER,
    DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED,
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SILICONFLOW_BASE_URL,
    DEFAULT_XIAOMI_BASE_URL,
    GEMINI_ENDPOINT,
    GEMINI_QUOTA_EXHAUSTED_MESSAGE,
    PROMPT_REQUIRED_MESSAGE,
    PROGRESSIVE_MAX_BLOCKS,
    ConfigMismatchError,
    GenerationConfig,
    load_generation_fallback_chain,
    load_generation_config,
    public_generation_settings,
    update_generation_settings,
    validate_generation_config,
)
from workbench.formal_planning import (
    ensure_formal_planning,
)

__all__ = [
    "DEFAULT_DEEPSEEK_BASE_URL",
    "DEFAULT_GENERATION_PROVIDER",
    "DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED",
    "DEFAULT_SETTINGS_PATH",
    "DEFAULT_SILICONFLOW_BASE_URL",
    "DEFAULT_XIAOMI_BASE_URL",
    "GEMINI_ENDPOINT",
    "GEMINI_QUOTA_EXHAUSTED_MESSAGE",
    "PROMPT_REQUIRED_MESSAGE",
    "PROGRESSIVE_MAX_BLOCKS",
    "GenerationConfig",
    "ConfigMismatchError",
    "call_model_generate",
    "call_slide_model_generate",
    "call_model_generate_with_fallback",
    "clear_generation_limit_for_config",
    "probe_connection_generation",
    "user_facing_generation_error",
    "generation_limit_reason",
    "is_quota_or_rate_limit_error",
    "last_generation_trace",
    "load_generation_fallback_chain",
    "load_generation_config",
    "public_generation_settings",
    "reset_generation_limit_state",
    "sanitize_generation_error_message",
    "sanitize_generation_trace",
    "update_generation_settings",
    "validate_generation_config",
]


_GENERATION_TRACE: ContextVar[tuple[dict, ...]] = ContextVar("workbench_generation_trace", default=())
_GENERATION_LIMIT_STATE: dict[tuple[str, int], datetime] = {}
SENSITIVE_TRACE_KEYS = {"api_key", "apikey", "authorization", "token", "secret"}
GENERATION_ERROR_LIMIT = 900
SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{8,}\b"),
    re.compile(r"([?&](?:api_key|key|token|access_token)=)[^&\s]+", re.I),
)
CONTENT_HANDLING_LABELS = {
    "preserve": "保持原文",
    "polish": "适度润色",
    "expand": "AI 扩写",
}
CONTENT_HANDLING_GUIDANCE = {
    "preserve": "Preserve the user's original wording as much as possible; only trim obvious repetition when needed for fit.",
    "polish": "preserve the original meaning, but improve phrasing, hierarchy, and slide-ready concision where useful.",
    "expand": "Preserve the original intent and expand it into a fuller, clearer consulting-style slide when the brief is thin.",
}
PAGE_STYLE_LABELS = {
    "business_simple": "商务简洁",
    "software_consulting": "软件咨询",
}
PAGE_STYLE_GUIDANCE = {
    "business_simple": "Use a clean business style: restrained palette, clear hierarchy, direct structure, and minimal decoration.",
    "software_consulting": "Use a software consulting style: product/workflow framing, implementation logic, capability maps, and crisp operational labels.",
}


def _normalized_content_handling(value: object) -> str:
    key = str(value or "polish").strip()
    return key if key in CONTENT_HANDLING_LABELS else "polish"


def _normalized_page_style(value: object) -> str:
    key = str(value or "business_simple").strip()
    return key if key in PAGE_STYLE_LABELS else "business_simple"


def sanitize_generation_error_message(message: object, limit: int = GENERATION_ERROR_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[redacted]" if match.lastindex else "[redacted]", text)
    if len(text) > limit:
        text = text[: max(1, limit - 3)].rstrip() + "..."
    return text


def _sanitize_generation_trace_value(value: object) -> object:
    if isinstance(value, str):
        return sanitize_generation_error_message(value)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_generation_trace_value(item)
            for key, item in value.items()
            if str(key).strip().lower() not in SENSITIVE_TRACE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_generation_trace_value(item) for item in value[:20]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return sanitize_generation_error_message(value)


def sanitize_generation_trace(trace: object) -> list[dict]:
    if not isinstance(trace, list):
        return []
    sanitized: list[dict] = []
    for item in trace[-20:]:
        if not isinstance(item, dict):
            continue
        sanitized_item = _sanitize_generation_trace_value(item)
        if isinstance(sanitized_item, dict):
            sanitized.append(sanitized_item)
    return sanitized


def _reset_generation_trace() -> None:
    _GENERATION_TRACE.set(())


def _trace_generation_event(**event: object) -> None:
    safe_event = sanitize_generation_trace([event])[0] if event else {}
    _GENERATION_TRACE.set((*_GENERATION_TRACE.get(()), safe_event))


def last_generation_trace() -> list[dict]:
    return sanitize_generation_trace([dict(item) for item in _GENERATION_TRACE.get(())])


def _trace_has_limit_for_provider(provider: str) -> bool:
    return any(
        isinstance(item, dict)
        and item.get("provider") == provider
        and item.get("event") == "limit_cooldown_recorded"
        for item in _GENERATION_TRACE.get(())
    )


def local_generation_now() -> datetime:
    return datetime.now()


def reset_generation_limit_state() -> None:
    _GENERATION_LIMIT_STATE.clear()


def clear_generation_limit_for_config(config: GenerationConfig) -> None:
    """Drop cooldown entries for this config's keys so a manual connection probe always issues a fresh request."""
    keys = config.effective_api_keys() or ("",)
    for key_index, _key in enumerate(keys, start=1):
        _GENERATION_LIMIT_STATE.pop((config.provider, key_index), None)


def generation_limit_reason(error: BaseException | str) -> str:
    folded = str(error or "").lower()
    if any(token in folded for token in ("resource_exhausted", "quota", "insufficient_quota")):
        return "quota"
    if any(token in folded for token in ("http 429", "rate limit", "rate-limits", "too many requests")):
        return "rate_limit"
    return ""


def generation_permission_reason(error: BaseException | str) -> str:
    folded = str(error or "").lower()
    if "http 403" in folded or "permission_denied" in folded or "denied access" in folded or "forbidden" in folded:
        return "provider_permission_denied"
    return ""


def generation_busy_reason(error: BaseException | str) -> str:
    folded = str(error or "").lower()
    if any(
        token in folded
        for token in (
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "unavailable",
            "temporarily unavailable",
            "high demand",
            "模型服务临时繁忙",
            "妯″瀷鏈嶅姟涓存椂绻佸繖",
        )
    ):
        return "provider_busy"
    return ""


def generation_fallback_reason(error: BaseException | str) -> str:
    return generation_limit_reason(error)


def is_quota_or_rate_limit_error(error: BaseException | str) -> bool:
    return bool(generation_limit_reason(error))


def _next_local_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _limit_reset_at(provider: str, reason: str, now: datetime) -> datetime:
    if provider == "google" and reason == "quota":
        return _next_local_midnight(now)
    if reason == "quota":
        return now + timedelta(minutes=15)
    return now + timedelta(minutes=5)


def _prune_generation_limit_state(now: datetime | None = None) -> None:
    current = now or local_generation_now()
    expired = [key for key, reset_at in _GENERATION_LIMIT_STATE.items() if reset_at <= current]
    for key in expired:
        _GENERATION_LIMIT_STATE.pop(key, None)


def _record_generation_limit(provider: str, key_index: int, reason: str) -> None:
    if not reason:
        return
    now = local_generation_now()
    reset_at = _limit_reset_at(provider, reason, now)
    _GENERATION_LIMIT_STATE[(provider, int(key_index or 1))] = reset_at
    _trace_generation_event(
        event="limit_cooldown_recorded",
        provider=provider,
        key_index=int(key_index or 1),
        reason=reason,
        reset_at=reset_at.isoformat(timespec="seconds"),
    )


def _record_config_limit(config: GenerationConfig, reason: str) -> None:
    keys = config.effective_api_keys() or ("",)
    for key_index, _key in enumerate(keys, start=1):
        _record_generation_limit(config.provider, key_index, reason)


def _available_config_key_indexes(config: GenerationConfig) -> list[int]:
    _prune_generation_limit_state()
    keys = config.effective_api_keys()
    return [
        key_index
        for key_index, _key in enumerate(keys, start=1)
        if (config.provider, key_index) not in _GENERATION_LIMIT_STATE
    ]


def _has_available_config_key(config: GenerationConfig) -> bool:
    return bool(config.effective_api_keys()) and bool(_available_config_key_indexes(config))


def user_facing_generation_error(error: BaseException | str) -> str:
    message = str(error or "").strip()
    if isinstance(error, ConfigMismatchError) or "模型配置不一致" in message:
        return sanitize_generation_error_message(message)
    if generation_permission_reason(message):
        return "模型权限不可用。当前模型服务拒绝访问，请检查模型配置后再重试。"
    if is_quota_or_rate_limit_error(message):
        return GEMINI_QUOTA_EXHAUSTED_MESSAGE
    folded = message.lower()
    if "not valid xml" in folded or "did not contain a complete svg" in folded:
        return "本页生成内容格式异常，请重新生成本页。"
    if (
        "urlopen error" in folded
        or "unexpected_eof" in folded
        or "ssl:" in folded
        or "timed out" in folded
        or "connection reset" in folded
        or "connection aborted" in folded
        or "http 500" in folded
        or "http 502" in folded
        or "http 503" in folded
        or "http 504" in folded
        or "unavailable" in folded
        or "high demand" in folded
    ):
        return "模型服务临时繁忙，请稍后重新生成本页。"
    return sanitize_generation_error_message(message) or "自动生成失败，请稍后重试。"


def _auto_generation_retry_reason(error: BaseException | str) -> str:
    folded = str(error or "").lower()
    if generation_busy_reason(error):
        return "provider_busy"
    if "not valid xml" in folded or "did not contain a complete svg" in folded:
        return "svg_parse_error"
    return ""


def _auto_generation_failure_reason(error: BaseException | str) -> str:
    permission_reason = generation_permission_reason(error)
    if permission_reason:
        return permission_reason
    limit_reason = generation_limit_reason(error)
    if limit_reason == "quota":
        return "provider_quota"
    if limit_reason == "rate_limit":
        return "provider_rate_limit"
    return _auto_generation_retry_reason(error) or generation_fallback_reason(error)


SYSTEMIC_BATCH_PAUSE_REASONS = {
    "provider_quota",
    "provider_rate_limit",
    "provider_permission_denied",
}
TRANSIENT_BATCH_PAUSE_REASONS = {"provider_busy", "provider_timeout"}
TRANSIENT_BATCH_PAUSE_THRESHOLD = 3


def _slide_failure_code(project_path: Path, slide_id: int) -> str:
    status = load_status(project_path) or {}
    for slide in status.get("slides", []):
        if isinstance(slide, dict) and int(slide.get("slide_id") or 0) == int(slide_id):
            return str(slide.get("last_error_code") or "")
    return ""


def _block_remaining_slides_after_pause(project_path: Path, slide_ids: list[int], reason_code: str, message: str) -> list[int]:
    if not slide_ids:
        return []
    status = load_status(project_path) or {}
    slides = status.get("slides") if isinstance(status.get("slides"), list) else []
    blocked: list[int] = []
    now = now_iso()
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        slide_id = int(slide.get("slide_id") or 0)
        if slide_id not in slide_ids:
            continue
        slide_no = int(slide.get("slide_no") or slide_id)
        target = slide_svg_path(project_path, slide_no)
        if slide.get("has_svg") and target.exists():
            continue
        slide["status"] = "blocked"
        slide["has_svg"] = bool(target.exists())
        slide["qa_status"] = "not_run"
        slide["last_error"] = message
        slide["last_error_code"] = reason_code
        slide["generation_phase"] = "blocked"
        slide["generation_completed_at"] = now
        slide["lock_updated_at"] = now
        blocked.append(slide_id)
    if blocked:
        status["deck_status"] = "paused"
        status["generation_pause_reason"] = reason_code
        status["generation_pause_message"] = message
        add_event(status, "api_auto_generate_paused", f"Batch generation paused after {reason_code}; blocked pages: {', '.join(map(str, blocked))}.")
        save_status(project_path, status)
    return blocked


PALE_DECORATIVE_TEXT_FILLS = {"#FCE8EB", "#FBE7EB", "#F8DDE4", "#F7D6DF", "#F2D9DE"}


def _text_content(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def _font_size_px(element: ET.Element) -> float:
    raw = str(element.attrib.get("font-size") or "").strip().lower().replace("px", "")
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _is_low_value_micro_label(element: ET.Element) -> bool:
    text = _text_content(element)
    if not text or _font_size_px(element) > 10:
        return False
    if re.fullmatch(r"\d{1,3}\s*%", text):
        return True
    if re.fullmatch(r"\d{1,2}\s*月", text):
        return True
    if re.fullmatch(r"[A-Z][A-Z0-9 .:_/-]{1,24}", text):
        return True
    if len(text) <= 8 and any(token in text for token in ("率", "趋势", "状态", "实时", "闭环")):
        return True
    return False


def _prune_excessive_decorative_text(svg: str, *, max_text_nodes: int = 28) -> str:
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    if str(root.tag).startswith("{http://www.w3.org/2000/svg}"):
        ET.register_namespace("", "http://www.w3.org/2000/svg")
    text_nodes = [element for element in root.iter() if str(element.tag).lower().endswith("text")]
    if len(text_nodes) <= max_text_nodes:
        return svg
    parent_by_child = {child: parent for parent in root.iter() for child in list(parent)}
    removable = [element for element in text_nodes if _is_low_value_micro_label(element)]
    removed = 0
    for element in removable:
        if len(text_nodes) - removed <= max_text_nodes:
            break
        parent = parent_by_child.get(element)
        if parent is None:
            continue
        parent.remove(element)
        removed += 1
    if removed <= 0:
        return svg
    return ET.tostring(root, encoding="unicode")


def _ensure_full_canvas_background_rect(svg: str) -> str:
    rect_pattern = re.compile(r"<rect\b(?P<attrs>[^>]*)/?>", flags=re.I)
    for match in rect_pattern.finditer(svg):
        attrs = match.group("attrs")
        x = re.search(r'\bx="(?P<value>[^"]+)"', attrs)
        y = re.search(r'\by="(?P<value>[^"]+)"', attrs)
        width = re.search(r'\bwidth="(?P<value>[^"]+)"', attrs)
        height = re.search(r'\bheight="(?P<value>[^"]+)"', attrs)
        if (
            (x is None or x.group("value") in {"0", "0.0"})
            and (y is None or y.group("value") in {"0", "0.0"})
            and width is not None
            and height is not None
            and width.group("value") in {"1280", "1280.0", "100%"}
            and height.group("value") in {"720", "720.0", "100%"}
        ):
            return svg

    open_svg = re.search(r"<svg\b[^>]*>", svg, flags=re.I)
    if not open_svg:
        return svg
    style_bg = re.search(r"background(?:-color)?\s*:\s*(?P<fill>#[0-9A-Fa-f]{6})", open_svg.group(0), flags=re.I)
    fill = style_bg.group("fill") if style_bg else "#FFFFFF"
    background = f'\n  <rect x="0" y="0" width="1280" height="720" fill="{fill}" />'
    return svg[: open_svg.end()] + background + svg[open_svg.end() :]


def _repair_common_svg_generation_artifacts(svg: str) -> str:
    svg = re.sub(r"(?<!<)/(text|tspan)>", r"</\1>", svg)
    svg = re.sub(r"(<text\b[^>]*>)\s+(<tspan\b)", r"\1\2", svg)
    svg = re.sub(r"(</tspan>)\s+(<tspan\b)", r"\1\2", svg)
    svg = re.sub(r"(</tspan>)\s+(</text>)", r"\1\2", svg)
    svg = re.sub(r"(<g\b[^>]*?)\s+opacity=\"[^\"]+\"", r"\1", svg, flags=re.I)
    svg = re.sub(r'fill="url\(\#[A-Za-z0-9_\-]+\)"', 'fill="#932141"', svg)

    def flatten_tinted_accent_shape(match: re.Match[str]) -> str:
        tag = match.group(0)
        fill_match = re.search(r'fill="(?P<fill>#(?:932141|800020))"', tag, flags=re.I)
        opacity_match = re.search(r'\s*(?:fill-)?opacity="(?P<opacity>0(?:\.\d+)?|1(?:\.0+)?)"', tag, flags=re.I)
        if not fill_match or not opacity_match:
            return tag
        try:
            opacity = float(opacity_match.group("opacity"))
        except ValueError:
            return tag
        if opacity <= 0.25:
            tag = tag[: fill_match.start()] + 'fill="#FFF0F2"' + tag[fill_match.end() :]
            tag = tag[: opacity_match.start()] + tag[opacity_match.end() :]
        return tag

    svg = re.sub(r"<(?:rect|path|circle|ellipse)\b[^>]*>", flatten_tinted_accent_shape, svg, flags=re.I)

    def darken_pale_numeric_text(match: re.Match[str]) -> str:
        attrs = match.group("attrs")
        fill_match = re.search(r'fill="(?P<fill>#[0-9A-Fa-f]{6})"', attrs)
        if not fill_match or fill_match.group("fill").upper() not in PALE_DECORATIVE_TEXT_FILLS:
            return match.group(0)
        return f'<text {attrs[: fill_match.start()]}fill="#932141"{attrs[fill_match.end() :]}>{match.group("body")}</text>'

    svg = re.sub(
        r'<text\s+(?P<attrs>[^>]*)>(?P<body>\s*\d{1,2}\s*)</text>',
        darken_pale_numeric_text,
        svg,
        flags=re.I,
    )
    svg = re.sub(
        r'(<text\b[^>]*?)fill="#D8E2F2"([^>]*>\s*\|\s*</text>)',
        r'\1fill="#667085"\2',
        svg,
        flags=re.I,
    )
    svg = re.sub(
        r'(<text\b[^>]*?)fill="#E4E7EC"([^>]*>\s*\|\s*</text>)',
        r'\1fill="#667085"\2',
        svg,
        flags=re.I,
    )
    svg = _add_missing_text_anchor_from_first_tspan(svg)
    svg = _ensure_full_canvas_background_rect(svg)
    svg = _prune_excessive_decorative_text(svg)
    return svg


def _add_missing_text_anchor_from_first_tspan(svg: str) -> str:
    def patch(match: re.Match[str]) -> str:
        attrs = match.group("attrs").strip()
        body = match.group("body")
        if re.search(r'\bx=', attrs) and re.search(r'\by=', attrs):
            return match.group(0)
        first_tspan = re.search(r"<tspan\b(?P<attrs>[^>]*)>", body, flags=re.I)
        if not first_tspan:
            return match.group(0)
        tspan_attrs = first_tspan.group("attrs")
        x_match = re.search(r'\bx="(?P<x>[^"]+)"', tspan_attrs)
        y_match = re.search(r'\by="(?P<y>[^"]+)"', tspan_attrs)
        if not x_match or not y_match:
            return match.group(0)
        prefix = ""
        if not re.search(r'\bx=', attrs):
            prefix += f' x="{x_match.group("x")}"'
        if not re.search(r'\by=', attrs):
            prefix += f' y="{y_match.group("y")}"'
        return f"<text{prefix} {attrs}>{body}</text>"

    return re.sub(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", patch, svg, flags=re.I | re.S)


def extract_svg(text: str) -> str:
    content = text.strip()
    fenced = re.search(r"```(?:svg|xml)?\s*(?P<body>.*?)```", content, re.S | re.I)
    if fenced:
        content = fenced.group("body").strip()
    match = re.search(r"<svg\b.*?</svg>", content, re.S | re.I)
    if not match:
        raise ValueError("Gemini response did not contain a complete SVG.")
    svg = match.group(0).strip()
    if "<foreignObject" in svg:
        raise ValueError("Generated SVG contains foreignObject, which is not allowed.")
    if "viewBox" not in svg[:300]:
        svg = svg.replace("<svg", '<svg viewBox="0 0 1280 720"', 1)
    svg = _repair_common_svg_generation_artifacts(svg)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise ValueError(f"Generated SVG is not valid XML: {exc}") from exc
    if not str(root.tag).lower().endswith("svg"):
        raise ValueError("Generated content root is not an SVG element.")
    for element in root.iter():
        if str(element.tag).lower().endswith("style"):
            raise ValueError("Generated SVG contains <style>, which is not allowed.")
        if "class" in element.attrib:
            raise ValueError("Generated SVG contains class attributes, which are not allowed.")
    return svg + "\n"


def _validate_attempt_limits(
    max_attempts_per_key: int,
    max_total_attempts: int | None,
) -> None:
    if isinstance(max_attempts_per_key, bool) or not isinstance(max_attempts_per_key, int):
        raise ValueError("max_attempts_per_key must be an integer")
    if max_attempts_per_key <= 0:
        raise ValueError("max_attempts_per_key must be at least 1")
    if max_total_attempts is not None:
        if isinstance(max_total_attempts, bool) or not isinstance(max_total_attempts, int):
            raise ValueError("max_total_attempts must be an integer or None")
        if max_total_attempts <= 0:
            raise ValueError("max_total_attempts must be at least 1")


def call_gemini_generate(
    prompt: str,
    config: GenerationConfig,
    timeout: int = 90,
    max_attempts_per_key: int = 3,
    max_total_attempts: int | None = None,
) -> str:
    _validate_attempt_limits(max_attempts_per_key, max_total_attempts)
    if not config.configured():
        raise ValueError("Google API key is not configured. Set GEMINI_API_KEY or configure api_key_env in workbench/settings.local.json.")
    request_body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": 32768},
        }
    ).encode("utf-8")
    payload = None
    last_limit_error = ""
    total_attempts = 0
    keys = config.effective_api_keys()
    available_key_indexes = _available_config_key_indexes(config)
    if not available_key_indexes:
        raise RuntimeError("Gemini request skipped because all Google keys are cooling down after quota/rate limits.")
    for key_index in available_key_indexes:
        api_key = keys[key_index - 1]
        for attempt in range(1, max_attempts_per_key + 1):
            if max_total_attempts is not None and total_attempts >= max_total_attempts:
                break
            total_attempts += 1
            _trace_generation_event(
                event="request",
                provider="google",
                model=config.model,
                key_index=key_index,
                key_count=len(keys),
                attempt=attempt,
            )
            request = urllib.request.Request(
                GEMINI_ENDPOINT.format(model=config.model),
                data=request_body,
                headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                _trace_generation_event(
                    event="success",
                    provider="google",
                    model=config.model,
                    key_index=key_index,
                    key_count=len(keys),
                    attempt=attempt,
                )
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[-1200:] if exc.fp else ""
                limit_reason = generation_limit_reason(f"HTTP {exc.code}: {detail}")
                if limit_reason:
                    last_limit_error = f"Gemini request failed with HTTP {exc.code}: {detail}"
                    _record_generation_limit("google", key_index, limit_reason)
                    _trace_generation_event(
                        event="quota_or_rate_limit",
                        provider="google",
                        model=config.model,
                        key_index=key_index,
                        key_count=len(keys),
                        attempt=attempt,
                    )
                    break
                permission_reason = generation_permission_reason(f"HTTP {exc.code}: {detail}")
                if permission_reason:
                    last_limit_error = f"Gemini request failed with HTTP {exc.code}: {detail}"
                    _record_generation_limit("google", key_index, permission_reason)
                    _trace_generation_event(
                        event="provider_permission_denied",
                        provider="google",
                        model=config.model,
                        key_index=key_index,
                        key_count=len(keys),
                        attempt=attempt,
                    )
                    break
                if (
                    exc.code in {500, 502, 503, 504}
                    and attempt < max_attempts_per_key
                    and (max_total_attempts is None or total_attempts < max_total_attempts)
                ):
                    time.sleep(attempt * 2)
                    continue
                raise RuntimeError(f"Gemini request failed with HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
                if (
                    attempt >= max_attempts_per_key
                    or (max_total_attempts is not None and total_attempts >= max_total_attempts)
                ):
                    raise RuntimeError(f"Gemini request failed after retries: {exc}") from exc
                time.sleep(attempt)
        if max_total_attempts is not None and total_attempts >= max_total_attempts:
            if last_limit_error:
                break
        if payload is not None:
            break
    if payload is None:
        if last_limit_error:
            raise RuntimeError(last_limit_error)
        raise RuntimeError("Gemini request failed without a response payload.")
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise RuntimeError("Gemini response did not include text content.")
    return text


def openai_compatible_chat_endpoint(config: GenerationConfig) -> str:
    if config.provider == "deepseek":
        default_base = DEFAULT_DEEPSEEK_BASE_URL
    elif config.provider == "xiaomi":
        default_base = DEFAULT_XIAOMI_BASE_URL
    else:
        default_base = DEFAULT_SILICONFLOW_BASE_URL
    base_url = (config.base_url or default_base).rstrip("/")
    return f"{base_url}/chat/completions"


def provider_display_label(provider: str) -> str:
    if provider == "deepseek":
        return "DeepSeek"
    if provider == "xiaomi":
        return "Xiaomi"
    if provider == "siliconflow":
        return "SiliconFlow"
    return "Google"


def call_openai_compatible_generate(
    prompt: str,
    config: GenerationConfig,
    timeout: int = 90,
    max_attempts_per_key: int = 3,
    max_total_attempts: int | None = None,
    disable_thinking: bool = False,
) -> str:
    _validate_attempt_limits(max_attempts_per_key, max_total_attempts)
    provider_label = provider_display_label(config.provider)
    if not config.configured():
        raise ValueError(f"{provider_label} API key is not configured. Set env var or configure {config.provider}_api_key_env in workbench/settings.local.json.")
    available_key_indexes = _available_config_key_indexes(config)
    if not available_key_indexes:
        raise RuntimeError(f"{provider_label} request skipped because the configured key is cooling down after quota/rate limits.")
    request_payload = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.45,
        "max_tokens": 32768,
        "stream": False,
    }
    if disable_thinking and config.provider == "deepseek":
        request_payload["thinking"] = {"type": "disabled"}
    request_body = json.dumps(request_payload).encode("utf-8")
    payload = None
    last_limit_error = ""
    total_attempts = 0
    keys = config.effective_api_keys()
    for key_index in available_key_indexes:
        api_key = keys[key_index - 1]
        for attempt in range(1, max_attempts_per_key + 1):
            if max_total_attempts is not None and total_attempts >= max_total_attempts:
                break
            total_attempts += 1
            _trace_generation_event(
                event="request",
                provider=config.provider,
                model=config.model,
                key_index=key_index,
                key_count=len(keys),
                attempt=attempt,
            )
            request = urllib.request.Request(
                openai_compatible_chat_endpoint(config),
                data=request_body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                _trace_generation_event(
                    event="success",
                    provider=config.provider,
                    model=config.model,
                    key_index=key_index,
                    key_count=len(keys),
                    attempt=attempt,
                )
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[-1200:]
                limit_reason = generation_limit_reason(f"HTTP {exc.code}: {detail}")
                if limit_reason:
                    last_limit_error = f"{provider_label} request failed with HTTP {exc.code}: {detail}"
                    _record_generation_limit(config.provider, key_index, limit_reason)
                    _trace_generation_event(
                        event="quota_or_rate_limit",
                        provider=config.provider,
                        model=config.model,
                        key_index=key_index,
                        key_count=len(keys),
                        attempt=attempt,
                    )
                    break
                permission_reason = generation_permission_reason(f"HTTP {exc.code}: {detail}")
                if permission_reason:
                    last_limit_error = f"{provider_label} request failed with HTTP {exc.code}: {detail}"
                    _record_generation_limit(config.provider, key_index, permission_reason)
                    _trace_generation_event(
                        event="provider_permission_denied",
                        provider=config.provider,
                        model=config.model,
                        key_index=key_index,
                        key_count=len(keys),
                        attempt=attempt,
                    )
                    break
                if (
                    exc.code in {500, 502, 503, 504}
                    and attempt < max_attempts_per_key
                    and (max_total_attempts is None or total_attempts < max_total_attempts)
                ):
                    time.sleep(attempt * 2)
                    continue
                raise RuntimeError(f"{provider_label} request failed with HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected) as exc:
                if (
                    attempt >= max_attempts_per_key
                    or (max_total_attempts is not None and total_attempts >= max_total_attempts)
                ):
                    raise RuntimeError(f"{provider_label} request failed after retries: {exc}") from exc
                time.sleep(attempt)
        if max_total_attempts is not None and total_attempts >= max_total_attempts:
            if last_limit_error:
                break
        if payload is not None:
            break
    if payload is None:
        if last_limit_error:
            raise RuntimeError(last_limit_error)
        raise RuntimeError(f"{provider_label} request failed without a response payload.")
    choices = payload.get("choices") if isinstance(payload, dict) else []
    if not choices:
        raise RuntimeError(f"{provider_label} response did not include choices.")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    text = str(message.get("content") or choices[0].get("text") or "").strip()
    if not text:
        raise RuntimeError(f"{provider_label} response did not include text content.")
    return text


def call_model_generate(
    prompt: str,
    config: GenerationConfig,
    timeout: int = 90,
    max_attempts_per_key: int = 3,
    max_total_attempts: int | None = None,
    disable_thinking: bool = False,
) -> str:
    _validate_attempt_limits(max_attempts_per_key, max_total_attempts)
    validate_generation_config(config)
    if config.provider in {"xiaomi", "siliconflow", "deepseek", "openai_compatible"}:
        request_options = {
            "timeout": timeout,
            "max_attempts_per_key": max_attempts_per_key,
            "max_total_attempts": max_total_attempts,
        }
        if disable_thinking:
            request_options["disable_thinking"] = True
        return call_openai_compatible_generate(prompt, config, **request_options)
    return call_gemini_generate(
        prompt,
        config,
        timeout=timeout,
        max_attempts_per_key=max_attempts_per_key,
        max_total_attempts=max_total_attempts,
    )


def call_slide_model_generate(prompt: str, config: GenerationConfig) -> str:
    return call_model_generate(prompt, config, disable_thinking=True)


CONNECTION_PROBE_PROMPT = "Reply with the single word OK."


def probe_connection_generation(
    provider: str,
    model: str,
    api_key: str,
    base_url: str = "",
    timeout: int = 30,
) -> str:
    """Issue one minimal real generation call so a connection test reflects true generate access.

    A model-list probe returns 200 even when the project is denied generate access, so the
    connection test must exercise the same generateContent/chat endpoint real generation uses.
    Raises on any failure; the caller maps the error to a user-facing message.
    """
    config = GenerationConfig(
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        api_key_source="connection_test",
        model_source="connection_test",
    )
    clear_generation_limit_for_config(config)
    return call_model_generate(CONNECTION_PROBE_PROMPT, config, timeout=timeout)


def call_model_generate_with_fallback(prompt: str, config: GenerationConfig, timeout: int = 90) -> str:
    """Generate with local provider fallback for quota or rate-limit failures."""
    validate_generation_config(config)
    _reset_generation_trace()
    chain = load_generation_fallback_chain()
    if not chain:
        chain = (config,)
    last_fallback_error: BaseException | None = None
    last_fallback_reason = ""
    attempted_provider = False
    for index, candidate in enumerate(chain):
        validate_generation_config(candidate)
        if not _has_available_config_key(candidate):
            next_provider = chain[index + 1].provider if index + 1 < len(chain) else ""
            _trace_generation_event(
                event="fallback_next_provider" if next_provider else "fallback_exhausted",
                provider=candidate.provider,
                model=candidate.model,
                reason="limit_cooldown_active",
                next_provider=next_provider,
            )
            continue
        attempted_provider = True
        try:
            return call_model_generate(prompt, candidate, timeout=timeout)
        except Exception as exc:
            fallback_reason = generation_fallback_reason(exc)
            if not fallback_reason:
                raise
            last_fallback_error = exc
            last_fallback_reason = fallback_reason
            if not _trace_has_limit_for_provider(candidate.provider):
                _record_config_limit(candidate, fallback_reason)
            next_provider = chain[index + 1].provider if index + 1 < len(chain) else ""
            _trace_generation_event(
                event="fallback_next_provider" if next_provider else "fallback_exhausted",
                provider=candidate.provider,
                model=candidate.model,
                reason=fallback_reason,
                next_provider=next_provider,
            )
            if not next_provider:
                break
            continue
    if last_fallback_error is not None:
        if last_fallback_reason == "provider_permission_denied":
            raise RuntimeError("All configured generation providers denied access.") from last_fallback_error
        if last_fallback_reason == "provider_busy":
            raise RuntimeError("All configured generation providers are temporarily unavailable.") from last_fallback_error
        raise RuntimeError("All configured generation providers exhausted quota/rate limits.") from last_fallback_error
    if not attempted_provider:
        raise RuntimeError("All configured generation providers are cooling down after quota/rate limits.")
    return call_model_generate(prompt, config, timeout=timeout)


def _read_context_file(path: Path, limit: int = 8000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:limit]


def _read_slide_task_context(path: Path, limit: int = 7000) -> str:
    context = _read_context_file(path, limit)
    if not context:
        return ""
    return re.sub(
        r"(?ms)^## Slide Brief\s+.*?(?=^## |\Z)",
        "## Slide Brief\nUse the original slide brief already provided above.\n\n",
        context,
    )


def _read_slide_payload(path: Path, slide_id: int) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return {}
    for item in slides:
        if not isinstance(item, dict):
            continue
        current_id = item.get("slide_id", item.get("id"))
        if str(current_id) == str(slide_id):
            return item
    return {}


def _read_slide_context(
    path: Path,
    slide_id: int,
    limit: int = 8000,
    *,
    excluded_keys: frozenset[str] = frozenset(),
) -> str:
    if not path.exists():
        return ""
    raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:limit]
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return raw[:limit]
    for item in slides:
        if not isinstance(item, dict):
            continue
        current_id = item.get("slide_id", item.get("id"))
        if str(current_id) == str(slide_id):
            context_item = {key: value for key, value in item.items() if key not in excluded_keys}
            return json.dumps(context_item, ensure_ascii=False, indent=2)[:limit]
    return raw[:limit]


def _normalized_page_type(raw: object) -> str:
    page_type = str(raw or "").strip().lower()
    return page_type or "content"


def _visual_intensity_guidance(page_type: str) -> str:
    if page_type in {"cover", "section"}:
        return (
            "- Visual style target: high-polish hero page. You may use one controlled gradient area, soft shadow layers, and subtle translucent background numerals.\n"
            "- Keep typography bold and focal, but do not let decorative effects reduce text contrast or readability."
        )
    if page_type in {"toc", "outline"}:
        return (
            "- Visual style target: structured navigation page. Use restrained accents and spacing rhythm; avoid heavy decorative effects that distract from information scanning.\n"
            "- If using gradient/shadow/transparency, keep it minimal and secondary to hierarchy clarity."
        )
    if page_type in {"closing", "conclusion", "summary"}:
        return (
            "- Visual style target: concise concluding page. Moderate emphasis effects are allowed (soft gradient, light shadow, translucent emphasis) only around the key takeaway.\n"
            "- Keep layout clean and focused so the conclusion remains immediately readable."
        )
    return (
        "- Visual style target: content/business page. Prioritize structure and readability over decoration.\n"
        "- Avoid effect stacking: no multiple heavy gradients/shadows or large translucent overlays behind dense text."
    )


def _format_task_list(values: object, limit: int = 4) -> str:
    if not isinstance(values, list):
        return _truncate_text(values, 180)
    items = [_truncate_text(item, 140) for item in values[:limit] if str(item or "").strip()]
    return " | ".join(items)


def _format_task_map(values: object) -> str:
    if not isinstance(values, dict):
        return _truncate_text(values, 180)
    parts = [
        f"{key}={_truncate_text(value, 80)}"
        for key, value in values.items()
        if str(value or "").strip()
    ]
    return ", ".join(parts)


def _compact_page_task_sheet(
    project_path: Path,
    slide_id: int,
    *,
    include_structural_fields: bool = True,
) -> str:
    visual_item = _read_slide_payload(project_path / "slide_visual_plan.json", slide_id)
    visual_contract = visual_item.get("visual_contract") if isinstance(visual_item.get("visual_contract"), dict) else {}
    page_type_decision = (
        visual_item.get("page_type_decision")
        if isinstance(visual_item.get("page_type_decision"), dict)
        else {}
    )
    prompt_pattern = (
        visual_item.get("page_prompt_pattern")
        if isinstance(visual_item.get("page_prompt_pattern"), dict)
        else {}
    )
    execution_policy = (
        visual_item.get("execution_policy")
        if isinstance(visual_item.get("execution_policy"), dict)
        else {}
    )
    density_budget = visual_item.get("density_budget") or visual_contract.get("density_budget")
    proof_object = visual_item.get("proof_object") or visual_item.get("evidence_artifact_plan")
    conclusion_source = str(visual_item.get("conclusion_source") or "").strip()
    conclusion_confidence = str(visual_item.get("conclusion_confidence") or "").strip()
    conclusion_provenance = " / ".join(
        value for value in (conclusion_source, conclusion_confidence) if value
    )
    acceptance_criteria = visual_item.get("acceptance_criteria")
    must_answer = visual_contract.get("must_answer_question")
    lines = [
        "Priority order:",
        "1. Hard export/readability/safe-area rules are non-negotiable.",
        "2. User explicit requirements outrank page task sheet defaults.",
        "3. Page task sheet guides content selection, layout direction, and density.",
        "4. Global/default style suggestions are last.",
        "Acceptance Criteria are internal expression checks only.",
        (
            "They are not the Core Conclusion, not default on-canvas copy, and must not be copied "
            "into the slide title, labels, or body text."
        ),
        (
            "Compatibility warning: title-fallback / low is context for old projects only; "
            "treat it as a drafting hint, not as a verified business conclusion."
        ),
    ]
    if not visual_item:
        lines.append("Page task sheet: no slide_visual_plan entry was found; rely on the original brief and blueprint.")
        return "\n".join(lines)

    if str(page_type_decision.get("page_type") or "") == "supplier_penetration":
        proof_objects = visual_item.get("proof_objects")
        if proof_objects:
            lines.append(
                f"- Source-backed proof objects (closed business set): {_format_task_list(proof_objects)}"
            )
        evidence_terms = page_type_decision.get("evidence_terms")
        evidence = evidence_terms if isinstance(evidence_terms, list) else []
        endpoints: list[str] = []
        actions: list[str] = []
        allowed_actions = ("下发", "汇总", "回传", "上传", "提交", "审核", "退回", "整改", "流转", "传递")
        for value in evidence:
            term = str(value or "").strip()
            if not term:
                continue
            if re.fullmatch(r"T(?:\d+|N)", term, flags=re.I):
                endpoint = term.upper()
                if endpoint not in endpoints:
                    endpoints.append(endpoint)
            elif term in allowed_actions and term not in actions:
                actions.append(term)
        if endpoints:
            lines.append(f"- Allowed supplier endpoint labels: {' | '.join(endpoints)}")
        if actions:
            lines.append(f"- Allowed supplier action terms: {' | '.join(actions)}")
        lines.append(
            "- Supplier copy lock: Do not expand endpoint labels into role or tier names, "
            "and do not infer counterpart actions. Leave unused space instead of adding copy."
        )

    field_specs = [
        ("Core conclusion", visual_item.get("core_conclusion")),
        ("Conclusion source/confidence", conclusion_provenance),
        ("Supporting claims", _format_task_list(visual_item.get("supporting_claims"))),
        ("Evidence anchors", _format_task_list(visual_item.get("evidence"))),
        ("Source references", _format_task_list(visual_item.get("source_refs"))),
        ("Proof Object", _format_task_map(proof_object)),
        ("Dominant object", visual_item.get("dominant_object")),
        ("Layout objective", visual_item.get("layout_objective") or visual_item.get("composition_intent")),
        ("Must answer", must_answer),
        ("Acceptance Criteria (internal only)", _format_task_list(acceptance_criteria)),
        ("Semantic visual intent", visual_item.get("visual_intent") or visual_contract.get("visual_intent")),
        ("Recommended grammar", visual_contract.get("recommended_diagram_grammar")),
        ("Template reference files", _format_task_list(visual_item.get("reference_slides"))),
        ("Template use principles", _format_task_list(visual_item.get("template_reference_principles"))),
        ("Visual contract", _format_task_map(visual_contract)),
        ("Pattern", prompt_pattern.get("pattern_id")),
        ("Block structure", _format_task_list(prompt_pattern.get("block_structure"))),
        ("Density budget", _format_task_map(density_budget)),
        ("Dominance map", _format_task_map(visual_item.get("dominance_map"))),
        ("Must keep claims", _format_task_list(visual_item.get("must_keep_claims"))),
        ("Execution loop", execution_policy.get("required_loop")),
        ("First-pass rules", _format_task_list(execution_policy.get("expected_first_pass_rules"))),
    ]
    if not include_structural_fields:
        field_specs = [
            (label, value)
            for label, value in field_specs
            if label not in {"Visual contract", "Pattern", "Block structure", "Density budget"}
        ]
    for label, value in field_specs:
        clean = _truncate_text(value, 260)
        if clean:
            lines.append(f"- {label}: {clean}")
    claim_boundary = _read_blueprint_slide_claim_boundary(project_path, slide_id)
    if claim_boundary in {"assumption", "inference"}:
        lines.append(
            f"- Claim boundary ({claim_boundary}): The core conclusion is not a confirmed fact. "
            "Keep an explicit qualifier (预计 / 计划 / 假设 / 拟 / 待验证 or equivalent) on the "
            "on-canvas conclusion; do not present it as an established result."
        )
    return "\n".join(lines)


def _truncate_text(value: object, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def _read_blueprint_slide_content(project_path: Path, slide_id: int) -> dict:
    blueprint_path = project_path / "blueprint.json"
    if not blueprint_path.exists():
        return {}
    try:
        payload = json.loads(blueprint_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return {}
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return {}
    for index, item in enumerate(slides, start=1):
        if not isinstance(item, dict):
            continue
        current_id = int(item.get("id") or index)
        if current_id != int(slide_id):
            continue
        content = item.get("content")
        if isinstance(content, dict):
            return content
        break
    return {}


def _read_blueprint_slide_claim_boundary(project_path: Path, slide_id: int) -> str:
    """Read the slide-level claim_boundary from blueprint.json (AB-04).

    blueprint.json is written once and is not regenerated by formal planning, so
    it is the stable carrier for the evidence-boundary passthrough.
    """
    blueprint_path = project_path / "blueprint.json"
    if not blueprint_path.exists():
        return ""
    try:
        payload = json.loads(blueprint_path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    slides = payload.get("slides") if isinstance(payload, dict) else None
    if not isinstance(slides, list):
        return ""
    for index, item in enumerate(slides, start=1):
        if not isinstance(item, dict):
            continue
        if int(item.get("id") or index) == int(slide_id):
            return str(item.get("claim_boundary") or "").strip().lower()
    return ""


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


_COMPLEX_STRUCTURE_SCAFFOLD_TYPES = frozenset(
    {
        "core_orbit",
        "timeline_spine",
        "node_flow",
        "decision_matrix",
        "control_gate_shift",
        "closure_dashboard",
        "pain_left_right",
        "proof_map",
    }
)
_RELATIONSHIP_SCAFFOLD_TYPES = frozenset(
    {
        "core_orbit",
        "timeline_spine",
        "node_flow",
        "control_gate_shift",
        "closure_dashboard",
        "pain_left_right",
    }
)
_EMPTY_CONTRACT_TEXT = frozenset({"", "none", "null", "n/a", "na", "unknown", "placeholder", "default"})
_GENERIC_RELATIONSHIP_MODELS = frozenset({"supporting_evidence"})


def _has_meaningful_contract_value(value: object) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in _EMPTY_CONTRACT_TEXT
    if isinstance(value, dict):
        return any(_has_meaningful_contract_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_contract_value(item) for item in value)
    return True


def _contract_value(*sources: dict, key: str) -> object:
    for source in sources:
        value = source.get(key)
        if _has_meaningful_contract_value(value):
            return value
    return None


def _has_explicit_relationship_model(value: object) -> bool:
    if not _has_meaningful_contract_value(value):
        return False
    return not (
        isinstance(value, str)
        and value.strip().lower() in _GENERIC_RELATIONSHIP_MODELS
    )


def _has_explicit_complex_structure_contract(visual_item: dict) -> bool:
    """Accept only explicit page-local structure evidence, not generic planning fields."""
    visual_contract = visual_item.get("visual_contract")
    visual_contract = visual_contract if isinstance(visual_contract, dict) else {}
    artifact_plan = visual_item.get("evidence_artifact_plan")
    artifact_plan = artifact_plan if isinstance(artifact_plan, dict) else {}
    sources = (visual_item, visual_contract, artifact_plan)

    artifact_type = _contract_value(*sources, key="artifact_type")
    if artifact_plan.get("required") is True and _has_meaningful_contract_value(artifact_type):
        return True

    if _has_explicit_relationship_model(_contract_value(*sources, key="relationship_model")):
        return True

    scaffold = _contract_value(*sources, key="deterministic_scaffold")
    if isinstance(scaffold, dict):
        scaffold_type = str(scaffold.get("type") or "").strip().lower()
        required_regions = scaffold.get("required_regions")
        if (
            scaffold_type in _COMPLEX_STRUCTURE_SCAFFOLD_TYPES
            and _has_meaningful_contract_value(required_regions)
        ):
            return True

    if any(
        _has_meaningful_contract_value(_contract_value(*sources, key=key))
        for key in ("core_node", "flow_edges", "engine_hub")
    ):
        return True

    diagram_grammar = _contract_value(*sources, key="recommended_diagram_grammar")
    required_regions = _contract_value(*sources, key="required_regions")
    return _has_meaningful_contract_value(diagram_grammar) and _has_meaningful_contract_value(
        required_regions
    )


def _structured_slide_contract(visual_item: dict) -> dict:
    """Return the existing page-local structure contract, if one is explicit."""
    visual_contract = visual_item.get("visual_contract")
    visual_contract = visual_contract if isinstance(visual_contract, dict) else {}
    artifact_plan = visual_item.get("evidence_artifact_plan")
    artifact_plan = artifact_plan if isinstance(artifact_plan, dict) else {}
    prompt_pattern = visual_item.get("page_prompt_pattern")
    prompt_pattern = prompt_pattern if isinstance(prompt_pattern, dict) else {}

    if not _has_explicit_complex_structure_contract(visual_item):
        return {}

    contract: dict[str, object] = {}
    for key in (
        "page_type_decision",
        "selected_archetype",
        "visual_archetype",
        "composition_intent",
        "recommended_diagram_grammar",
        "required_regions",
        "proof_objects",
        "anti_patterns",
    ):
        value = visual_item.get(key)
        if value not in (None, "", [], {}):
            contract[key] = value

    if artifact_plan:
        contract["evidence_artifact_plan"] = artifact_plan
    if prompt_pattern:
        contract["page_prompt_pattern"] = prompt_pattern

    structure_keys = (
        "scene_type",
        "visual_intent",
        "composition_grammar",
        "recommended_diagram_grammar",
        "must_answer_question",
        "focal_point",
        "primary_read_path",
        "required_regions",
        "anti_patterns",
        "deterministic_scaffold",
        "narrative_composition",
        "text_budget",
        "density_budget",
        "bbox_budget",
        "hierarchy_ladder",
        "whitespace_target",
        "layout_intent",
        "focal_point",
        "primary_read_path",
    )
    selected_visual_contract = {}
    for key in structure_keys:
        value = _contract_value(visual_contract, visual_item, key=key)
        if _has_meaningful_contract_value(value):
            selected_visual_contract[key] = value
    for key in ("core_node", "flow_edges", "engine_hub"):
        for source in (visual_contract, artifact_plan, visual_item):
            if source.get(key) not in (None, "", [], {}):
                selected_visual_contract[key] = source[key]
                break
    if selected_visual_contract:
        contract["visual_contract"] = selected_visual_contract
    return contract


def _compact_style_execution_tokens(project_path: Path) -> str:
    reference_path = project_path / "reference_pack.json"
    execution_tokens: dict[str, object] = {}
    if reference_path.exists():
        try:
            reference_pack = json.loads(reference_path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            reference_pack = {}
        if isinstance(reference_pack, dict):
            raw_tokens = reference_pack.get("execution_tokens")
            token_source = raw_tokens if isinstance(raw_tokens, dict) else reference_pack
            for key in (
                "token_set",
                "canvas",
                "background",
                "color_system",
                "typography",
                "typography_system",
                "font",
                "shape_language",
                "line_style",
                "spacing",
                "spacing_system",
                "rhythm_rules",
                "radius",
                "taboo_patterns",
            ):
                value = token_source.get(key)
                if value not in (None, "", [], {}):
                    execution_tokens[key] = value
    if not execution_tokens:
        execution_tokens = {
            "canvas": {"width": 1280, "height": 720},
            "note": "Use the active page style tokens and keep the safe-area rules below.",
        }
    return _compact_json(execution_tokens)


def _spatial_execution_contract(visual_item: dict, contract: dict) -> str:
    """Translate the existing page-local visual contract into spatial instructions."""
    artifact_plan = visual_item.get("evidence_artifact_plan")
    artifact_plan = artifact_plan if isinstance(artifact_plan, dict) else {}
    visual_contract = visual_item.get("visual_contract")
    visual_contract = visual_contract if isinstance(visual_contract, dict) else {}
    sources = (visual_item, visual_contract, artifact_plan)
    artifact_type = str(_contract_value(*sources, key="artifact_type") or "").strip()
    required_regions = contract.get("required_regions") or visual_item.get("required_regions") or []
    selected_archetype = contract.get("selected_archetype") or visual_item.get("selected_archetype") or ""
    visual_archetype = contract.get("visual_archetype") or visual_item.get("visual_archetype") or ""
    composition_intent = contract.get("composition_intent") or visual_item.get("composition_intent") or ""
    diagram_grammar = (
        contract.get("recommended_diagram_grammar")
        or visual_item.get("recommended_diagram_grammar")
        or visual_contract.get("recommended_diagram_grammar")
        or ""
    )
    compact_visual_contract = contract.get("visual_contract")
    compact_visual_contract = compact_visual_contract if isinstance(compact_visual_contract, dict) else {}
    relationship_model = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="relationship_model"
    ) or ""
    primary_read_path = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="primary_read_path"
    ) or []
    deterministic_scaffold = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="deterministic_scaffold"
    ) or {}
    core_node = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="core_node"
    )
    flow_edges = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="flow_edges"
    )
    engine_hub = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="engine_hub"
    )
    capability_equation = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="capability_equation"
    )
    central_engine = _contract_value(
        compact_visual_contract, visual_contract, visual_item, artifact_plan, key="central_engine"
    )
    scaffold_type = (
        str(deterministic_scaffold.get("type") or "").strip().lower()
        if isinstance(deterministic_scaffold, dict)
        else ""
    )
    proof_objects = contract.get("proof_objects") or visual_item.get("proof_objects") or []
    anti_patterns = contract.get("anti_patterns") or visual_item.get("anti_patterns") or []
    normalized_artifact_type = artifact_type.lower()
    has_explicit_artifact_type = normalized_artifact_type not in _EMPTY_CONTRACT_TEXT
    is_capability_engine = artifact_type == "capability_engine_diagram" or (
        not has_explicit_artifact_type
        and any(
            _has_meaningful_contract_value(value)
            for value in (engine_hub, capability_equation, central_engine)
        )
    )

    lines = [
        "SPATIAL EXECUTION CONTRACT",
        "Convert the visual contract into explicit spatial composition before writing SVG.",
        f"- Existing spatial inputs: artifact_type={_compact_json(artifact_type)}; required_regions={_compact_json(required_regions)}; selected_archetype={_compact_json(selected_archetype)}; visual_archetype={_compact_json(visual_archetype)}; composition_intent={_compact_json(composition_intent)}; recommended_diagram_grammar={_compact_json(diagram_grammar)}.",
        f"- Relationship inputs: relationship_model={_compact_json(relationship_model)}; primary_read_path={_compact_json(primary_read_path)}; deterministic_scaffold={_compact_json(deterministic_scaffold)}.",
        f"- Proof objects to keep visible: {_compact_json(proof_objects)}.",
        f"- Existing anti-patterns to avoid: {_compact_json(anti_patterns)}.",
        "- Allocate the page by role: a dominant main structure, readable supporting content, and enough whitespace for a 100% PNG preview; do not let secondary text become the main visual.",
        "- Use visible containment, direction, or input-output paths for every required relationship; spacing and card size alone are not relationship semantics.",
        "- Readability floor: main title >=34px, module title >=20px, body text >=17px.",
        "- Keep each module to no more than four short points where possible; compress wording before reducing font size, and do not make small explanatory text carry the primary message.",
    ]
    is_relationship_structure = bool(
        _has_explicit_relationship_model(relationship_model)
        or any(
            _has_meaningful_contract_value(value)
            for value in (core_node, flow_edges, engine_hub)
        )
        or scaffold_type in _RELATIONSHIP_SCAFFOLD_TYPES
    )
    if is_relationship_structure:
        lines.extend(
            [
                "- Treat the primary read path as one visible relationship structure; do not flatten it into independent equal containers.",
                "- Each required region is a semantic role on a continuous path or relationship map. Connectors must attach to meaningful nodes or regions and show direction, transition, or handoff.",
                "- For sequence or node-edge contracts, make the start, intermediate transformation, end, and any stated boundary visibly distinct; decorative arrows between unrelated cards are invalid.",
                "- Do not use a card grid plus decorative arrows as a substitute for the existing flow, node-edge, or center-periphery contract.",
            ]
        )
    if is_capability_engine:
        lines.extend(
            [
                "- The central engine / central capability object must be the page's primary visual object, with a readable core name and at least two linked layers where the existing contract supports them.",
                "- The central capability object should occupy approximately 30%-45% of the main visual area; it must not be represented only by a small dot, icon, or decorative symbol.",
                "- Every major module must connect to the central object through visible directional connections, arrows, or input-output paths that express business relationship; do not use short horizontal strokes as decorative connectors.",
                "- The primary structure must read as outer modules -> central capability transformation -> output or closed loop, or an equivalent relationship structure already defined by the visual contract.",
                "- Cards may carry content but must not define the primary structure; the main visual must remain the connected capability relationship.",
                "- Do not use three or four equal-weight cards, left/right columns with a decorative center dot, a title plus card grid plus summary bar, or a normal card with a heavier border as the central engine.",
                "- The relationship main visual must occupy at least 60% of the main content area. The supporting panel不得抢占主图的视觉权重，也不得替代主图表达； keep it to approximately <=28% of canvas width and visually weaker than the relationship structure.",
            ]
        )
    return "\n".join(lines)


def _build_structured_slide_prompt(
    project_name: str,
    project_path: Path,
    slide: dict,
    *,
    visual_item: dict,
    contract: dict,
    page_type: str,
    content_handling: str,
    page_style: str,
) -> str:
    slide_id = int(slide.get("slide_id") or 1)
    title = str(slide.get("title") or f"Slide {slide_id}").strip()
    raw_slide_prompt = str(slide.get("prompt") or "").strip()
    blueprint_content = _read_blueprint_slide_content(project_path, slide_id)
    claim_boundary = _read_blueprint_slide_claim_boundary(project_path, slide_id) or str(
        visual_item.get("claim_boundary") or ""
    ).strip()
    must_keep_claims = visual_item.get("must_keep_claims")
    page_task_sheet = _compact_page_task_sheet(
        project_path,
        slide_id,
        include_structural_fields=False,
    )
    pattern = contract.get("page_prompt_pattern")
    pattern_anti_patterns = pattern.get("anti_patterns") if isinstance(pattern, dict) else []
    anti_patterns = contract.get("anti_patterns") or pattern_anti_patterns or []
    contract_lines = [
        "NON-NEGOTIABLE STRUCTURE CONTRACT",
        "This contract has the highest priority for the page composition.",
        "The final SVG must visibly realize the required regions and relationships below.",
        "A result that omits the core structure, required regions, or required relationships is invalid.",
        f"- Page structure contract: {_compact_json(contract)}",
        f"- Forbidden structures: {_compact_json(anti_patterns)}",
        "- Relationship rule: represent the stated object-to-object relationships as visible connectors, flow, containment, or another explicit relationship grammar; do not replace them with disconnected equal cards.",
        "- ## page task sheet (compact contract notes)",
        page_task_sheet,
    ]
    contract_lines.extend(
        [
            "",
            _spatial_execution_contract(visual_item, contract),
        ]
    )

    content_lines = [
        "CURRENT SLIDE CONTENT",
        f"- Project: {project_name}",
        f"- Slide: {slide_id}",
        f"- Title: {title}",
        f"- Page type: {page_type}",
        f"- Content handling: {CONTENT_HANDLING_LABELS[content_handling]}",
        f"- Content handling guidance: {CONTENT_HANDLING_GUIDANCE[content_handling]}",
        f"- Original slide brief:\n{raw_slide_prompt or '(No separate user slide brief was recorded.)'}",
        f"- Blueprint current-page content:\n{_compact_json(blueprint_content or {'title': title})}",
    ]
    if must_keep_claims not in (None, "", [], {}):
        content_lines.append(f"- Must keep claims: {_compact_json(must_keep_claims)}")
    if claim_boundary:
        content_lines.append(f"- Claim boundary: {claim_boundary}")

    numbered_module_headings: list[str] = []
    heading_sources = [
        visual_item.get("visual_brief"),
        (
            visual_item.get("visual_contract", {}).get("text_budget", {}).get("body")
            if isinstance(visual_item.get("visual_contract"), dict)
            else None
        ),
        raw_slide_prompt,
    ]
    for source in heading_sources:
        if not isinstance(source, str):
            continue
        for line in source.splitlines():
            match = re.match(
                r"^\s*((?:\d{1,2})(?:\s+|[.、)）｜]\s*|\s*[-:：]\s*)\S.*?)\s*$",
                line,
            )
            if match:
                heading = match.group(1).strip()
                if heading not in numbered_module_headings:
                    numbered_module_headings.append(heading)
    if numbered_module_headings:
        content_lines.extend(
            [
                f"- Numbered module headings detected in current-page content (preserve exact text): {_compact_json(numbered_module_headings)}",
                "- Preserve all numbered module headings exactly as provided. Do not shorten, merge, rename, or omit them.",
                "- Preserve every module's core actions and business boundary; compress sentences before reducing readability or deleting a module.",
            ]
        )

    style_lines = [
        "STYLE EXECUTION TOKENS",
        f"- Page style: {PAGE_STYLE_LABELS[page_style]}",
        f"- Page style guidance: {PAGE_STYLE_GUIDANCE[page_style]}",
        f"- Current-page execution tokens: {_compact_style_execution_tokens(project_path)}",
        "- Keep the current consulting visual rhythm: clear hierarchy, purposeful whitespace, readable contrast, restrained accents, and consistent alignment.",
    ]
    guardrail_lines = [
        "SEMANTIC AND SVG SAFETY GUARDRAILS",
        "- The original slide brief remains the semantic authority for business facts.",
        "- Visual contracts authorize composition and emphasis only; they are not evidence for new business facts, states, roles, actions, sequences, or conclusions.",
        "- Do not turn administrative, planning, QA, style, or prompt instructions into on-canvas copy.",
        "- Preserve explicit labels, qualifiers, status, scope, numbers, and conclusion strength; do not infer reverse-side actions or unstated business relationships.",
        "- Preserve Simplified Chinese exactly and do not output mojibake.",
        '- Return exactly one complete valid SVG with viewBox="0 0 1280 720".',
        "- The first child must be a full-canvas background rect; use native SVG text nodes.",
        "- Do not use foreignObject, external images, scripts, animation, web fonts, style, or class; do not use group-level opacity.",
        "- Give every visible text element explicit x/y coordinates; keep text inside the safe area with no overlap or obvious overflow.",
        "- XML must be valid and correctly closed.",
    ]
    hard_rules = [
        "SVG HARD RULES",
        "- Return only SVG; no Markdown or commentary. The guardrails are non-negotiable.",
    ]
    return "\n\n".join(
        "\n".join(lines)
        for lines in (contract_lines, content_lines, style_lines, guardrail_lines, hard_rules)
    ) + "\n"


def _summarize_block_item(item: object) -> str:
    if isinstance(item, dict):
        parts: list[str] = []
        for key in ("phase", "date", "title", "label", "value", "body", "support", "deliverable", "system_support"):
            value = str(item.get(key) or "").strip()
            if not value:
                continue
            parts.append(f"{key}: {value}")
        if parts:
            return _truncate_text(" | ".join(parts), 280)
    return _truncate_text(item, 280)


def _fallback_blocks_from_prompt(prompt: str) -> list[str]:
    lines = [line.strip(" -•\t") for line in str(prompt or "").splitlines()]
    cleaned = [line for line in lines if line and len(line) > 2]
    if not cleaned:
        return []
    numbered = [line for line in cleaned if re.match(r"^(\d+[\.\)]|[一二三四五六七八九十]+[、\.])", line)]
    candidates = numbered if numbered else cleaned
    return [_truncate_text(item, 260) for item in candidates[:12]]


def plan_slide_blocks(project_path: Path, slide: dict, max_blocks: int = PROGRESSIVE_MAX_BLOCKS) -> list[dict[str, str]]:
    slide_id = int(slide.get("slide_id") or 0)
    content = _read_blueprint_slide_content(project_path, slide_id)
    list_keys = (
        "cards",
        "items",
        "kpis",
        "steps",
        "phases",
        "events",
        "pros",
        "cons",
        "capabilities",
        "pillars",
        "initiatives",
    )
    blocks: list[dict[str, str]] = []
    for key in list_keys:
        value = content.get(key) if isinstance(content, dict) else None
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value, start=1):
            text = _summarize_block_item(item)
            if not text:
                continue
            blocks.append({"label": f"{key}_{index}", "text": text})
    for key in ("left", "right"):
        value = content.get(key) if isinstance(content, dict) else None
        if isinstance(value, dict):
            text = _summarize_block_item(value)
            if text:
                blocks.append({"label": key, "text": text})
    if not blocks:
        blocks = [{"label": f"prompt_{idx + 1}", "text": text} for idx, text in enumerate(_fallback_blocks_from_prompt(slide_prompt_text(slide)))]
    if not blocks:
        fallback = _truncate_text(slide_prompt_text(slide) or slide.get("title") or f"Slide {slide_id}", 260)
        blocks = [{"label": "main", "text": fallback}]
    max_blocks = max(1, int(max_blocks or PROGRESSIVE_MAX_BLOCKS))
    if len(blocks) <= max_blocks:
        return blocks
    head = blocks[: max_blocks - 1]
    tail = blocks[max_blocks - 1 :]
    merged = " || ".join(item["text"] for item in tail if item.get("text"))
    head.append({"label": f"merged_{len(tail)}", "text": _truncate_text(merged, 540)})
    return head


def _set_progress_state(
    slide: dict,
    *,
    phase: str,
    block_total: int,
    block_completed: int,
    current_block_label: str = "",
) -> None:
    stamp = now_iso()
    slide["generation_phase"] = str(phase or "")
    slide["block_total"] = max(0, int(block_total or 0))
    slide["block_completed"] = max(0, min(int(block_completed or 0), slide["block_total"]))
    slide["current_block_label"] = str(current_block_label or "")
    slide["lock_updated_at"] = stamp


def _clear_progress_state(slide: dict) -> None:
    slide["generation_phase"] = "completed"
    slide["current_block_label"] = ""
    slide["lock_updated_at"] = now_iso()


def _persist_current_slide(
    project_path: Path,
    status: dict,
    slide: dict,
    *,
    status_patch: dict | None = None,
    event_type: str = "",
    event_message: str = "",
) -> tuple[dict, dict]:
    slide_id = int(slide.get("slide_id") or 0)
    latest_status = merge_slide_status(
        project_path,
        status,
        slide_id,
        dict(slide),
        status_patch=status_patch,
        event_type=event_type,
        event_message=event_message,
    )
    latest_slide = next(
        (item for item in latest_status.get("slides", []) if isinstance(item, dict) and int(item.get("slide_id") or 0) == slide_id),
        slide,
    )
    return latest_status, latest_slide


def run_progressive_slide_generation(
    *,
    project_name: str,
    project_path: Path,
    status: dict,
    slide: dict,
    config: GenerationConfig,
    target: Path,
    generate: Callable[[str, GenerationConfig], str],
) -> tuple[str, list[dict[str, str]]]:
    blocks = plan_slide_blocks(project_path, slide, max_blocks=PROGRESSIVE_MAX_BLOCKS)
    block_total = len(blocks)
    _set_progress_state(slide, phase="scaffold", block_total=block_total, block_completed=0, current_block_label="scaffold")
    status, slide = _persist_current_slide(project_path, status, slide)
    scaffold_svg = extract_svg(
        generate(
            build_slide_prompt(project_name, project_path, slide, phase="scaffold", block_payload=None, prior_svg=""),
            config,
        )
    )
    target.write_text(scaffold_svg, encoding="utf-8")
    slide["has_svg"] = True
    slide["svg_path"] = f"svg_output/slide_{int(slide.get('slide_no') or slide.get('slide_id') or 0):02d}.svg"
    slide["lock_updated_at"] = now_iso()
    status, slide = _persist_current_slide(project_path, status, slide)
    current_svg = scaffold_svg
    for index, block in enumerate(blocks, start=1):
        label = block.get("label") or f"block_{index}"
        _set_progress_state(
            slide,
            phase=f"block_{index}",
            block_total=block_total,
            block_completed=index - 1,
            current_block_label=label,
        )
        status, slide = _persist_current_slide(project_path, status, slide)
        block_svg = extract_svg(
            generate(
                build_slide_prompt(
                    project_name,
                    project_path,
                    slide,
                    phase=f"block_{index}",
                    block_payload=block,
                    prior_svg=current_svg,
                ),
                config,
            )
        )
        target.write_text(block_svg, encoding="utf-8")
        current_svg = block_svg
        _set_progress_state(
            slide,
            phase=f"block_{index}",
            block_total=block_total,
            block_completed=index,
            current_block_label=label,
        )
        slide["has_svg"] = True
        status, slide = _persist_current_slide(project_path, status, slide)
    _set_progress_state(
        slide,
        phase="polish",
        block_total=block_total,
        block_completed=block_total,
        current_block_label="polish",
    )
    status, slide = _persist_current_slide(project_path, status, slide)
    polished_svg = extract_svg(
        generate(
            build_slide_prompt(project_name, project_path, slide, phase="polish", block_payload=None, prior_svg=current_svg),
            config,
        )
    )
    target.write_text(polished_svg, encoding="utf-8")
    _clear_progress_state(slide)
    _persist_current_slide(project_path, status, slide)
    return polished_svg, blocks


def build_slide_prompt(
    project_name: str,
    project_path: Path,
    slide: dict,
    *,
    phase: str = "full",
    block_payload: dict[str, str] | None = None,
    prior_svg: str = "",
) -> str:
    slide_id = int(slide.get("slide_id") or 1)
    slide_no = int(slide.get("slide_no") or slide_id)
    raw_slide_prompt = str(slide.get("prompt") or "").strip()
    page_type = _normalized_page_type(slide.get("page_type"))
    content_handling = _normalized_content_handling(slide.get("content_handling"))
    page_style = _normalized_page_style(slide.get("page_style"))
    phase_name = str(phase or "full").strip().lower()
    visual_item = _read_slide_payload(project_path / "slide_visual_plan.json", slide_id)
    structured_contract = _structured_slide_contract(visual_item)
    if phase_name == "full" and structured_contract:
        return _build_structured_slide_prompt(
            project_name,
            project_path,
            slide,
            visual_item=visual_item,
            contract=structured_contract,
            page_type=page_type,
            content_handling=content_handling,
            page_style=page_style,
        )
    blueprint_context = _read_slide_context(
        project_path / "blueprint.json",
        slide_id,
        limit=5000,
        excluded_keys=frozenset({"prompt"}),
    )
    visual_plan_context = _read_slide_context(project_path / "slide_visual_plan.json", slide_id, limit=5000)
    page_task_sheet = _compact_page_task_sheet(project_path, slide_id)
    phase_context = ""
    if phase_name != "full":
        payload_text = json.dumps(block_payload or {}, ensure_ascii=False, indent=2)
        prior_svg_excerpt = _truncate_text(prior_svg.replace("\n", " "), 8000) if prior_svg else ""
        phase_context = f"""

## progressive rendering mode
- current phase: {phase_name}
- editing policy: preserve existing visual hierarchy and only add/refine what current phase requests.
- block payload:
{payload_text}
- previous svg excerpt:
{prior_svg_excerpt or "(none)"}"""
    return f"""You are generating one production SVG page for a PowerPoint deck.

Project: {project_name}
Slide: {slide_no}
Title: {slide.get("title") or f"Slide {slide_no}"}
Page type: {page_type}
Content handling: {CONTENT_HANDLING_LABELS[content_handling]}
Content handling guidance: {CONTENT_HANDLING_GUIDANCE[content_handling]}
Page style: {PAGE_STYLE_LABELS[page_style]}
Page style guidance: {PAGE_STYLE_GUIDANCE[page_style]}

Return only one complete SVG. No Markdown, no commentary.

Hard requirements:
- Use native SVG only, with <svg viewBox="0 0 1280 720">.
- Do not use foreignObject, external images, scripts, animation, or web fonts.
- Do not use <style> blocks or class attributes; put font, fill, stroke, and size directly on each SVG element.
- Do not put opacity on <g> groups; if transparency is needed, put fill-opacity or stroke-opacity on the specific shape.
- Write Chinese text as real <text> nodes.
- Every visible <text> element must have explicit x and y attributes; when using <tspan> lines, the parent <text> must also carry x/y matching the first visible tspan.
- Preserve Simplified Chinese exactly. Never output mojibake/re-encoded text such as "鍥", "绗", "寰", "涓", or "鏂".
- Keep the page presentation-ready, with clear hierarchy and no overlapping text.
- Follow the original slide brief first, then the project design spec, blueprint, art direction, reference pack, and slide task.
- Treat the original slide brief as the semantic authority for business facts. Planning artifacts may organize explicit facts, but they do not authorize new business meaning.
- Do not invent statuses, owners, stage names, business actions, or conclusions that are absent from the original slide brief.
- Faithful professional compression and rewriting are allowed, but they must not change or add any business object, action, relationship, number, status, scope, or conclusion strength from the original slide brief.
- Do not omit qualifiers that carry status, scope, or conclusion strength. For example, “已计划未开展” must not be shortened to “已计划”.
- Do not infer the reverse-side action from a stated action. For example, “T2汇总TN材料” does not authorize “TN提供材料” or “TN配合汇总”.
- Keep explicit business labels such as T1, T2, and TN exactly as written. Do not expand them into newly named tiers or roles.
- A bottom takeaway may be used when it is explicitly stated in or directly supported by the original slide brief. It may faithfully compress the supported conclusion, but must not add a new business conclusion or strengthen the original conclusion.
- Unless the exact meaning is explicit in the original slide brief, do not add labels such as “进行中”, “目标”, “形成闭环”, or “执行标准”.
- Unless explicitly present in the original slide brief, do not add claims such as “全程可追溯”, “管理模型”, or “动作清晰”.
- A visual contract authorizes composition and emphasis only. It must never be treated as evidence for a new state, role, sequence, hierarchy, action, or conclusion.
- Use the page task sheet as the compact planning bridge; if it conflicts with an explicit user requirement, keep the user requirement unless it breaks hard export/readability/safe-area rules.
- Treat slide_visual_plan.json as the binding page contract: follow visual_contract.recommended_diagram_grammar, visual_contract.must_answer_question, page_prompt_pattern.block_structure, and density_budget for the main structure.
- Do not turn admin/style instructions into on-canvas copy. Use blueprint content and visual_contract.text_budget as the copy budget; use target audience, scene, colors, and style sections only as design constraints.
- Think through a structure pass and a polish pass internally, then output only the final refined SVG.
- The page should feel like a senior consulting/internal-practice deck, not a quick four-card wireframe, dashboard, poster, webpage, or tool advertisement.
- Use restrained visual sophistication: strong title hierarchy, purposeful whitespace, aligned geometry, subtle dividers, meaningful emphasis, and a bottom takeaway only when it is explicitly stated in or directly supported by the source.
- If the brief asks for a quadrant/map, make it a polished practice map with connective structure and clear focus. Avoid plain equal white cards unless the brief explicitly requires a raw table.
- The main headline font-size must be at least 40px on content pages; use 44-52px when the title is short enough.
- Hard cap the page at 24 visible <text> elements; target 16-20. Merge short labels into grouped <text> blocks with <tspan> lines instead of scattering many small text fragments.
- Do not build mock dashboards, chart axes, legends, month labels, or decorative KPI readouts unless the user explicitly asks for a dashboard. Axis labels and mock numbers count against the text-node cap.
- Use 2-4 consistent x-alignment tracks for the whole page. Snap module titles, body text, and evidence labels to the same column rails.
- Body text should be grouped into 3-5 strong visual modules; avoid tiny disconnected captions unless they are axis labels or compact chips.
- All visible <text> must have strong contrast against its local background. On white or light cards, use dark text (#172033/#344054/#932141); do not use pale pink/gray decorative numbers as text. If step numbers are needed, use high-contrast small badges or shape-only decoration instead of low-contrast text.
- For arrow-linked cards, leave at least 96px between cards for labels, or put the label in a filled chip above/below the arrow; never squeeze text into a narrow gap.
- Do not use orange accent text on white or pale backgrounds. Reserve orange for rules, icons, or small filled tags; use wine (#932141) or navy (#123B7A) for readable text on light surfaces.
- Avoid gradient fills behind text on content pages; use solid fills so the PPT exporter and QA checker can preserve readability.
- Keep text within the safe area: x >= 96, x + width <= 1184, y >= 56, y + height <= 664.
- The first child of the SVG must be a full-canvas background <rect x="0" y="0" width="1280" height="720" fill="...">; do not rely only on <svg style="background-color: ...">.
- For card layouts, reserve a clear card header band: body text must start at least 24px below any card number/tag/title row and at least 18px below the header divider. Card header labels and body text bounding boxes must not touch or overlap.
- Keep the slide concise: short labels and compact phrases are better than copying every instruction onto the canvas.
- The SVG must be valid XML. Close every tag correctly.

## visual intensity policy by page type
{_visual_intensity_guidance(page_type)}

## page task sheet
{page_task_sheet}

## original slide brief
{raw_slide_prompt or "(No separate user slide brief was recorded.)"}

## design_spec.md
{_read_context_file(project_path / "design_spec.md", 5000)}

## art_direction.md
{_read_context_file(project_path / "art_direction.md", 5000)}

## reference_pack.json
{_read_context_file(project_path / "reference_pack.json", 5000)}

## blueprint.json
{blueprint_context}

## slide_visual_plan.json
{visual_plan_context}

## slide task
{_read_slide_task_context(project_path / "agent_tasks" / f"slide_{slide_no:02d}.md", 7000)}
{phase_context}
"""


def slide_prompt_text(slide: dict) -> str:
    return str(slide.get("prompt") or "").strip()


def mark_waiting_for_prompt(slide: dict, target: Path) -> None:
    slide["status"] = "waiting_prompt"
    slide["has_svg"] = target.exists()
    slide["qa_status"] = "not_run"
    slide["last_error"] = PROMPT_REQUIRED_MESSAGE


def _ensure_planning_before_generation(project_path: Path, status: dict) -> None:
    ensure_formal_planning(project_path, status)


def auto_generate_project(
    project_name: str,
    project_path: Path,
    config: GenerationConfig | None = None,
    generate: Callable[[str, GenerationConfig], str] = call_slide_model_generate,
) -> dict:
    status = load_status(project_path)
    if not status:
        raise ValueError("Project status not found.")
    _ensure_planning_before_generation(project_path, status)
    status["generation_mode"] = "api_auto"
    config = config or load_generation_config()
    if not config.configured():
        raise ValueError(f"{config.provider} API key is not configured. Set env var or configure {config.provider}_api_key_env in workbench/settings.local.json.")
    _reset_generation_trace()
    status["generation"] = config.public_metadata()
    status["generation_fallback_trace"] = []
    save_status(project_path, status)

    output_dir = project_path / "svg_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[int] = []
    skipped: list[int] = []
    failed: list[int] = []
    blocked: list[int] = []
    queued: list[int] = []
    paused = False
    pause_reason = ""
    consecutive_transient_reason = ""
    consecutive_transient_failures = 0
    slide_ids = [int(item.get("slide_id") or 0) for item in list(status.get("slides", []))]
    for index, slide_id in enumerate(slide_ids):
        if slide_id <= 0:
            continue
        live_status = load_status(project_path) or {}
        live_slide = next(
            (entry for entry in live_status.get("slides", []) if int(entry.get("slide_id") or 0) == slide_id),
            None,
        )
        if not isinstance(live_slide, dict):
            continue
        slide_no = int(live_slide.get("slide_no") or slide_id)
        target = output_dir / f"slide_{slide_no:02d}.svg"
        if live_slide.get("has_svg") and target.exists():
            continue
        live_slide_status = str(live_slide.get("status") or "")
        live_generation_phase = str(live_slide.get("generation_phase") or "")
        if live_slide_status in {"queued", "running", "generating"} or live_generation_phase in {"queued", "starting", "running", "retrying"}:
            queued.append(slide_id)
            continue
        if not slide_prompt_text(live_slide):
            mark_waiting_for_prompt(live_slide, target)
            live_slide["generation_phase"] = "waiting_prompt"
            live_slide["block_total"] = 0
            live_slide["block_completed"] = 0
            live_slide["current_block_label"] = ""
            live_slide["lock_updated_at"] = now_iso()
            skipped.append(slide_id)
            live_status["generation"] = config.public_metadata()
            live_status["generation_fallback_trace"] = []
            save_status(project_path, live_status)
            continue
        try:
            result = auto_generate_slide(
                project_name,
                project_path,
                slide_id,
                config=config,
                generate=generate,
                overwrite=True,
            )
        except RuntimeError:
            failed.append(slide_id)
            failure_code = _slide_failure_code(project_path, slide_id)
            if failure_code in SYSTEMIC_BATCH_PAUSE_REASONS:
                pause_reason = failure_code
                paused = True
                remaining_slide_ids = [value for value in slide_ids[index + 1 :] if int(value or 0) > 0]
                blocked.extend(
                    _block_remaining_slides_after_pause(
                        project_path,
                        remaining_slide_ids,
                        failure_code,
                        f"Batch generation paused after slide {slide_id}: {failure_code}.",
                    )
                )
                break
            if failure_code in TRANSIENT_BATCH_PAUSE_REASONS:
                if failure_code == consecutive_transient_reason:
                    consecutive_transient_failures += 1
                else:
                    consecutive_transient_reason = failure_code
                    consecutive_transient_failures = 1
                if consecutive_transient_failures >= TRANSIENT_BATCH_PAUSE_THRESHOLD:
                    pause_reason = failure_code
                    paused = True
                    remaining_slide_ids = [value for value in slide_ids[index + 1 :] if int(value or 0) > 0]
                    blocked.extend(
                        _block_remaining_slides_after_pause(
                            project_path,
                            remaining_slide_ids,
                            failure_code,
                            f"Batch generation paused after {consecutive_transient_failures} consecutive {failure_code} failures.",
                        )
                    )
                    break
            else:
                consecutive_transient_reason = ""
                consecutive_transient_failures = 0
            continue
        generated.extend([int(value) for value in (result.get("generated_slides") or []) if int(value) > 0])
        consecutive_transient_reason = ""
        consecutive_transient_failures = 0

    status = load_status(project_path)
    if not status:
        raise ValueError("Project status not found after generation.")
    status["project_status"] = "svg_ready" if all(slide.get("has_svg") for slide in status.get("slides", [])) else "svg_partial"
    status["generation"] = config.public_metadata()
    if generated:
        trace = status.get("generation_fallback_trace") if isinstance(status.get("generation_fallback_trace"), list) else []
        success_provider = next(
            (str(item.get("provider")) for item in reversed(trace) if isinstance(item, dict) and item.get("event") == "success" and item.get("provider")),
            config.provider,
        )
        add_event(status, "api_auto_generate", f"Generated SVG pages via {success_provider}: {', '.join(map(str, generated))}.")
    if skipped:
        add_event(status, "api_auto_generate_skipped", f"Skipped pages without prompts: {', '.join(map(str, skipped))}.")
    if queued:
        add_event(status, "api_auto_generate_already_queued", f"Skipped pages already queued or running: {', '.join(map(str, queued))}.")
    if failed:
        add_event(status, "api_auto_generate_partial_failed", f"Pages failed during batch generation: {', '.join(map(str, failed))}.")
    if blocked:
        status["deck_status"] = "paused"
        status["generation_pause_reason"] = pause_reason
        add_event(status, "api_auto_generate_blocked", f"Pages blocked by batch pause: {', '.join(map(str, blocked))}.")
    if not generated and not skipped and not failed:
        add_event(status, "api_auto_generate", "No missing SVG pages to generate.")
    save_status(project_path, status)
    return {
        "generated_slides": generated,
        "skipped_slides": skipped,
        "failed_slides": failed,
        "blocked_slides": blocked,
        "queued_slides": queued,
        "paused": paused,
        "pause_reason": pause_reason,
        "generated_count": len(generated),
        "failed_count": len(failed),
        "generation": config.public_metadata(),
    }


def auto_generate_slide(
    project_name: str,
    project_path: Path,
    slide_id: int,
    config: GenerationConfig | None = None,
    generate: Callable[[str, GenerationConfig], str] = call_slide_model_generate,
    overwrite: bool = True,
) -> dict:
    status = load_status(project_path)
    if not status:
        raise ValueError("Project status not found.")
    _ensure_planning_before_generation(project_path, status)
    status["generation_mode"] = "api_auto"
    config = config or load_generation_config()
    if not config.configured():
        raise ValueError(f"{config.provider} API key is not configured. Set env var or configure {config.provider}_api_key_env in workbench/settings.local.json.")
    _reset_generation_trace()
    effective_generate = generate

    slide = next((item for item in status.get("slides", []) if int(item.get("slide_id") or 0) == int(slide_id)), None)
    if slide is None:
        raise ValueError(f"Slide {slide_id} not found.")
    slide_no = int(slide.get("slide_no") or slide_id)

    output_dir = project_path / "svg_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"slide_{slide_no:02d}.svg"
    if not slide_prompt_text(slide):
        mark_waiting_for_prompt(slide, target)
        status["generation"] = config.public_metadata()
        status["generation_fallback_trace"] = []
        _persist_current_slide(
            project_path,
            status,
            slide,
            status_patch={"generation": config.public_metadata(), "generation_fallback_trace": []},
            event_type="api_auto_generate_skipped",
            event_message=f"Skipped slide {slide_id}: prompt is empty.",
        )
        raise ValueError(PROMPT_REQUIRED_MESSAGE)
    if target.exists() and not overwrite:
        return {"generated_slides": [], "generated_count": 0, "generation": config.public_metadata()}
    had_existing_svg = target.exists()
    if target.exists():
        backup_slide_revision(project_path, slide_no, "before-auto-generate-page")

    slide["status"] = "generating"
    slide["qa_status"] = "not_run"
    slide["last_error"] = ""
    slide["last_error_code"] = ""
    slide["generation_started_at"] = now_iso()
    slide["generation_completed_at"] = ""
    slide["lock_updated_at"] = now_iso()
    slide["generation_phase"] = "starting"
    slide["block_total"] = 0
    slide["block_completed"] = 0
    slide["current_block_label"] = ""
    status["project_status"] = "generating"
    status["generation"] = config.public_metadata()
    status["generation_fallback_trace"] = []
    status, slide = _persist_current_slide(
        project_path,
        status,
        slide,
        status_patch={"project_status": "generating", "generation": config.public_metadata(), "generation_mode": "api_auto", "generation_fallback_trace": []},
        event_type="api_auto_generate_started",
        event_message=f"Slide {slide_id} auto generation started.",
    )

    planned_blocks: list[dict[str, str]] = []
    try:
        for generation_attempt in range(1, 3):
            try:
                if config.progressive_visualization_enabled:
                    try:
                        svg, planned_blocks = run_progressive_slide_generation(
                            project_name=project_name,
                            project_path=project_path,
                            status=status,
                            slide=slide,
                            config=config,
                            target=target,
                            generate=effective_generate,
                        )
                    except Exception as progressive_exc:
                        _set_progress_state(
                            slide,
                            phase="fallback_single_pass",
                            block_total=max(1, len(planned_blocks)),
                            block_completed=max(0, len(planned_blocks)),
                            current_block_label="fallback",
                        )
                        status, slide = _persist_current_slide(
                            project_path,
                            status,
                            slide,
                            event_type="api_auto_generate_progressive_fallback",
                            event_message=f"Slide {slide_id} progressive generation fallback to single-pass: {user_facing_generation_error(progressive_exc)}",
                        )
                        svg = extract_svg(effective_generate(build_slide_prompt(project_name, project_path, slide, phase="full"), config))
                else:
                    svg = extract_svg(effective_generate(build_slide_prompt(project_name, project_path, slide, phase="full"), config))
                break
            except Exception as generation_exc:
                retry_reason = _auto_generation_retry_reason(generation_exc)
                if generation_attempt >= 2 or not retry_reason:
                    raise
                slide["generation_phase"] = "retrying"
                slide["last_error"] = user_facing_generation_error(generation_exc)
                slide["lock_updated_at"] = now_iso()
                status, slide = _persist_current_slide(
                    project_path,
                    status,
                    slide,
                    event_type="api_auto_generate_retry",
                    event_message=f"Slide {slide_id} auto generation retry after {retry_reason}: {user_facing_generation_error(generation_exc)}",
                )
    except Exception as exc:
        message = user_facing_generation_error(exc)
        reason_code = _auto_generation_failure_reason(exc)
        trace = last_generation_trace()
        preserved_existing_svg = had_existing_svg and target.exists()
        slide["status"] = "qa_failed" if preserved_existing_svg else "failed"
        slide["has_svg"] = preserved_existing_svg
        slide["qa_status"] = "failed" if preserved_existing_svg else "not_run"
        slide["svg_path"] = f"svg_output/slide_{slide_no:02d}.svg"
        slide["last_error"] = message
        slide["last_error_code"] = reason_code
        if reason_code in {"provider_busy", "svg_parse_error"}:
            slide["recommended_action"] = "auto_generate"
        slide["generation_completed_at"] = now_iso()
        slide["lock_updated_at"] = now_iso()
        slide["generation_phase"] = "failed_preserved_previous" if preserved_existing_svg else "failed"
        status["project_status"] = "svg_partial" if any(item.get("has_svg") for item in status.get("slides", [])) else "waiting_codex"
        status["generation"] = config.public_metadata()
        status["generation_fallback_trace"] = trace[-20:] if trace else []
        latest_slides = (load_status(project_path) or status).get("slides", [])
        if preserved_existing_svg:
            project_status = "qa_failed"
        else:
            project_status = "svg_partial" if any(item.get("has_svg") for item in latest_slides if isinstance(item, dict)) else "waiting_codex"
        status_patch = {
            "generation_mode": "api_auto",
            "project_status": project_status,
            "generation": config.public_metadata(),
            "generation_fallback_trace": trace[-20:] if trace else [],
        }
        _persist_current_slide(
            project_path,
            status,
            slide,
            status_patch=status_patch,
            event_type="api_auto_generate_failed",
            event_message=f"Slide {slide_id} auto generation failed: {message}",
        )
        raise RuntimeError(message) from exc

    target.write_text(svg, encoding="utf-8")
    slide["status"] = "svg_ready"
    slide["has_svg"] = True
    slide["svg_path"] = f"svg_output/slide_{slide_no:02d}.svg"
    slide["qa_status"] = "not_run"
    slide["last_error"] = ""
    slide["last_error_code"] = ""
    slide.pop("recommended_action", None)
    slide["generation_completed_at"] = now_iso()
    slide["lock_updated_at"] = now_iso()
    slide["block_total"] = max(slide.get("block_total") or len(planned_blocks), len(planned_blocks))
    slide["block_completed"] = slide["block_total"]
    slide["generation_phase"] = "completed"
    slide["current_block_label"] = ""
    status["project_status"] = "svg_ready" if all(item.get("has_svg") for item in status.get("slides", [])) else "svg_partial"
    trace = last_generation_trace()
    status["generation"] = config.public_metadata()
    status["generation_fallback_trace"] = trace[-20:] if trace else []
    fallback_used = any(item.get("event") == "fallback_next_provider" for item in trace)
    success_provider = next(
        (str(item.get("provider")) for item in reversed(trace) if item.get("event") == "success" and item.get("provider")),
        config.provider,
    )
    if fallback_used:
        status, slide = _persist_current_slide(
            project_path,
            status,
            slide,
            status_patch={"generation": config.public_metadata(), "generation_mode": "api_auto", "generation_fallback_trace": trace[-20:] if trace else []},
            event_type="api_auto_generate_fallback",
            event_message=f"Slide {slide_id} used quota fallback across providers.",
        )
    success_patch = {
        "generation": config.public_metadata(),
        "generation_mode": "api_auto",
        "generation_fallback_trace": trace[-20:] if trace else [],
    }
    latest_slides = (load_status(project_path) or status).get("slides", [])
    success_patch["project_status"] = "svg_ready" if all(
        item.get("has_svg") or int(item.get("slide_id") or 0) == int(slide_id)
        for item in latest_slides
        if isinstance(item, dict)
    ) else "svg_partial"
    _persist_current_slide(
        project_path,
        status,
        slide,
        status_patch=success_patch,
        event_type="api_auto_generate",
        event_message=f"Generated SVG page via {success_provider}: {slide_id}.",
    )
    return {"generated_slides": [slide_id], "generated_count": 1, "generation": config.public_metadata()}
