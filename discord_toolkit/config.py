from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TypingSettings:
    enabled: bool = True


def get_typing_settings(config: Any) -> TypingSettings:
    section = _as_mapping(_mapping_get(config, "typing", {}))
    return TypingSettings(
        enabled=_coerce_bool(_mapping_get(section, "enabled", True), default=True),
    )


def _mapping_get(obj: Any, key: str, default: Any) -> Any:
    if obj is None:
        return default
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            return getter(key)
    return default


def _as_mapping(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if obj is None:
        return {}
    getter = getattr(obj, "items", None)
    if callable(getter):
        try:
            return dict(getter())
        except Exception:
            return {}
    try:
        return dict(obj)
    except Exception:
        return {}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default
