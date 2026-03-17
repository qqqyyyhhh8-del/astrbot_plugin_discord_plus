from collections.abc import Callable
from typing import Any

from astrbot_plugin_discord_plus_core.discord_bridge import is_discord_event
from astrbot_plugin_discord_plus_core.feature_base import FeatureBase
from astrbot_plugin_discord_plus_core.message_chain import (
    build_plain_component,
    component_name,
    get_chain_items,
    set_chain_items,
)


class DiscordMentionFixFeature(FeatureBase):
    name = "discord_mention_fix"

    def __init__(self, logger: Any, config_getter: Callable[[], bool]):
        self._logger = logger
        self._config_getter = config_getter

    async def on_decorating_result(self, event: Any) -> None:
        if not self._config_getter() or not is_discord_event(event):
            return

        items = get_chain_items(event)
        if not items:
            return

        changed = False
        updated_items: list[Any] = []
        for item in items:
            if component_name(item) != "At":
                updated_items.append(item)
                continue

            mention_text = _format_mention(_extract_target(item))
            if mention_text is None:
                updated_items.append(item)
                continue

            plain_component = build_plain_component(mention_text)
            if plain_component is None:
                self._logger.warning("failed to build Plain component for Discord mention fix")
                updated_items.append(item)
                continue

            updated_items.append(plain_component)
            changed = True

        if changed:
            set_chain_items(event, updated_items)


def _extract_target(component: Any) -> Any | None:
    for attr in ("qq", "id", "target", "uid", "user_id"):
        value = getattr(component, attr, None)
        if value not in (None, ""):
            return value
    return None


def _format_mention(target: Any) -> str | None:
    if target in (None, ""):
        return None

    text = str(target).strip()
    if not text:
        return None
    if text.startswith("<@") and text.endswith(">"):
        return text
    if text.lower() in {"all", "@all", "everyone", "@everyone"}:
        return "@everyone"
    if text.lower() in {"here", "@here"}:
        return "@here"
    return f"<@{text}>"
