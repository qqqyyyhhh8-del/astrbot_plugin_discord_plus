from pathlib import Path
import sys
from types import SimpleNamespace

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

try:
    from astrbot_plugin_discord_plus_core.features.discord_send_permission import (
        DiscordSendPermissionFeature,
        describe_scope,
        serialize_send_permission_rules,
    )
except ImportError:
    DiscordSendPermissionFeature = None
    describe_scope = None
    serialize_send_permission_rules = None


@register(
    "astrbot_plugin_discord_plus",
    "Codex",
    "Discord enhancement toolkit for AstrBot. Initial feature: typing indicator.",
    "0.1.5",
    "",
)
class DiscordPlusPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self._plugin_config = config or {}
        features = []
        self._send_permission_feature = None
        if DiscordSendPermissionFeature is not None:
            self._send_permission_feature = DiscordSendPermissionFeature(
                logger=logger,
                config_getter=self._send_permission_settings,
            )
            features.append(self._send_permission_feature)
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

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("discord_send_rules_refresh")
    async def discord_send_rules_refresh(self, event: AstrMessageEvent):
        if self._send_permission_feature is None:
            yield event.plain_result("当前插件版本尚未加载发言权限覆盖功能。")
            return

        refresh_result = self._send_permission_feature.refresh_rules_from_event(event)
        if refresh_result is None:
            yield event.plain_result("未能从当前事件获取 Discord 客户端。请在 Discord 内由管理员执行此命令。")
            return

        self._set_plugin_config_value(
            "send_permission_rules",
            serialize_send_permission_rules(refresh_result.rules),
        )
        self._save_plugin_config()
        yield event.plain_result(
            "\n".join(
                (
                    "已自动填充 Discord 发言权限规则。",
                    f"服务器: {refresh_result.guild_count}",
                    f"分类: {refresh_result.category_count}",
                    f"频道: {refresh_result.channel_count}",
                    f"线程: {refresh_result.thread_count}",
                    f"总规则数: {refresh_result.total_rules}",
                    "所有新填充规则默认 allow=false，请到插件配置中批量改成需要放行的项。",
                )
            )
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("discord_send_scope_here")
    async def discord_send_scope_here(self, event: AstrMessageEvent):
        if self._send_permission_feature is None:
            yield event.plain_result("当前插件版本尚未加载发言权限覆盖功能。")
            return

        inspection = self._send_permission_feature.inspect_event(event)
        if inspection is None:
            yield event.plain_result("当前事件不在 Discord 服务器上下文中，无法读取服务器/频道/线程范围。")
            return

        scope, allowed = inspection
        status = "允许发言" if allowed else "禁止发言"
        yield event.plain_result(f"{describe_scope(scope)}\n当前判定: {status}")

    def _typing_enabled(self) -> bool:
        return discord_plus_config.get_typing_settings(self._plugin_config).enabled

    def _mention_fix_enabled(self) -> bool:
        return self._message_decoration_enabled("mention_fix_enabled")

    def _reply_reference_enabled(self) -> bool:
        return self._message_decoration_enabled("reply_reference_enabled")

    def _send_permission_settings(self):
        getter = getattr(discord_plus_config, "get_send_permission_settings", None)
        if callable(getter):
            return getter(self._plugin_config)
        return SimpleNamespace(
            enabled=_coerce_bool(
                _mapping_get(self._plugin_config, "send_permission_override_enabled", True),
                default=True,
            ),
            rules=(),
        )

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
            event = args[0] if args else None
            if _event_stopped(event):
                break

    def _set_plugin_config_value(self, key: str, value) -> None:
        if isinstance(self._plugin_config, dict):
            self._plugin_config[key] = value
            return

        setter = getattr(self._plugin_config, "__setitem__", None)
        if callable(setter):
            setter(key, value)
            return

        update = getattr(self._plugin_config, "update", None)
        if callable(update):
            update({key: value})
            return

        setattr(self._plugin_config, key, value)

    def _save_plugin_config(self) -> None:
        saver = getattr(self._plugin_config, "save_config", None)
        if callable(saver):
            saver()


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


def _event_stopped(event) -> bool:
    checker = getattr(event, "is_stopped", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


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
