from collections.abc import Callable
from typing import Any

from astrbot_plugin_discord_plus_core.discord_bridge import (
    get_source_message_id,
    is_discord_event,
)
from astrbot_plugin_discord_plus_core.feature_base import FeatureBase
from astrbot_plugin_discord_plus_core.message_chain import (
    build_reply_component,
    component_name,
    get_chain_items,
    set_chain_items,
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
        if items is None:
            return

        if any(component_name(item) == "Reply" for item in items):
            return

        message_id = get_source_message_id(event)
        if message_id in (None, ""):
            return

        reply_component = build_reply_component(message_id)
        if reply_component is None:
            self._logger.warning("failed to build Reply component for Discord reply reference")
            return

        set_chain_items(event, [reply_component, *items])
