from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_GOOGLE_MODEL = "gemini-3.5-flash"
DEFAULT_GENERATION_PROVIDER = "siliconflow"
DEFAULT_XIAOMI_MODEL = "mimo-v2.5-pro"
DEFAULT_XIAOMI_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_SILICONFLOW_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent / "settings.local.json"
DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED = False
PROGRESSIVE_MAX_BLOCKS = 6
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPT_REQUIRED_MESSAGE = "请先填写本页提示词，再生成页面。"
GEMINI_QUOTA_EXHAUSTED_MESSAGE = "模型额度或频率已达上限，已尝试切换可用配置；如果仍失败，请稍后再试。"


class ConfigMismatchError(ValueError):
    """Raised when a model configuration combines fields from different providers."""


PROVIDER_FALLBACK_ORDER = ("google", "xiaomi", "siliconflow", "deepseek")
ENV_VAR_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
PROVIDER_SECRET_FIELDS = {
    "google": ("google_api_key", "google_api_keys", "google_api_key_env", "google_api_keys_env"),
    "xiaomi": ("xiaomi_api_key", "xiaomi_api_keys", "xiaomi_api_key_env", "xiaomi_api_keys_env"),
    "siliconflow": ("siliconflow_api_key", "siliconflow_api_keys", "siliconflow_api_key_env", "siliconflow_api_keys_env"),
    "deepseek": ("deepseek_api_key", "deepseek_api_keys", "deepseek_api_key_env", "deepseek_api_keys_env"),
}
PROVIDER_PLAINTEXT_FIELDS = {
    "google": ("google_api_key", "google_api_keys"),
    "xiaomi": ("xiaomi_api_key", "xiaomi_api_keys"),
    "siliconflow": ("siliconflow_api_key", "siliconflow_api_keys"),
    "deepseek": ("deepseek_api_key", "deepseek_api_keys"),
}
PROVIDER_PRIMARY_ENV = {
    "google": "WORKBENCH_GOOGLE_API_KEY",
    "xiaomi": "WORKBENCH_XIAOMI_API_KEY",
    "siliconflow": "WORKBENCH_SILICONFLOW_API_KEY",
    "deepseek": "WORKBENCH_DEEPSEEK_API_KEY",
}


def default_model_for_provider(provider: str) -> str:
    if provider == "google":
        return DEFAULT_GOOGLE_MODEL
    if provider == "xiaomi":
        return DEFAULT_XIAOMI_MODEL
    if provider == "siliconflow":
        return DEFAULT_SILICONFLOW_MODEL
    return DEFAULT_DEEPSEEK_MODEL


def is_cross_provider_model(provider: str, model: str) -> bool:
    folded_provider = str(provider or "").strip().lower()
    folded_model = str(model or "").strip().lower()
    if not folded_model:
        return False
    if folded_provider in {"xiaomi", "siliconflow", "deepseek"} and folded_model.startswith("gemini"):
        return True
    if folded_provider == "xiaomi" and folded_model.startswith("deepseek"):
        return True
    if folded_provider == "google" and (folded_model.startswith("deepseek") or folded_model.startswith("mimo")):
        return True
    return False


def normalize_model_for_provider(provider: str, model: str) -> tuple[str, bool]:
    clean_model = str(model or "").strip()
    if not clean_model:
        return default_model_for_provider(provider), True
    if is_cross_provider_model(provider, clean_model):
        return default_model_for_provider(provider), True
    return clean_model, False


