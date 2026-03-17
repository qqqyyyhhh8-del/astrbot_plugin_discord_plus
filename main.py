from pathlib import Path
import sys

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse
from astrbot.api.star import Context, Star, register

from astrbot_plugin_discord_plus_core import config as discord_plus_config
from astrbot_plugin_discord_plus_core.features.discord_typing import DiscordTypingFeature
from astrbot_plugin_discord_plus_core.runtime import DiscordFeatureRuntime

try:
    from astrbot_plugin_discord_plus_core.features.discord_mention_fix import (
        DiscordMentionFixFeature,
    )
except ImportError:
    DiscordMentionFixFeature = None

try:
    from astrbot_plugin_discord_plus_core.features.discord_reply_reference import (
        DiscordReplyReferenceFeature,
    )
except ImportError:
    DiscordReplyReferenceFeature = None


@register(
    "astrbot_plugin_discord_plus",
    "Codex",
    "Discord enhancement toolkit for AstrBot. Initial feature: typing indicator.",
    "0.1.4",
    "",
)
class DiscordPlusPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self._plugin_config = config or {}
        features = []
        if DiscordReplyReferenceFeature is not None:
            features.append(
                DiscordReplyReferenceFeature(
                    logger=logger,
                    config_getter=self._reply_reference_enabled,
                )
            )
        if DiscordMentionFixFeature is not None:
            features.append(
                DiscordMentionFixFeature(
                    logger=logger,
                    config_getter=self._mention_fix_enabled,
                )
            )
        features.append(
            DiscordTypingFeature(
                logger=logger,
                config_getter=self._typing_enabled,
            )
        )
        self._features = features
        self.runtime = DiscordFeatureRuntime(
            features=features,
            logger=logger,
        )

    @filter.on_waiting_llm_request()
    async def on_waiting_llm_request(self, event: AstrMessageEvent):
        await self._dispatch_runtime_hook("on_waiting_llm_request", event)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        await self._dispatch_runtime_hook("on_llm_response", event, resp)
        return resp

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        await self._dispatch_runtime_hook("on_decorating_result", event)

    def _typing_enabled(self) -> bool:
        return discord_plus_config.get_typing_settings(self._plugin_config).enabled

    def _mention_fix_enabled(self) -> bool:
        return self._message_decoration_enabled("mention_fix_enabled")

    def _reply_reference_enabled(self) -> bool:
        return self._message_decoration_enabled("reply_reference_enabled")

    def _message_decoration_enabled(self, key: str) -> bool:
        getter = getattr(discord_plus_config, "get_message_decoration_settings", None)
        if callable(getter):
            settings = getter(self._plugin_config)
            return bool(getattr(settings, key, True))
        return _coerce_bool(_mapping_get(self._plugin_config, key, True), default=True)

    async def _dispatch_runtime_hook(self, hook_name: str, *args) -> None:
        runtime_hook = getattr(self.runtime, hook_name, None)
        if callable(runtime_hook):
            await runtime_hook(*args)
            return

        for feature in self._features:
            feature_hook = getattr(feature, hook_name, None)
            if not callable(feature_hook):
                continue
            try:
                await feature_hook(*args)
            except Exception:
                logger.exception(
                    "discord feature '%s' failed in fallback hook '%s'",
                    getattr(feature, "name", feature.__class__.__name__),
                    hook_name,
                )


def _mapping_get(obj, key: str, default):
    if obj is None:
        return default
    getter = getattr(obj, "get", None)
    if callable(getter):
        try:
            return getter(key, default)
        except TypeError:
            return getter(key)
    return default


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default
