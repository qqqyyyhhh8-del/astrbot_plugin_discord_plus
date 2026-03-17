from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TypingSettings:
    enabled: bool = True


def get_typing_settings(config: Any) -> TypingSettings:
    return TypingSettings(
        enabled=_coerce_bool(_mapping_get(config, "typing_enabled", True), default=True),
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
