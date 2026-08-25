from __future__ import annotations

import http.client
import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

from workbench.generation_settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_SETTINGS_PATH,
    DEFAULT_SILICONFLOW_BASE_URL,
    DEFAULT_XIAOMI_BASE_URL,
    PROVIDER_PRIMARY_ENV,
    _normalize_env_var_name,
    _read_local_settings,
    default_model_for_provider,
    generation_model_presets,
)

DEFAULT_CONNECTIONS_PATH = Path(__file__).resolve().parent / "connections.local.json"
CONNECTIONS_FILE_VERSION = 1
KNOWN_CONNECTION_PROVIDERS = ("google", "xiaomi", "siliconflow", "deepseek", "openai_compatible")
GOOGLE_MODELS_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
CONNECTION_TEST_TIMEOUT_SECONDS = 10
CONNECTION_GENERATION_PROBE_TIMEOUT_SECONDS = 30
CONNECTION_ERROR_LIMIT = 500
MISSING_KEY_MESSAGE = "未配置 API 密钥：环境变量 {env} 为空，请先在服务端配置。"
CONNECTION_SECRET_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{8,}\b"),
    re.compile(r"([?&](?:api_key|key|token|access_token)=)[^&\s]+", re.I),
)

__all__ = [
    "DEFAULT_CONNECTIONS_PATH",
    "KNOWN_CONNECTION_PROVIDERS",
    "create_connection",
    "delete_connection",
    "list_connection_models",
    "list_connections",
    "seed_connection_from_settings",
    "test_connection",
    "update_connection",
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_connections_file(path: Path) -> dict:
    if not path.exists():
        return {"version": CONNECTIONS_FILE_VERSION, "connections": []}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    records = payload.get("connections")
    if not isinstance(records, list):
        records = []
    data = {"version": CONNECTIONS_FILE_VERSION, "connections": [item for item in records if isinstance(item, dict)]}
    # C08-b：迁移标记必须随读写保留，防止用户删光连接后重复迁移。
    if payload.get("seeded_from_settings"):
        data["seeded_from_settings"] = True
    return data


def _write_connections_file(path: Path, payload: dict) -> None:
    # 防御性剔除：任何形态的明文密钥字段都不允许写盘。
    for record in payload.get("connections", []):
        record.pop("api_key", None)
        record.pop("api_keys", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _derived_env_name(connection_id: str) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]", "", str(connection_id).removeprefix("conn-")).upper()
    return f"WORKBENCH_CONNECTION_{suffix}_API_KEY"


def _connection_api_key(record: dict) -> str:
    env_name = str(record.get("api_key_env") or "")
    if not env_name:
        return ""
    return str(os.environ.get(env_name) or "").strip()


def _api_key_hint(record: dict) -> str:
    # C07：仅在公开视图派生末 4 位；短密钥（<8 位）不展示，避免泄露过半内容。
    api_key = _connection_api_key(record)
    if len(api_key) < 8:
        return ""
    return api_key[-4:]


def sanitize_connection_error_message(message: object, secrets: list[str] | None = None) -> str:
    text = re.sub(r"\s+", " ", str(message or "")).strip()
    for secret in secrets or []:
        clean = str(secret or "").strip()
        if clean:
            text = text.replace(clean, "[redacted]")
    for pattern in CONNECTION_SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[redacted]" if match.lastindex else "[redacted]", text)
    if len(text) > CONNECTION_ERROR_LIMIT:
        text = text[: CONNECTION_ERROR_LIMIT - 3].rstrip() + "..."
    return text


def public_connection_view(record: dict) -> dict:
    return {
        "id": str(record.get("id") or ""),
        "name": str(record.get("name") or ""),
        "provider": str(record.get("provider") or ""),
        "base_url": str(record.get("base_url") or ""),
        "models": [str(item) for item in record.get("models") or [] if str(item or "").strip()],
        "api_key_env": str(record.get("api_key_env") or ""),
        "api_key_configured": bool(_connection_api_key(record)),
        "api_key_hint": _api_key_hint(record),
        "enabled": bool(record.get("enabled", True)),
        "created_at": str(record.get("created_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
    }


def list_connections(path: Path | None = None) -> list[dict]:
    payload = _read_connections_file(path or DEFAULT_CONNECTIONS_PATH)
    return [public_connection_view(record) for record in payload["connections"]]


def seed_connection_from_settings(path: Path | None = None, settings_path: Path | None = None) -> None:
    """C08-b 一次性迁移：连接列表为空且旧体系 settings 有显式 provider 时，自动建一条连接。

    幂等保证：文件顶层 seeded_from_settings 标记落盘后不再触发，即使用户删光连接。
    """
    target = path or DEFAULT_CONNECTIONS_PATH
    data = _read_connections_file(target)
    if data["connections"] or data.get("seeded_from_settings"):
        return
    resolved_settings = settings_path or DEFAULT_SETTINGS_PATH
    if not resolved_settings.exists():
        return
    local = _read_local_settings(resolved_settings)
    provider = str(local.get("generation_provider") or local.get("provider") or "").strip().lower()
    if provider == "gemini":
        provider = "google"
    if provider not in PROVIDER_PRIMARY_ENV:
        return
    # 迁移语义是“搬 settings 文件里的显式配置”，不能走 load_generation_config（会混入本机环境变量）。
    default_base_urls = {
        "xiaomi": DEFAULT_XIAOMI_BASE_URL,
        "siliconflow": DEFAULT_SILICONFLOW_BASE_URL,
        "deepseek": DEFAULT_DEEPSEEK_BASE_URL,
        "google": "",
    }
    model = str(local.get(f"{provider}_model") or "").strip() or default_model_for_provider(provider)
    base_url = str(local.get(f"{provider}_base_url") or "").strip().rstrip("/") or default_base_urls[provider]
    api_key_env = _normalize_env_var_name(str(local.get(f"{provider}_api_key_env") or "")) or PROVIDER_PRIMARY_ENV[provider]
    now = _now_iso()
    record = {
        "id": f"conn-{uuid.uuid4().hex[:8]}",
        "name": "默认连接（迁移自全局设置）",
        "provider": provider,
        "base_url": base_url,
        "models": [model] if model else [],
        "api_key_env": api_key_env,
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    data["connections"].append(record)
    data["seeded_from_settings"] = True
    _write_connections_file(target, data)


def _coerce_models(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("models must be a list of model ids.")
    result: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def _apply_secret_fields(record: dict, payload: dict) -> None:
    api_key = str(payload.get("api_key") or "").strip()
    raw_env = payload.get("api_key_env")
    if raw_env is not None:
        env_name = _normalize_env_var_name(str(raw_env))
        if not env_name:
            raise ValueError("api_key_env must be a valid environment variable name.")
        record["api_key_env"] = env_name
    if api_key:
        env_name = str(record.get("api_key_env") or "") or _derived_env_name(str(record.get("id") or ""))
        os.environ[env_name] = api_key
        record["api_key_env"] = env_name


def create_connection(path: Path | None, payload: dict) -> dict:
    target = path or DEFAULT_CONNECTIONS_PATH
    name = str(payload.get("name") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()
    if not name:
        raise ValueError("name is required.")
    if provider not in KNOWN_CONNECTION_PROVIDERS:
        raise ValueError(f"provider must be one of: {', '.join(KNOWN_CONNECTION_PROVIDERS)}.")
    if provider == "openai_compatible" and not base_url:
        raise ValueError("base_url is required for openai_compatible connections.")
    now = _now_iso()
    record = {
        "id": f"conn-{uuid.uuid4().hex[:8]}",
        "name": name,
        "provider": provider,
        "base_url": base_url,
        "models": _coerce_models(payload.get("models") if payload.get("models") is not None else []),
        "api_key_env": "",
        "enabled": True,
        "created_at": now,
        "updated_at": now,
    }
    _apply_secret_fields(record, payload)
    data = _read_connections_file(target)
    data["connections"].append(record)
    _write_connections_file(target, data)
    return public_connection_view(record)


def _find_connection(data: dict, connection_id: str) -> dict:
    for record in data["connections"]:
        if str(record.get("id") or "") == connection_id:
            return record
    raise KeyError(connection_id)


CONNECTION_UPDATE_FIELDS = {"name", "base_url", "models", "api_key", "api_key_env", "enabled"}


def update_connection(path: Path | None, connection_id: str, payload: dict) -> dict:
    target = path or DEFAULT_CONNECTIONS_PATH
    unknown = sorted(set(payload) - CONNECTION_UPDATE_FIELDS)
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(unknown)}.")
    data = _read_connections_file(target)
    record = _find_connection(data, connection_id)
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name must not be empty.")
        record["name"] = name
    if "base_url" in payload:
        base_url = str(payload.get("base_url") or "").strip()
        if record.get("provider") == "openai_compatible" and not base_url:
            raise ValueError("base_url is required for openai_compatible connections.")
        record["base_url"] = base_url
    if "models" in payload:
        record["models"] = _coerce_models(payload.get("models"))
    if "enabled" in payload:
        record["enabled"] = bool(payload.get("enabled"))
    _apply_secret_fields(record, payload)
    record["updated_at"] = _now_iso()
    _write_connections_file(target, data)
    return public_connection_view(record)


def delete_connection(path: Path | None, connection_id: str) -> dict:
    # 物理删除连接记录；派生环境变量中的密钥一并清理，用户自管环境变量不动。
    target = path or DEFAULT_CONNECTIONS_PATH
    data = _read_connections_file(target)
    record = _find_connection(data, connection_id)
    removed = public_connection_view(record)
    env_name = str(record.get("api_key_env") or "")
    if env_name and env_name == _derived_env_name(connection_id):
        os.environ.pop(env_name, None)
    data["connections"] = [item for item in data["connections"] if str(item.get("id") or "") != connection_id]
    _write_connections_file(target, data)
    return removed


def _http_get_json(url: str, headers: dict[str, str], timeout: int = CONNECTION_TEST_TIMEOUT_SECONDS) -> tuple[int, dict]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise OSError(f"HTTP {exc.code}: {exc.reason}") from exc
    except http.client.HTTPException as exc:
        raise OSError(f"HTTP protocol error: {type(exc).__name__}") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}
    return status, payload if isinstance(payload, dict) else {}


def _models_probe_target(record: dict, api_key: str) -> tuple[str, dict[str, str]]:
    if str(record.get("provider") or "") == "google":
        return f"{GOOGLE_MODELS_ENDPOINT}?key={api_key}", {}
    base_url = str(record.get("base_url") or "").rstrip("/")
    if not base_url:
        raise ValueError("base_url is required to reach this connection.")
    return f"{base_url}/models", {"Authorization": f"Bearer {api_key}"}


def test_connection(path: Path | None, connection_id: str) -> dict:
    target = path or DEFAULT_CONNECTIONS_PATH
    record = _find_connection(_read_connections_file(target), connection_id)
    env_name = str(record.get("api_key_env") or "") or "(未设置)"
    api_key = _connection_api_key(record)
    checked_at = _now_iso()
    if not api_key:
        return {"ok": False, "status_code": 0, "message": MISSING_KEY_MESSAGE.format(env=env_name), "checked_at": checked_at}
    provider = str(record.get("provider") or "")
    stored_models = [str(item) for item in record.get("models") or [] if str(item or "").strip()]
    model = (stored_models[0] if stored_models else "") or default_model_for_provider(provider)
    # 用首个模型发一次最小真实生成调用：模型列表接口在项目被拒时仍返回 200，只有
    # 真正的 generateContent/chat 接口才会暴露 403/额度/模型不存在等问题，避免假绿灯。
    from workbench.generation import probe_connection_generation, user_facing_generation_error

    try:
        probe_connection_generation(
            provider,
            model,
            api_key,
            str(record.get("base_url") or ""),
            timeout=CONNECTION_GENERATION_PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - 任何生成失败都应如实报告为连接测试失败
        return {
            "ok": False,
            "status_code": 0,
            "message": sanitize_connection_error_message(user_facing_generation_error(exc), secrets=[api_key]),
            "checked_at": checked_at,
        }
    return {
        "ok": True,
        "status_code": 200,
        "message": f"连接测试通过（已用 {model} 实测生成）。",
        "checked_at": checked_at,
    }


def _remote_model_ids(provider: str, payload: dict) -> list[str]:
    if provider == "google":
        raw_items = payload.get("models") or []
        names = [str(item.get("name") or "") for item in raw_items if isinstance(item, dict)]
        return [name.removeprefix("models/") for name in names if name]
    raw_items = payload.get("data") or []
    return [str(item.get("id") or "") for item in raw_items if isinstance(item, dict) and item.get("id")]


def list_connection_models(path: Path | None, connection_id: str) -> dict:
    target = path or DEFAULT_CONNECTIONS_PATH
    record = _find_connection(_read_connections_file(target), connection_id)
    provider = str(record.get("provider") or "")
    stored = [str(item) for item in record.get("models") or [] if str(item or "").strip()]
    api_key = _connection_api_key(record)
    if api_key:
        try:
            url, headers = _models_probe_target(record, api_key)
            _status, payload = _http_get_json(url, headers)
            remote = _remote_model_ids(provider, payload)
            if remote:
                return {"models": remote, "source": "remote"}
        except (OSError, ValueError):
            pass
    fallback: list[str] = []
    for model in stored + generation_model_presets().get(provider, []):
        if model and model not in fallback:
            fallback.append(model)
    return {"models": fallback, "source": "fallback"}
