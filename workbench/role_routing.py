from __future__ import annotations

import json
from pathlib import Path

from workbench.connections import DEFAULT_CONNECTIONS_PATH, _connection_api_key, _find_connection, _read_connections_file
from workbench.generation_settings import (
    GenerationConfig,
    default_model_for_provider,
    load_progressive_visualization_enabled,
)

DEFAULT_ROLE_ROUTING_PATH = Path(__file__).resolve().parent / "role_routing.local.json"
ROLE_ROUTING_FILE_VERSION = 1
GENERATION_ROLES = ("content_planning", "svg_generation", "page_regeneration")
ROLE_ENTRY_FIELDS = {"connection_id", "model_id"}

__all__ = [
    "DEFAULT_ROLE_ROUTING_PATH",
    "GENERATION_ROLES",
    "load_role_routing",
    "resolve_role_config",
    "update_role_routing",
]


def _empty_entry() -> dict:
    return {"connection_id": "", "model_id": ""}


def load_role_routing(path: Path | None = None) -> dict:
    target = path or DEFAULT_ROLE_ROUTING_PATH
    roles = {role: _empty_entry() for role in GENERATION_ROLES}
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
        stored = payload.get("roles") if isinstance(payload.get("roles"), dict) else {}
        for role in GENERATION_ROLES:
            entry = stored.get(role)
            if isinstance(entry, dict):
                roles[role] = {
                    "connection_id": str(entry.get("connection_id") or "").strip(),
                    "model_id": str(entry.get("model_id") or "").strip(),
                }
    return {"version": ROLE_ROUTING_FILE_VERSION, "roles": roles}


def update_role_routing(path: Path | None, roles_payload: object, connections_path: Path | None = None) -> dict:
    target = path or DEFAULT_ROLE_ROUTING_PATH
    if not isinstance(roles_payload, dict) or not roles_payload:
        raise ValueError("roles must be a non-empty object keyed by generation role.")
    unknown_roles = sorted(set(roles_payload) - set(GENERATION_ROLES))
    if unknown_roles:
        raise ValueError(f"Unknown roles: {', '.join(unknown_roles)}. Allowed: {', '.join(GENERATION_ROLES)}.")
    data = load_role_routing(target)
    connections_data = None
    for role, raw_entry in roles_payload.items():
        if not isinstance(raw_entry, dict):
            raise ValueError(f"Role entry for {role} must be an object.")
        unknown_fields = sorted(set(raw_entry) - ROLE_ENTRY_FIELDS)
        if unknown_fields:
            raise ValueError(f"Unsupported fields for {role}: {', '.join(unknown_fields)}.")
        entry = dict(data["roles"][role])
        if "connection_id" in raw_entry:
            entry["connection_id"] = str(raw_entry.get("connection_id") or "").strip()
        if "model_id" in raw_entry:
            entry["model_id"] = str(raw_entry.get("model_id") or "").strip()
        if entry["model_id"] and not entry["connection_id"]:
            raise ValueError(f"model_id for {role} requires a connection_id.")
        if entry["connection_id"] and connections_path is not None:
            if connections_data is None:
                connections_data = _read_connections_file(connections_path)
            try:
                _find_connection(connections_data, entry["connection_id"])
            except KeyError:
                raise ValueError(f"Connection not found for {role}: {entry['connection_id']}.") from None
        data["roles"][role] = entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def _config_from_connection(
    record: dict,
    model_id: str,
    settings_path: Path | None = None,
    model_source: str = "role_routing",
) -> GenerationConfig:
    provider = str(record.get("provider") or "")
    stored_models = [str(item) for item in record.get("models") or [] if str(item or "").strip()]
    model = model_id or (stored_models[0] if stored_models else "") or default_model_for_provider(provider)
    return GenerationConfig(
        api_key=_connection_api_key(record),
        model=model,
        provider=provider,
        base_url=str(record.get("base_url") or ""),
        api_key_source=f"connection:{record.get('id')}",
        model_source=model_source,
        # 角色路由只替换模型与密钥来源，全局渐进可视化开关必须原样继承。
        progressive_visualization_enabled=load_progressive_visualization_enabled(settings_path),
    )


def _default_connection_config(
    role: str,
    connections_path: Path | None,
    settings_path: Path | None,
) -> GenerationConfig | None:
    """C08-b：角色未配路由时，默认取第一个已启用且带模型列表的连接；无候选时回落旧体系。"""
    data = _read_connections_file(connections_path or DEFAULT_CONNECTIONS_PATH)
    record = next(
        (
            item
            for item in data["connections"]
            if item.get("enabled", True) and any(str(model or "").strip() for model in item.get("models") or [])
        ),
        None,
    )
    if record is None:
        return None
    config = _config_from_connection(record, "", settings_path=settings_path, model_source="default_connection")
    if not config.configured():
        raise ValueError(
            f"Default connection {record.get('id')} for {role} "
            f"has empty API key env {record.get('api_key_env') or ''}."
        )
    return config


def resolve_role_config(
    role: str,
    routing_path: Path | None = None,
    connections_path: Path | None = None,
    settings_path: Path | None = None,
) -> GenerationConfig | None:
    if role not in GENERATION_ROLES:
        raise ValueError(f"Unknown role: {role}. Allowed: {', '.join(GENERATION_ROLES)}.")
    roles = load_role_routing(routing_path)["roles"]
    entry = roles[role]
    if not entry["connection_id"] and role == "page_regeneration":
        entry = roles["svg_generation"]
    if not entry["connection_id"]:
        # C08-b：未配路由 → 默认启用连接 → 旧体系兜底（返回 None 由调用方走 load_generation_config）。
        return _default_connection_config(role, connections_path, settings_path)
    data = _read_connections_file(connections_path or DEFAULT_CONNECTIONS_PATH)
    try:
        record = _find_connection(data, entry["connection_id"])
    except KeyError:
        raise ValueError(f"Role routing for {role} points to a missing connection: {entry['connection_id']}.") from None
    if not record.get("enabled", True):
        raise ValueError(f"Role routing for {role} points to a disabled connection: {entry['connection_id']}.")
    config = _config_from_connection(record, entry["model_id"], settings_path=settings_path)
    if not config.configured():
        raise ValueError(
            f"Role routing for {role} points to connection {entry['connection_id']} "
            f"whose API key env {record.get('api_key_env') or ''} is empty."
        )
    return config
