import inspect
from collections import deque
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


def build_event_key(event: Any) -> str:
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
            return f"message:{value}"
    return f"event:{id(event)}"


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


def _is_discord_channel(obj: Any) -> bool:
    if obj is None:
        return False
    module_name = type(obj).__module__.lower()
    if "discord" not in module_name:
        return False
    return hasattr(obj, "trigger_typing") or hasattr(obj, "typing")
