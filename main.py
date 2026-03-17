from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register

from astrbot_plugin_discord_plus_core.config import (
    get_message_decoration_settings,
    get_typing_settings,
)
from astrbot_plugin_discord_plus_core.features.discord_mention_fix import (
    DiscordMentionFixFeature,
)
from astrbot_plugin_discord_plus_core.features.discord_reply_reference import (
    DiscordReplyReferenceFeature,
)
from astrbot_plugin_discord_plus_core.features.discord_typing import DiscordTypingFeature
from astrbot_plugin_discord_plus_core.runtime import DiscordFeatureRuntime


@register(
    "astrbot_plugin_discord_plus",
    "Codex",
    "Discord enhancement toolkit for AstrBot. Initial feature: typing indicator.",
    "0.1.0",
    "",
)
class DiscordPlusPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self._plugin_config = config or {}
        self.runtime = DiscordFeatureRuntime(
            features=[
                DiscordReplyReferenceFeature(
                    logger=logger,
                    config_getter=self._reply_reference_enabled,
                ),
                DiscordMentionFixFeature(
                    logger=logger,
                    config_getter=self._mention_fix_enabled,
                ),
                DiscordTypingFeature(
                    logger=logger,
                    config_getter=self._typing_enabled,
                )
            ],
            logger=logger,
        )

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent):
        await self.runtime.on_waiting_llm_request(event)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        await self.runtime.on_llm_response(event, resp)
        return resp

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        await self.runtime.on_decorating_result(event)

    def _typing_enabled(self) -> bool:
        return get_typing_settings(self._plugin_config).enabled

    def _mention_fix_enabled(self) -> bool:
        return get_message_decoration_settings(self._plugin_config).mention_fix_enabled

    def _reply_reference_enabled(self) -> bool:
        return get_message_decoration_settings(self._plugin_config).reply_reference_enabled