def validate_generation_config(config: "GenerationConfig") -> None:
    provider = str(config.provider or "").strip().lower()
    model = str(config.model or "").strip()
    base_url = str(config.base_url or "").strip().rstrip("/")
    if is_cross_provider_model(provider, model):
        raise ConfigMismatchError(
            f"模型配置不一致：provider={provider} 与 model={model} 不匹配，已在请求前阻止发送。"
        )
    if provider == "google" and base_url:
        raise ConfigMismatchError(
            f"模型配置不一致：provider=google 与 base_url={base_url} 不匹配，已在请求前阻止发送。"
        )
    known_provider_hosts = {
        "xiaomi": "token-plan-cn.xiaomimimo.com",
        "siliconflow": "api.siliconflow.cn",
        "deepseek": "api.deepseek.com",
    }
    for other_provider, host in known_provider_hosts.items():
        if provider != other_provider and host in base_url.lower():
            raise ConfigMismatchError(
                f"模型配置不一致：provider={provider} 与 base_url={base_url} 不匹配，已在请求前阻止发送。"
            )
    if provider == "openai_compatible" and not base_url:
        raise ConfigMismatchError("模型配置不一致：provider=openai_compatible 缺少 base_url，已在请求前阻止发送。")


@dataclass(frozen=True)
class GenerationConfig:
    api_key: str
    model: str = DEFAULT_GOOGLE_MODEL
    provider: str = "google"
    base_url: str = ""
    api_key_source: str = "missing"
    model_source: str = "default"
    base_url_source: str = "default"
    api_keys: tuple[str, ...] = ()
    progressive_visualization_enabled: bool = DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED

    def configured(self) -> bool:
        return bool(self.effective_api_keys())

    def effective_api_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        for key in (self.api_key, *self.api_keys):
            clean = str(key or "").strip()
            if clean and clean not in keys:
                keys.append(clean)
        return tuple(keys)

    def public_metadata(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "api_key_configured": self.configured(),
            "api_key_count": len(self.effective_api_keys()),
            "configured_from": self.api_key_source,
            "model_source": self.model_source,
            "base_url": self.base_url,
            "base_url_source": self.base_url_source,
            "progressive_visualization_enabled": bool(self.progressive_visualization_enabled),
        }


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _read_local_settings(settings_path: Path) -> dict:
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8-sig"))


