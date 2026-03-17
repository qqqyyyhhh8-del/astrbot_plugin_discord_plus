from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from astrbot_plugin_discord_plus_core.config import SendPermissionRule, SendPermissionSettings
from astrbot_plugin_discord_plus_core.discord_bridge import (
    DiscordMessageScope,
    get_discord_client,
    get_discord_scope,
    is_discord_event,
)
from astrbot_plugin_discord_plus_core.feature_base import FeatureBase


@dataclass(frozen=True, slots=True)
class SendPermissionRefreshResult:
    rules: tuple[SendPermissionRule, ...]
    guild_count: int
    category_count: int
    channel_count: int
    thread_count: int

    @property
    def total_rules(self) -> int:
        return len(self.rules)


class DiscordSendPermissionFeature(FeatureBase):
    name = "discord_send_permission"

    def __init__(
        self,
        logger: Any,
        config_getter: Callable[[], SendPermissionSettings],
    ):
        self._logger = logger
        self._config_getter = config_getter

    async def on_waiting_llm_request(self, event: Any) -> None:
        if not is_discord_event(event):
            return

        scope = get_discord_scope(event)
        if scope is None:
            return

        settings = self._config_getter()
        if not settings.enabled:
            return

        if is_scope_allowed(scope, settings.rules):
            return

        stopper = getattr(event, "stop_event", None)
        if callable(stopper):
            stopper()
        _log_debug_or_warning(
            self._logger,
            "discord send blocked by override: guild=%s channel=%s thread=%s",
            scope.guild_id or "-",
            scope.channel_id or "-",
            scope.thread_id or "-",
        )

    def refresh_rules_from_event(self, event: Any) -> SendPermissionRefreshResult | None:
        client = get_discord_client(event)
        if client is None:
            return None
        return build_refresh_result(client, self._config_getter().rules)

    def inspect_event(self, event: Any) -> tuple[DiscordMessageScope, bool] | None:
        if not is_discord_event(event):
            return None

        scope = get_discord_scope(event)
        if scope is None:
            return None

        settings = self._config_getter()
        allowed = True if not settings.enabled else is_scope_allowed(scope, settings.rules)
        return scope, allowed


def is_scope_allowed(scope: DiscordMessageScope, rules: Iterable[SendPermissionRule]) -> bool:
    best_specificity = -1
    best_index = -1
    best_allow = False

    for index, rule in enumerate(rules):
        if not _rule_matches(scope, rule):
            continue

        specificity = _rule_specificity(rule)
        if specificity > best_specificity or (
            specificity == best_specificity and index > best_index
        ):
            best_specificity = specificity
            best_index = index
            best_allow = rule.allow

    if best_specificity < 0:
        return False
    return best_allow


def serialize_send_permission_rules(rules: Iterable[SendPermissionRule]) -> list[dict[str, Any]]:
    return [_serialize_rule(rule) for rule in rules]


def get_send_permission_rule_key(rule: SendPermissionRule) -> tuple[str, str, str, str, str]:
    return _rule_key(rule)


def build_refresh_result(
    client: Any,
    existing_rules: Iterable[SendPermissionRule],
) -> SendPermissionRefreshResult:
    current_rules = list(existing_rules)
    existing_by_key = {_rule_key(rule): rule for rule in current_rules}
    discovered_rules: list[SendPermissionRule] = []
    discovered_keys: set[tuple[str, str, str, str, str]] = set()

    guild_count = 0
    category_count = 0
    channel_count = 0
    thread_count = 0

    guilds = sorted(getattr(client, "guilds", []), key=_object_sort_key)
    for guild in guilds:
        guild_scope = DiscordMessageScope(
            guild_id=_snowflake_str(getattr(guild, "id", None)),
            guild_name=_display_name(guild),
        )
        if not guild_scope.guild_id:
            continue

        guild_rule = _rule_from_scope("guild", guild_scope, existing_by_key)
        discovered_rules.append(guild_rule)
        discovered_keys.add(_rule_key(guild_rule))
        guild_count += 1

        for category in sorted(getattr(guild, "categories", []), key=_object_sort_key):
            category_scope = DiscordMessageScope(
                guild_id=guild_scope.guild_id,
                guild_name=guild_scope.guild_name,
                category_id=_snowflake_str(getattr(category, "id", None)),
                category_name=_display_name(category),
            )
            if not category_scope.category_id:
                continue

            category_rule = _rule_from_scope("category", category_scope, existing_by_key)
            discovered_rules.append(category_rule)
            discovered_keys.add(_rule_key(category_rule))
            category_count += 1

        for channel in sorted(getattr(guild, "channels", []), key=_object_sort_key):
            if not _is_message_channel(channel):
                continue

            channel_scope = DiscordMessageScope(
                guild_id=guild_scope.guild_id,
                guild_name=guild_scope.guild_name,
                category_id=_snowflake_str(getattr(channel, "category_id", None)),
                category_name=_display_name(getattr(channel, "category", None)),
                channel_id=_snowflake_str(getattr(channel, "id", None)),
                channel_name=_display_name(channel),
            )
            if not channel_scope.channel_id:
                continue

            channel_rule = _rule_from_scope("channel", channel_scope, existing_by_key)
            discovered_rules.append(channel_rule)
            discovered_keys.add(_rule_key(channel_rule))
            channel_count += 1

        for thread in sorted(getattr(guild, "threads", []), key=_object_sort_key):
            parent = getattr(thread, "parent", None)
            thread_scope = DiscordMessageScope(
                guild_id=guild_scope.guild_id,
                guild_name=guild_scope.guild_name,
                category_id=_snowflake_str(getattr(parent, "category_id", None)),
                category_name=_display_name(getattr(parent, "category", None)),
                channel_id=_snowflake_str(getattr(thread, "parent_id", None))
                or _snowflake_str(getattr(parent, "id", None)),
                channel_name=_display_name(parent),
                thread_id=_snowflake_str(getattr(thread, "id", None)),
                thread_name=_display_name(thread),
            )
            if not thread_scope.thread_id or not thread_scope.channel_id:
                continue

            thread_rule = _rule_from_scope("thread", thread_scope, existing_by_key)
            discovered_rules.append(thread_rule)
            discovered_keys.add(_rule_key(thread_rule))
            thread_count += 1

    extras = [rule for rule in current_rules if _rule_key(rule) not in discovered_keys]
    return SendPermissionRefreshResult(
        rules=tuple(discovered_rules + extras),
        guild_count=guild_count,
        category_count=category_count,
        channel_count=channel_count,
        thread_count=thread_count,
    )


