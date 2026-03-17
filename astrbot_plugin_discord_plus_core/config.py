from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TypingSettings:
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MessageDecorationSettings:
    mention_fix_enabled: bool = True
    reply_reference_enabled: bool = True


@dataclass(frozen=True, slots=True)
class SendPermissionRule:
    scope_type: str
    allow: bool = False
    guild_id: str = ""
    guild_name: str = ""
    category_id: str = ""
    category_name: str = ""
    channel_id: str = ""
    channel_name: str = ""
    thread_id: str = ""
    thread_name: str = ""


@dataclass(frozen=True, slots=True)
class SendPermissionSettings:
    enabled: bool = True
    rules: tuple[SendPermissionRule, ...] = ()


def get_typing_settings(config: Any) -> TypingSettings:
    return TypingSettings(
        enabled=_coerce_bool(_mapping_get(config, "typing_enabled", True), default=True),
    )


def get_message_decoration_settings(config: Any) -> MessageDecorationSettings:
    return MessageDecorationSettings(
        mention_fix_enabled=_coerce_bool(
            _mapping_get(config, "mention_fix_enabled", True),
            default=True,
        ),
        reply_reference_enabled=_coerce_bool(
            _mapping_get(config, "reply_reference_enabled", True),
            default=True,
        ),
    )


def get_send_permission_settings(config: Any) -> SendPermissionSettings:
    raw_rules = _mapping_get(config, "send_permission_rules", [])
    return SendPermissionSettings(
        enabled=_coerce_bool(
            _mapping_get(config, "send_permission_override_enabled", True),
            default=True,
        ),
        rules=_coerce_send_permission_rules(raw_rules),
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


def _coerce_send_permission_rules(value: Any) -> tuple[SendPermissionRule, ...]:
    if not isinstance(value, list):
        return ()

    rules: list[SendPermissionRule] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        scope_type = _coerce_str(
            item.get("__template_key"),
            _infer_scope_type(item),
        )
        if scope_type not in {"guild", "category", "channel", "thread"}:
            continue

        rules.append(
            SendPermissionRule(
                scope_type=scope_type,
                allow=_coerce_bool(item.get("allow"), default=False),
                guild_id=_coerce_str(item.get("guild_id")),
                guild_name=_coerce_str(item.get("guild_name")),
                category_id=_coerce_str(item.get("category_id")),
                category_name=_coerce_str(item.get("category_name")),
                channel_id=_coerce_str(item.get("channel_id")),
                channel_name=_coerce_str(item.get("channel_name")),
                thread_id=_coerce_str(item.get("thread_id")),
                thread_name=_coerce_str(item.get("thread_name")),
            )
        )

    return tuple(rules)


def _infer_scope_type(value: dict[str, Any]) -> str:
    if _coerce_str(value.get("thread_id")):
        return "thread"
    if _coerce_str(value.get("channel_id")):
        return "channel"
    if _coerce_str(value.get("category_id")):
        return "category"
    return "guild"


def _coerce_str(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


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