def _write_local_settings(settings_path: Path, payload: dict) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _coerce_secret_values(value: object) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, tuple):
        raw_items = list(value)
    else:
        raw_items = re.split(r"[\n,]+", str(value or ""))
    result: list[str] = []
    for item in raw_items:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _collect_key_candidates(sources: list[tuple[str, object]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, value in sources:
        values = _coerce_secret_values(value)
        for index, key in enumerate(values):
            if key in seen:
                continue
            seen.add(key)
            indexed_source = source if len(values) == 1 else f"{source}[{index}]"
            result.append((indexed_source, key))
    return result


def _normalize_env_var_name(name: str) -> str:
    clean = str(name or "").strip()
    if clean.lower().startswith("env:"):
        clean = clean[4:].strip()
    if not ENV_VAR_NAME_RE.fullmatch(clean):
        return ""
    return clean


def _collect_env_ref_candidates(source: str, value: object) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for raw_name in _coerce_secret_values(value):
        env_name = _normalize_env_var_name(raw_name)
        if not env_name:
            continue
        env_value = str(os.environ.get(env_name) or "").strip()
        if not env_value:
            continue
        values = _coerce_secret_values(env_value)
        for index, key in enumerate(values):
            indexed_source = f"{source}:{env_name}" if len(values) == 1 else f"{source}:{env_name}[{index}]"
            result.append((indexed_source, key))
    return result


def _merge_key_candidates(*candidate_groups: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group in candidate_groups:
        for source, key in group:
            clean = str(key or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            merged.append((source, clean))
    return merged


def _plaintext_secret_fields(local: dict) -> list[str]:
    found: list[str] = []
    for fields in PROVIDER_PLAINTEXT_FIELDS.values():
        for field in fields:
            value = local.get(field)
            if field.endswith("_api_keys"):
                if isinstance(value, list) and any(str(item or "").strip() for item in value):
                    found.append(field)
            elif str(value or "").strip():
                found.append(field)
    return sorted(set(found))


def load_progressive_visualization_enabled(settings_path: Path | None = None) -> bool:
    local = _read_local_settings(settings_path or DEFAULT_SETTINGS_PATH)
    return _coerce_bool(
        os.environ.get("WORKBENCH_PROGRESSIVE_VISUALIZATION_ENABLED", local.get("progressive_visualization_enabled")),
        DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED,
    )


def load_generation_config(settings_path: Path | None = None, *, provider_override: str = "") -> GenerationConfig:
    path = settings_path or DEFAULT_SETTINGS_PATH
    local = _read_local_settings(path)
    provider = str(provider_override or "").strip().lower()
    if not provider:
        provider = next(
            (
                str(value).strip().lower()
                for value in [
                    local.get("generation_provider") or local.get("provider"),
                    os.environ.get("WORKBENCH_GENERATION_PROVIDER"),
                ]
                if str(value or "").strip()
            ),
            "",
        )
    if not provider:
        provider = DEFAULT_GENERATION_PROVIDER
    if provider == "gemini":
        provider = "google"
    if provider not in {"google", "xiaomi", "siliconflow", "deepseek"}:
        raise ValueError("generation_provider must be google, gemini, xiaomi, siliconflow, or deepseek.")
    env_ref_candidates: list[tuple[str, str]] = []
    if provider == "xiaomi":
        env_ref_candidates = _collect_env_ref_candidates(
            f"envref:file:{path.name}:xiaomi_api_key_env",
            local.get("xiaomi_api_key_env"),
        ) + _collect_env_ref_candidates(
            f"envref:file:{path.name}:xiaomi_api_keys_env",
            local.get("xiaomi_api_keys_env"),
        )
        key_sources = [
            ("env:WORKBENCH_XIAOMI_API_KEYS", os.environ.get("WORKBENCH_XIAOMI_API_KEYS")),
            ("env:WORKBENCH_XIAOMI_API_KEY", os.environ.get("WORKBENCH_XIAOMI_API_KEY")),
            ("env:XIAOMI_API_KEYS", os.environ.get("XIAOMI_API_KEYS")),
            ("env:XIAOMI_API_KEY", os.environ.get("XIAOMI_API_KEY")),
            (f"file:{path.name}:xiaomi_api_keys", local.get("xiaomi_api_keys")),
            (f"file:{path.name}:xiaomi_api_key", local.get("xiaomi_api_key")),
        ]
        model_sources = [
            ("env:WORKBENCH_XIAOMI_MODEL", os.environ.get("WORKBENCH_XIAOMI_MODEL")),
            ("env:XIAOMI_MODEL", os.environ.get("XIAOMI_MODEL")),
            (f"file:{path.name}:xiaomi_model", local.get("xiaomi_model")),
        ]
        base_url_sources = [
            ("env:WORKBENCH_XIAOMI_BASE_URL", os.environ.get("WORKBENCH_XIAOMI_BASE_URL")),
            ("env:XIAOMI_BASE_URL", os.environ.get("XIAOMI_BASE_URL")),
            (f"file:{path.name}:xiaomi_base_url", local.get("xiaomi_base_url")),
        ]
        default_model = DEFAULT_XIAOMI_MODEL
        default_base_url = DEFAULT_XIAOMI_BASE_URL
    elif provider == "siliconflow":
        env_ref_candidates = _collect_env_ref_candidates(
            f"envref:file:{path.name}:siliconflow_api_key_env",
            local.get("siliconflow_api_key_env"),
        ) + _collect_env_ref_candidates(
            f"envref:file:{path.name}:siliconflow_api_keys_env",
            local.get("siliconflow_api_keys_env"),
        )
        key_sources = [
            ("env:WORKBENCH_SILICONFLOW_API_KEYS", os.environ.get("WORKBENCH_SILICONFLOW_API_KEYS")),
            ("env:WORKBENCH_SILICONFLOW_API_KEY", os.environ.get("WORKBENCH_SILICONFLOW_API_KEY")),
            ("env:SILICONFLOW_API_KEY", os.environ.get("SILICONFLOW_API_KEY")),
            (f"file:{path.name}:siliconflow_api_keys", local.get("siliconflow_api_keys")),
            (f"file:{path.name}:siliconflow_api_key", local.get("siliconflow_api_key")),
        ]
        model_sources = [
            ("env:WORKBENCH_SILICONFLOW_MODEL", os.environ.get("WORKBENCH_SILICONFLOW_MODEL")),
            ("env:SILICONFLOW_MODEL", os.environ.get("SILICONFLOW_MODEL")),
            (f"file:{path.name}:siliconflow_model", local.get("siliconflow_model")),
        ]
        base_url_sources = [
            ("env:WORKBENCH_SILICONFLOW_BASE_URL", os.environ.get("WORKBENCH_SILICONFLOW_BASE_URL")),
            ("env:SILICONFLOW_BASE_URL", os.environ.get("SILICONFLOW_BASE_URL")),
            (f"file:{path.name}:siliconflow_base_url", local.get("siliconflow_base_url")),
        ]
        default_model = DEFAULT_SILICONFLOW_MODEL
        default_base_url = DEFAULT_SILICONFLOW_BASE_URL
    elif provider == "deepseek":
        env_ref_candidates = _collect_env_ref_candidates(
            f"envref:file:{path.name}:deepseek_api_key_env",
            local.get("deepseek_api_key_env"),
        ) + _collect_env_ref_candidates(
            f"envref:file:{path.name}:deepseek_api_keys_env",
            local.get("deepseek_api_keys_env"),
        )
        key_sources = [
            ("env:WORKBENCH_DEEPSEEK_API_KEYS", os.environ.get("WORKBENCH_DEEPSEEK_API_KEYS")),
            ("env:WORKBENCH_DEEPSEEK_API_KEY", os.environ.get("WORKBENCH_DEEPSEEK_API_KEY")),
            ("env:DEEPSEEK_API_KEYS", os.environ.get("DEEPSEEK_API_KEYS")),
            ("env:DEEPSEEK_API_KEY", os.environ.get("DEEPSEEK_API_KEY")),
            (f"file:{path.name}:deepseek_api_keys", local.get("deepseek_api_keys")),
            (f"file:{path.name}:deepseek_api_key", local.get("deepseek_api_key")),
        ]
        model_sources = [
            ("env:WORKBENCH_DEEPSEEK_MODEL", os.environ.get("WORKBENCH_DEEPSEEK_MODEL")),
            ("env:DEEPSEEK_MODEL", os.environ.get("DEEPSEEK_MODEL")),
            (f"file:{path.name}:deepseek_model", local.get("deepseek_model")),
        ]
        base_url_sources = [
            ("env:WORKBENCH_DEEPSEEK_BASE_URL", os.environ.get("WORKBENCH_DEEPSEEK_BASE_URL")),
            ("env:DEEPSEEK_BASE_URL", os.environ.get("DEEPSEEK_BASE_URL")),
            (f"file:{path.name}:deepseek_base_url", local.get("deepseek_base_url")),
        ]
        default_model = DEFAULT_DEEPSEEK_MODEL
        default_base_url = DEFAULT_DEEPSEEK_BASE_URL
    else:
        env_ref_candidates = _collect_env_ref_candidates(
            f"envref:file:{path.name}:google_api_key_env",
            local.get("google_api_key_env"),
        ) + _collect_env_ref_candidates(
            f"envref:file:{path.name}:google_api_keys_env",
            local.get("google_api_keys_env"),
        )
        key_sources = [
            ("env:WORKBENCH_GOOGLE_API_KEYS", os.environ.get("WORKBENCH_GOOGLE_API_KEYS")),
            ("env:WORKBENCH_GOOGLE_API_KEY", os.environ.get("WORKBENCH_GOOGLE_API_KEY")),
            ("env:GEMINI_API_KEYS", os.environ.get("GEMINI_API_KEYS")),
            ("env:GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY")),
            ("env:GOOGLE_API_KEY", os.environ.get("GOOGLE_API_KEY")),
            (f"file:{path.name}:google_api_keys", local.get("google_api_keys")),
            (f"file:{path.name}:google_api_key", local.get("google_api_key")),
        ]
        model_sources = [
            ("env:WORKBENCH_GOOGLE_MODEL", os.environ.get("WORKBENCH_GOOGLE_MODEL")),
            ("env:GEMINI_MODEL", os.environ.get("GEMINI_MODEL")),
            (f"file:{path.name}:google_model", local.get("google_model")),
        ]
        base_url_sources = []
        default_model = DEFAULT_GOOGLE_MODEL
        default_base_url = ""
    key_candidates = _merge_key_candidates(env_ref_candidates, _collect_key_candidates(key_sources))
    api_key_source, api_key = key_candidates[0] if key_candidates else ("missing", "")
    model_source, model = next(
        ((source, str(value).strip()) for source, value in model_sources if str(value or "").strip()),
        ("default", default_model),
    )
    model, normalized_model = normalize_model_for_provider(provider, model)
    if normalized_model and model_source != "default":
        model_source = f"normalized_from_{model_source}"
    base_url_source, base_url = next(
        ((source, str(value).strip().rstrip("/")) for source, value in base_url_sources if str(value or "").strip()),
        ("default", default_base_url),
    )
    progressive_visualization_enabled = load_progressive_visualization_enabled(path)
    config = GenerationConfig(
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url,
        api_key_source=api_key_source,
        model_source=model_source,
        base_url_source=base_url_source,
        api_keys=tuple(key for _, key in key_candidates),
        progressive_visualization_enabled=progressive_visualization_enabled,
    )
    validate_generation_config(config)
    return config


def load_generation_fallback_chain(settings_path: Path | None = None) -> tuple[GenerationConfig, ...]:
    """Return configured providers in the local fallback order."""
    path = settings_path or DEFAULT_SETTINGS_PATH
    configured: list[GenerationConfig] = []
    for provider in PROVIDER_FALLBACK_ORDER:
        config = load_generation_config(path, provider_override=provider)
        if config.configured():
            configured.append(config)
    if configured:
        return tuple(configured)
    return (load_generation_config(path),)


def generation_model_presets() -> dict[str, list[str]]:
    return {
        "google": [
            DEFAULT_GOOGLE_MODEL,
            "gemini-3.5-pro",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
        "xiaomi": [
            DEFAULT_XIAOMI_MODEL,
        ],
        "siliconflow": [
            DEFAULT_SILICONFLOW_MODEL,
        ],
        "deepseek": [
            DEFAULT_DEEPSEEK_MODEL,
            "deepseek-v4-pro",
            "deepseek-chat",
        ],
    }


def public_generation_settings(settings_path: Path | None = None) -> dict:
    path = settings_path or DEFAULT_SETTINGS_PATH
    local = _read_local_settings(path)
    plaintext_fields = _plaintext_secret_fields(local)
    warnings: list[str] = []
    if plaintext_fields:
        warnings.append(
            "Detected plaintext API key fields in settings.local.json. Migrate to *_api_key_env references."
        )
    presets = generation_model_presets()
    local_provider = str(local.get("generation_provider") or local.get("provider") or "")
    try:
        config = load_generation_config(path)
    except ValueError as exc:
        return {
            "provider": "",
            "model": "",
            "base_url": "",
            "fallback_order": list(PROVIDER_FALLBACK_ORDER),
            "api_key_configured": False,
            "api_key_count": 0,
            "configured_from": "invalid_provider",
            "api_key_env": "",
            "secret_persistence": "env_ref_only",
            "plaintext_secret_fields": plaintext_fields,
            "security_warnings": warnings,
            "model_source": "",
            "base_url_source": "",
            "settings_path": str(path),
            "presets": presets,
            "local_provider": local_provider,
            "progressive_visualization_enabled": bool(
                _coerce_bool(local.get("progressive_visualization_enabled"), DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED)
            ),
            "provider_config_valid": False,
            "config_error": str(exc),
        }
    return {
        "provider": config.provider,
        "model": config.model,
        "base_url": config.base_url,
        "fallback_order": list(PROVIDER_FALLBACK_ORDER),
        "api_key_configured": config.configured(),
        "api_key_count": len(config.effective_api_keys()),
        "configured_from": config.api_key_source,
        "api_key_env": str(local.get(f"{config.provider}_api_key_env") or ""),
        "secret_persistence": "env_ref_only",
        "plaintext_secret_fields": plaintext_fields,
        "security_warnings": warnings,
        "model_source": config.model_source,
        "base_url_source": config.base_url_source,
        "settings_path": str(path),
        "presets": presets,
        "local_provider": local_provider,
        "progressive_visualization_enabled": bool(
            _coerce_bool(local.get("progressive_visualization_enabled"), config.progressive_visualization_enabled)
        ),
        "provider_config_valid": True,
        "config_error": "",
    }


def update_generation_settings(payload: dict, settings_path: Path | None = None) -> dict:
    path = settings_path or DEFAULT_SETTINGS_PATH
    local = _read_local_settings(path)
    provider = str(payload.get("provider") or local.get("generation_provider") or local.get("provider") or DEFAULT_GENERATION_PROVIDER).strip().lower()
    if provider == "gemini":
        provider = "google"
    if provider not in {"google", "xiaomi", "siliconflow", "deepseek"}:
        raise ValueError("provider must be google, xiaomi, siliconflow, or deepseek.")
    model = str(payload.get("model") or "").strip()
    model, _ = normalize_model_for_provider(provider, model)
    if len(model) > 160:
        raise ValueError("model is too long.")
    api_key = str(payload.get("api_key") or "").strip()
    api_key_env = _normalize_env_var_name(str(payload.get("api_key_env") or ""))
    existing_api_key_env = _normalize_env_var_name(str(local.get(f"{provider}_api_key_env") or ""))
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    progressive_visualization_enabled = _coerce_bool(
        payload.get("progressive_visualization_enabled"),
        _coerce_bool(local.get("progressive_visualization_enabled"), DEFAULT_PROGRESSIVE_VISUALIZATION_ENABLED),
    )

    local["generation_provider"] = provider
    for fields in PROVIDER_PLAINTEXT_FIELDS.values():
        for field in fields:
            local.pop(field, None)
    for field in PROVIDER_SECRET_FIELDS.get(provider, ()):
        local.pop(field, None)
    if api_key:
        # Runtime-only secret injection: keep plaintext key out of settings.local.json.
        default_env_name = PROVIDER_PRIMARY_ENV[provider]
        os.environ[default_env_name] = api_key
        local[f"{provider}_api_key_env"] = api_key_env or default_env_name
    elif api_key_env:
        local[f"{provider}_api_key_env"] = api_key_env
    elif existing_api_key_env:
        local[f"{provider}_api_key_env"] = existing_api_key_env
    if provider == "google":
        local["google_model"] = model
    elif provider == "xiaomi":
        local["xiaomi_model"] = model
        local["xiaomi_base_url"] = base_url or DEFAULT_XIAOMI_BASE_URL
    elif provider == "siliconflow":
        local["siliconflow_model"] = model
        local["siliconflow_base_url"] = base_url or DEFAULT_SILICONFLOW_BASE_URL
    else:
        local["deepseek_model"] = model
        local["deepseek_base_url"] = base_url or DEFAULT_DEEPSEEK_BASE_URL
    local["progressive_visualization_enabled"] = bool(progressive_visualization_enabled)

    _write_local_settings(path, local)
    return public_generation_settings(path)