def describe_scope(scope: DiscordMessageScope) -> str:
    parts = [
        f"服务器: {scope.guild_name or '-'} ({scope.guild_id or '-'})",
        f"分类: {scope.category_name or '-'} ({scope.category_id or '-'})",
        f"频道: {scope.channel_name or '-'} ({scope.channel_id or '-'})",
        f"线程: {scope.thread_name or '-'} ({scope.thread_id or '-'})",
    ]
    return "\n".join(parts)


def _rule_matches(scope: DiscordMessageScope, rule: SendPermissionRule) -> bool:
    if not rule.guild_id or rule.guild_id != scope.guild_id:
        return False
    if rule.scope_type == "guild":
        return True
    if rule.scope_type == "category":
        return bool(rule.category_id) and rule.category_id == scope.category_id
    if rule.scope_type == "channel":
        return bool(rule.channel_id) and rule.channel_id == scope.channel_id
    if rule.scope_type == "thread":
        return bool(rule.thread_id) and rule.thread_id == scope.thread_id
    return False


def _rule_specificity(rule: SendPermissionRule) -> int:
    if rule.scope_type == "thread":
        return 4
    if rule.scope_type == "channel":
        return 3
    if rule.scope_type == "category":
        return 2
    if rule.scope_type == "guild":
        return 1
    return 0


def _rule_key(rule: SendPermissionRule) -> tuple[str, str, str, str, str]:
    return (
        rule.scope_type,
        rule.guild_id,
        rule.category_id,
        rule.channel_id,
        rule.thread_id,
    )


def _rule_from_scope(
    scope_type: str,
    scope: DiscordMessageScope,
    existing_by_key: dict[tuple[str, str, str, str, str], SendPermissionRule],
) -> SendPermissionRule:
    key = (
        scope_type,
        scope.guild_id,
        scope.category_id if scope_type == "category" else "",
        scope.channel_id if scope_type in {"channel", "thread"} else "",
        scope.thread_id if scope_type == "thread" else "",
    )
    existing = existing_by_key.get(key)
    return SendPermissionRule(
        scope_type=scope_type,
        allow=existing.allow if existing is not None else False,
        guild_id=scope.guild_id,
        guild_name=scope.guild_name,
        category_id=scope.category_id if scope_type == "category" else "",
        category_name=scope.category_name if scope_type == "category" else "",
        channel_id=scope.channel_id if scope_type in {"channel", "thread"} else "",
        channel_name=scope.channel_name if scope_type in {"channel", "thread"} else "",
        thread_id=scope.thread_id if scope_type == "thread" else "",
        thread_name=scope.thread_name if scope_type == "thread" else "",
    )


def _serialize_rule(rule: SendPermissionRule) -> dict[str, Any]:
    data: dict[str, Any] = {
        "__template_key": rule.scope_type,
        "guild_id": rule.guild_id,
        "guild_name": rule.guild_name,
        "allow": rule.allow,
    }
    if rule.scope_type == "category":
        data["category_id"] = rule.category_id
        data["category_name"] = rule.category_name
    elif rule.scope_type == "channel":
        data["channel_id"] = rule.channel_id
        data["channel_name"] = rule.channel_name
    elif rule.scope_type == "thread":
        data["channel_id"] = rule.channel_id
        data["channel_name"] = rule.channel_name
        data["thread_id"] = rule.thread_id
        data["thread_name"] = rule.thread_name
    return data


def _is_message_channel(channel: Any) -> bool:
    if channel is None:
        return False
    if getattr(channel, "parent_id", None) not in (None, ""):
        return False
    return callable(getattr(channel, "send", None))


def _object_sort_key(obj: Any) -> tuple[str, str]:
    return (_display_name(obj).lower(), _snowflake_str(getattr(obj, "id", None)))


def _snowflake_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _display_name(obj: Any) -> str:
    if obj is None:
        return ""
    value = getattr(obj, "name", None)
    if value in (None, ""):
        return ""
    return str(value)


def _log_debug_or_warning(logger: Any, message: str, *args: Any) -> None:
    debug = getattr(logger, "debug", None)
    if callable(debug):
        debug(message, *args)
        return
    warning = getattr(logger, "warning", None)
    if callable(warning):
        warning(message, *args)
