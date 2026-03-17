import inspect
from collections import deque
from dataclasses import dataclass
from typing import Any

DISCOVERY_ATTRS = (
    "message_obj",
    "raw_message",
    "message",
    "source_message",
    "platform_message",
    "raw_event",
    "channel",
)


@dataclass(frozen=True, slots=True)
class DiscordMessageScope:
    guild_id: str = ""
    guild_name: str = ""
    category_id: str = ""
    category_name: str = ""
    channel_id: str = ""
    channel_name: str = ""
    thread_id: str = ""
    thread_name: str = ""


def build_event_key(event: Any) -> str:
    message_id = get_source_message_id(event)
    if message_id not in (None, ""):
        return f"message:{message_id}"
    return f"event:{id(event)}"


def get_source_message_id(event: Any) -> Any | None:
    message_obj = getattr(event, "message_obj", None)
    raw_message = getattr(message_obj, "raw_message", None)
    candidates = (
        getattr(message_obj, "message_id", None),
        getattr(message_obj, "msg_id", None),
        getattr(raw_message, "id", None),
        getattr(event, "message_id", None),
    )
    for value in candidates:
        if value not in (None, ""):
            return value
    return None


def get_raw_discord_message(event: Any) -> Any | None:
    message_obj = getattr(event, "message_obj", None)
    raw_message = getattr(message_obj, "raw_message", None)
    if _is_discord_message(raw_message):
        return raw_message
    return None


def get_discord_scope(event: Any) -> DiscordMessageScope | None:
    raw_message = get_raw_discord_message(event)
    if raw_message is None:
        return None
    return _build_scope_from_message(raw_message)


def get_discord_client(event: Any) -> Any | None:
    raw_message = get_raw_discord_message(event)
    if raw_message is None:
        return None

    state = getattr(raw_message, "_state", None)
    getter = getattr(state, "_get_client", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None

    for attr in ("client", "_client"):
        client = getattr(state, attr, None)
        if client is not None:
            return client
    return None


def is_discord_event(event: Any) -> bool:
    message_obj = getattr(event, "message_obj", None)
    raw_message = getattr(message_obj, "raw_message", None)
    if _is_discord_object(raw_message):
        return True

    channel = getattr(raw_message, "channel", None)
    if _is_discord_object(channel):
        return True

    return find_discord_channel(event) is not None


def find_discord_channel(event: Any) -> Any | None:
    queue = deque((root, 0) for root in _seed_objects(event))
    visited = set()

    while queue:
        obj, depth = queue.popleft()
        if obj is None:
            continue

        marker = id(obj)
        if marker in visited:
            continue
        visited.add(marker)

        if _is_discord_channel(obj):
            return obj

        channel = getattr(obj, "channel", None)
        if _is_discord_channel(channel):
            return channel

        if depth >= 4:
            continue

        for attr in DISCOVERY_ATTRS:
            child = getattr(obj, attr, None)
            if child is not None:
                queue.append((child, depth + 1))

    return None


async def trigger_typing(channel: Any) -> bool:
    if channel is None:
        return False

    if hasattr(channel, "trigger_typing"):
        result = channel.trigger_typing()
        if inspect.isawaitable(result):
            await result
        return True

    typing_factory = getattr(channel, "typing", None)
    if typing_factory is None:
        return False

    typing_ctx = typing_factory()
    enter = getattr(typing_ctx, "__aenter__", None)
    exit_ = getattr(typing_ctx, "__aexit__", None)
    if callable(enter) and callable(exit_):
        await enter()
        await exit_(None, None, None)
        return True

    if inspect.isawaitable(typing_ctx):
        await typing_ctx
        return True

    return False


def _seed_objects(event: Any) -> list[Any]:
    seeds = [event]
    for attr in DISCOVERY_ATTRS:
        child = getattr(event, attr, None)
        if child is not None:
            seeds.append(child)
    message_obj = getattr(event, "message_obj", None)
    if message_obj is not None:
        raw_message = getattr(message_obj, "raw_message", None)
        if raw_message is not None:
            seeds.append(raw_message)
    return seeds


def _build_scope_from_message(raw_message: Any) -> DiscordMessageScope | None:
    guild = getattr(raw_message, "guild", None)
    channel = getattr(raw_message, "channel", None)
    if guild is None or channel is None:
        return None

    guild_id = _snowflake_str(getattr(guild, "id", None))
    if not guild_id:
        return None

    guild_name = _display_name(guild)
    category = getattr(channel, "category", None)
    category_id = _snowflake_str(getattr(channel, "category_id", None)) or _snowflake_str(
        getattr(category, "id", None)
    )
    category_name = _display_name(category)

    parent = getattr(channel, "parent", None)
    parent_id = _snowflake_str(getattr(channel, "parent_id", None)) or _snowflake_str(
        getattr(parent, "id", None)
    )
    parent_name = _display_name(parent)

    is_thread = bool(parent_id)
    if is_thread:
        channel_id = parent_id
        channel_name = parent_name
        thread_id = _snowflake_str(getattr(channel, "id", None))
        thread_name = _display_name(channel)
    else:
        channel_id = _snowflake_str(getattr(channel, "id", None))
        channel_name = _display_name(channel)
        thread_id = ""
        thread_name = ""

    return DiscordMessageScope(
        guild_id=guild_id,
        guild_name=guild_name,
        category_id=category_id,
        category_name=category_name,
        channel_id=channel_id,
        channel_name=channel_name,
        thread_id=thread_id,
        thread_name=thread_name,
    )


def _is_discord_channel(obj: Any) -> bool:
    if obj is None:
        return False
    return _is_discord_object(obj) and (hasattr(obj, "trigger_typing") or hasattr(obj, "typing"))


def _is_discord_object(obj: Any) -> bool:
    if obj is None:
        return False
    module_name = type(obj).__module__.lower()
    return "discord" in module_name


def _is_discord_message(obj: Any) -> bool:
    if obj is None:
        return False
    return _is_discord_object(obj) and hasattr(obj, "channel") and hasattr(obj, "author")


def _snowflake_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _display_name(obj: Any) -> str:
    if obj is None:
        return ""
    for attr in ("name",):
        value = getattr(obj, attr, None)
        if value not in (None, ""):
            return str(value)
    return ""
