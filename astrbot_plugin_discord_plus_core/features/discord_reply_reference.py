from collections.abc import Callable
from typing import Any

from astrbot_plugin_discord_plus_core.discord_bridge import find_discord_channel, is_discord_event
from astrbot_plugin_discord_plus_core.feature_base import FeatureBase
from astrbot_plugin_discord_plus_core.message_chain import (
    component_name,
    get_chain_items,
)


class DiscordReplyReferenceFeature(FeatureBase):
    name = "discord_reply_reference"

    def __init__(self, logger: Any, config_getter: Callable[[], bool]):
        self._logger = logger
        self._config_getter = config_getter

    async def on_decorating_result(self, event: Any) -> None:
        if not self._config_getter() or not is_discord_event(event):
            return

        items = get_chain_items(event)
        if not items:
            return

        raw_message = _get_raw_discord_message(event)
        if raw_message is None:
            return

        content = _render_chain_as_discord_text(items)
        if content is None:
            return

        try:
            sent = await _send_native_reply(event, raw_message, content)
        except Exception:
            self._logger.exception("failed to send native Discord reply")
            return

        if sent:
            stopper = getattr(event, "stop_event", None)
            if callable(stopper):
                stopper()


def _get_raw_discord_message(event: Any) -> Any | None:
    message_obj = getattr(event, "message_obj", None)
    raw_message = getattr(message_obj, "raw_message", None)
    if _is_discord_message(raw_message):
        return raw_message
    return None


def _is_discord_message(obj: Any) -> bool:
    if obj is None:
        return False
    module_name = type(obj).__module__.lower()
    return "discord" in module_name and hasattr(obj, "channel")


async def _send_native_reply(event: Any, raw_message: Any, content: str) -> bool:
    send_kwargs = {
        "content": content,
        "mention_author": False,
    }

    reply = getattr(raw_message, "reply", None)
    if callable(reply):
        try:
            await reply(**send_kwargs)
            return True
        except TypeError:
            await reply(content)
            return True

    channel = getattr(raw_message, "channel", None) or find_discord_channel(event)
    send = getattr(channel, "send", None)
    if not callable(send):
        return False

    try:
        await send(reference=raw_message, **send_kwargs)
        return True
    except TypeError:
        await send(content=content, reference=raw_message)
        return True


def _render_chain_as_discord_text(items: list[Any]) -> str | None:
    parts: list[str] = []
    for item in items:
        rendered = _render_component_as_text(item)
        if rendered is None:
            return None
        if rendered:
            parts.append(rendered)

    if not parts:
        return None

    content = "".join(parts).strip()
    return content or None


def _render_component_as_text(component: Any) -> str | None:
    name = component_name(component)
    if name == "Reply":
        return ""
    if name == "Plain":
        return _coerce_text(
            getattr(component, "text", None),
            getattr(component, "plain", None),
            getattr(component, "content", None),
        )
    if name == "At":
        target = _coerce_text(
            getattr(component, "qq", None),
            getattr(component, "id", None),
            getattr(component, "target", None),
            getattr(component, "uid", None),
            getattr(component, "user_id", None),
        )
        if not target:
            return None
        lowered = target.lower()
        if lowered in {"all", "@all", "everyone", "@everyone"}:
            return "@everyone"
        if lowered in {"here", "@here"}:
            return "@here"
        if target.startswith("<@") and target.endswith(">"):
            return target
        return f"<@{target}>"
    if name in {"Image", "Record", "Video", "File"}:
        media_url = _coerce_text(
            getattr(component, "url", None),
            getattr(component, "file", None),
            getattr(component, "path", None),
        )
        if not media_url:
            return None
        if not media_url.startswith(("http://", "https://")):
            return None
        return _ensure_prefixed_break(media_url)
    if name == "Share":
        title = _coerce_text(getattr(component, "title", None))
        url = _coerce_text(getattr(component, "url", None))
        if not title and not url:
            return None
        if title and url:
            return _ensure_prefixed_break(f"{title}\n{url}")
        return _ensure_prefixed_break(title or url)
    return None


def _coerce_text(*values: Any) -> str | None:
    for value in values:
        if value in (None, ""):
            continue
        text = str(value)
        if text:
            return text
    return None


def _ensure_prefixed_break(text: str) -> str:
    if not text:
        return ""
    return text if text.startswith(("\n", "\r")) else f"\n{text}"
