from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register

from discord_toolkit.features.discord_typing import DiscordTypingFeature
from discord_toolkit.runtime import DiscordFeatureRuntime


@register(
    "astrbot_plugin_discord_plus",
    "Codex",
    "Discord enhancement toolkit for AstrBot. Initial feature: typing indicator.",
    "0.1.0",
    "",
)
class DiscordPlusPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.runtime = DiscordFeatureRuntime(
            features=[DiscordTypingFeature(logger=logger)],
            logger=logger,
        )

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent):
        await self.runtime.on_waiting_llm_request(event)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        await self.runtime.on_llm_response(event, resp)
        return resp
