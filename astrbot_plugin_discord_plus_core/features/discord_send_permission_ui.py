import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

try:
    import discord
except ImportError:  # pragma: no cover - host environment decides availability
    discord = None

from astrbot_plugin_discord_plus_core.config import SendPermissionRule, SendPermissionSettings
from astrbot_plugin_discord_plus_core.feature_base import FeatureBase
from astrbot_plugin_discord_plus_core.features.discord_send_permission import (
    build_refresh_result,
    get_send_permission_rule_key,
    serialize_send_permission_rules,
)

COMMAND_NAME = "discord_send_panel"
COMMAND_DESCRIPTION = "打开 Discord 发言权限管理面板"
GUILD_PAGE_SIZE = 25
RULE_PAGE_SIZE = 20
SCOPE_TYPES = ("guild", "category", "channel", "thread")
SCOPE_TYPE_LABELS = {
    "guild": "服务器",
    "category": "分类",
    "channel": "频道",
    "thread": "线程",
}
CLIENT_DISCOVERY_ATTRS = (
    "platform_manager",
    "platform_insts",
    "platforms",
    "instances",
    "client",
    "bot",
    "_client",
    "discord_client",
    "adapter",
    "platform",
    "runner",
)


@dataclass(frozen=True, slots=True)
class GuildOption:
    guild_id: str
    guild_name: str


class DiscordSendPermissionUIFeature(FeatureBase):
    name = "discord_send_permission_ui"

    def __init__(
        self,
        logger: Any,
        settings_getter: Callable[[], SendPermissionSettings],
        config_setter: Callable[[str, Any], None],
        config_saver: Callable[[], None],
    ):
        self._logger = logger
        self._settings_getter = settings_getter
        self._config_setter = config_setter
        self._config_saver = config_saver
        self._register_task: asyncio.Task[Any] | None = None
        self._registered_guild_sets: dict[int, tuple[int, ...]] = {}

    async def register_startup(self, context: Any) -> None:
        if discord is None:
            self._log_warning("discord.py is unavailable; native send-permission panel disabled")
            return

        if self._register_task is not None and not self._register_task.done():
            return

        self._register_task = asyncio.create_task(self._register_loop(context))

    async def shutdown(self) -> None:
        if self._register_task is None:
            return
        if self._register_task.done():
            return
        self._register_task.cancel()
        try:
            await self._register_task
        except asyncio.CancelledError:
            return

    def get_settings(self) -> SendPermissionSettings:
        return self._settings_getter()

    def set_override_enabled(self, enabled: bool) -> None:
        self._config_setter("send_permission_override_enabled", enabled)
        self._config_saver()

    def replace_rules(self, rules: list[SendPermissionRule] | tuple[SendPermissionRule, ...]) -> None:
        self._config_setter("send_permission_rules", serialize_send_permission_rules(rules))
        self._config_saver()

    def refresh_rules(self, client: Any):
        refresh_result = build_refresh_result(client, self.get_settings().rules)
        self.replace_rules(list(refresh_result.rules))
        return refresh_result

    def set_rule_allow(self, encoded_keys: set[str], allow: bool) -> int:
        if not encoded_keys:
            return 0

        rules = list(self.get_settings().rules)
        changed = 0
        for index, rule in enumerate(rules):
            if _encode_rule_key(rule) not in encoded_keys:
                continue
            if rule.allow == allow:
                continue
            rules[index] = replace(rule, allow=allow)
            changed += 1

        if changed:
            self.replace_rules(rules)
        return changed

    async def open_panel(self, interaction: Any, client: Any) -> None:
        refresh_result = self.refresh_rules(client)
        current_guild_id = _snowflake_str(getattr(getattr(interaction, "guild", None), "id", None))
        view = DiscordSendPermissionPanelView(
            feature=self,
            client=client,
            operator_id=getattr(getattr(interaction, "user", None), "id", 0),
            current_guild_id=current_guild_id,
            refresh_result=refresh_result,
        )
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )

    async def _register_loop(self, context: Any) -> None:
        for attempt in range(1, 25):
            clients = _discover_discord_clients(context)
            if not clients:
                if attempt in {1, 6, 12, 24}:
                    self._log_warning(
                        "discord send-permission panel registration retrying; no Discord client found yet (attempt %s)",
                        attempt,
                    )
                await asyncio.sleep(5)
                continue

            pending_client = False
            for client in clients:
                registered = await self._register_client(client)
                if not registered:
                    pending_client = True

            if not pending_client:
                return
            await asyncio.sleep(5)

        self._log_warning("discord send-permission panel registration timed out after startup")

    async def _register_client(self, client: Any) -> bool:
        tree = getattr(client, "tree", None)
        if tree is None or not callable(getattr(tree, "add_command", None)):
            return True

        is_ready = getattr(client, "is_ready", None)
        if callable(is_ready):
            try:
                if not bool(is_ready()):
                    return False
            except Exception:
                return False

        guild_ids = tuple(
            sorted(
                int(guild_id)
                for guild_id in (
                    getattr(guild, "id", None) for guild in getattr(client, "guilds", [])
                )
                if guild_id not in (None, "")
            )
        )
        if not guild_ids:
            return False

        client_token = id(client)
        if self._registered_guild_sets.get(client_token) == guild_ids:
            return True

        try:
            tree.add_command(
                self._build_command(list(guild_ids)),
                override=True,
            )
            for guild_id in guild_ids:
                await tree.sync(guild=discord.Object(id=guild_id))
        except Exception:
            self._logger.exception("failed to register discord send-permission panel command")
            return False

        self._registered_guild_sets[client_token] = guild_ids
        self._log_info(
            "registered discord send-permission panel command for %s guild(s)",
            len(guild_ids),
        )
        return True

    def _build_command(self, guild_ids: list[int]):
        async def callback(interaction: Any) -> None:
            if getattr(interaction, "guild", None) is None:
                await interaction.response.send_message(
                    "这个面板只能在 Discord 服务器内使用。",
                    ephemeral=True,
                )
                return

            if not _is_admin_interaction(interaction):
                await interaction.response.send_message(
                    "只有 Discord 服务器管理员可以打开这个面板。",
                    ephemeral=True,
                )
                return

            client = getattr(interaction, "client", None)
            if client is None:
                await interaction.response.send_message(
                    "未能获取 Discord 客户端，暂时无法打开面板。",
                    ephemeral=True,
                )
                return

            await self.open_panel(interaction, client)

        callback = discord.app_commands.guild_only()(callback)
        callback = discord.app_commands.default_permissions(administrator=True)(callback)
        return discord.app_commands.Command(
            name=COMMAND_NAME,
            description=COMMAND_DESCRIPTION,
            callback=callback,
            guild_ids=guild_ids,
        )

    def _log_info(self, message: str, *args: Any) -> None:
        info = getattr(self._logger, "info", None)
        if callable(info):
            info(message, *args)

    def _log_warning(self, message: str, *args: Any) -> None:
        warning = getattr(self._logger, "warning", None)
        if callable(warning):
            warning(message, *args)


if discord is not None:

    class DiscordSendPermissionPanelView(discord.ui.View):
        def __init__(
            self,
            feature: DiscordSendPermissionUIFeature,
            client: Any,
            operator_id: int,
            current_guild_id: str,
            refresh_result: Any,
        ):
            super().__init__(timeout=900)
            self._feature = feature
            self._client = client
            self._operator_id = operator_id
            self._guild_page = 0
            self._rule_page = 0
            self._scope_type = "guild"
            self._selected_rule_keys: set[str] = set()
            self._refresh_result = refresh_result
            self._status_message = "面板打开时已自动扫描当前可见 Discord 范围，新项默认禁止发言。"

            guilds = self._guilds()
            guild_ids = {item.guild_id for item in guilds}
            self._current_guild_id = current_guild_id if current_guild_id in guild_ids else ""
            if not self._current_guild_id and guilds:
                self._current_guild_id = guilds[0].guild_id
            self._guild_page = self._guild_page_for_guild(self._current_guild_id)
            self._rebuild_items()

        async def interaction_check(self, interaction: Any) -> bool:
            if getattr(getattr(interaction, "user", None), "id", 0) == self._operator_id:
                return True
            await interaction.response.send_message(
                "这个面板只允许最初打开它的管理员操作。",
                ephemeral=True,
            )
            return False

        def build_embed(self):
            settings = self._feature.get_settings()
            guilds = self._guilds()
            current_guild = self._current_guild()
            scoped_rules = self._scoped_rules()
            page_rules = self._page_rules()
            allow_count = sum(1 for rule in scoped_rules if rule.allow)
            page_count = max(1, _page_count(len(scoped_rules), RULE_PAGE_SIZE))
            guild_page_count = max(1, _page_count(len(guilds), GUILD_PAGE_SIZE))
            title_name = current_guild.guild_name if current_guild is not None else "暂无可用服务器"

            embed = discord.Embed(
                title=f"Discord 发言权限面板 | {title_name}",
                description="\n".join(
                    (
                        f"覆盖开关: {'开启' if settings.enabled else '关闭'}",
                        f"当前范围: {SCOPE_TYPE_LABELS[self._scope_type]}",
                        f"服务器页码: {self._guild_page + 1}/{guild_page_count}",
                        f"条目页码: {self._rule_page + 1}/{page_count}",
                        "说明: 按钮操作会立即写回插件配置；全选和反选只作用于当前页。",
                    )
                ),
                color=0x3BA55D if settings.enabled else 0xED4245,
            )
            if current_guild is not None:
                embed.add_field(
                    name="当前服务器",
                    value=f"{current_guild.guild_name}\nID: {current_guild.guild_id}",
                    inline=False,
                )
            embed.add_field(
                name="当前范围统计",
                value="\n".join(
                    (
                        f"总条目: {len(scoped_rules)}",
                        f"允许发言: {allow_count}",
                        f"当前选中: {len(self._selected_rule_keys)}",
                    )
                ),
                inline=True,
            )
            if self._refresh_result is not None:
                embed.add_field(
                    name="最近扫描",
                    value="\n".join(
                        (
                            f"服务器: {self._refresh_result.guild_count}",
                            f"分类: {self._refresh_result.category_count}",
                            f"频道: {self._refresh_result.channel_count}",
                            f"线程: {self._refresh_result.thread_count}",
                        )
                    ),
                    inline=True,
                )
            embed.add_field(
                name="最近操作",
                value=self._status_message,
                inline=False,
            )
            embed.add_field(
                name="当前页条目",
                value=_render_rule_page(page_rules),
                inline=False,
            )
            embed.set_footer(text=f"命令名: /{COMMAND_NAME} | 仅自己可见")
            return embed

        def _rebuild_items(self) -> None:
            self.clear_items()
            self.add_item(_GuildSelect(self))
            self.add_item(_ScopeTypeSelect(self))
            self.add_item(_RuleSelect(self))

            self.add_item(
                _build_button(
                    label="服务器上一页",
                    row=3,
                    disabled=self._guild_page <= 0,
                    callback=self._on_prev_guild_page,
                )
            )
            self.add_item(
                _build_button(
                    label="服务器下一页",
                    row=3,
                    disabled=self._guild_page >= self._max_guild_page(),
                    callback=self._on_next_guild_page,
                )
            )
            self.add_item(
                _build_button(
                    label="条目上一页",
                    row=3,
                    disabled=self._rule_page <= 0,
                    callback=self._on_prev_rule_page,
                )
            )
            self.add_item(
                _build_button(
                    label="条目下一页",
                    row=3,
                    disabled=self._rule_page >= self._max_rule_page(),
                    callback=self._on_next_rule_page,
                )
            )
            self.add_item(
                _build_button(
                    label=f"覆盖:{'开' if self._feature.get_settings().enabled else '关'}",
                    row=3,
                    style=discord.ButtonStyle.success
                    if self._feature.get_settings().enabled
                    else discord.ButtonStyle.danger,
                    callback=self._on_toggle_override,
                )
            )

            page_rules = self._page_rules()
            has_rules = bool(page_rules)
            has_selected = bool(self._selected_rule_keys)
            self.add_item(
                _build_button(
                    label="全选本页",
                    row=4,
                    disabled=not has_rules,
                    callback=self._on_select_all_page,
                )
            )
            self.add_item(
                _build_button(
                    label="反选本页",
                    row=4,
                    disabled=not has_rules,
                    callback=self._on_invert_page,
                )
            )
            self.add_item(
                _build_button(
                    label="允许选中",
                    row=4,
                    style=discord.ButtonStyle.success,
                    disabled=not has_selected,
                    callback=self._on_allow_selected,
                )
            )
            self.add_item(
                _build_button(
                    label="禁止选中",
                    row=4,
                    style=discord.ButtonStyle.danger,
                    disabled=not has_selected,
                    callback=self._on_deny_selected,
                )
            )
            self.add_item(
                _build_button(
                    label="自动填充刷新",
                    row=4,
                    style=discord.ButtonStyle.primary,
                    callback=self._on_refresh_rules,
                )
            )

        def _guilds(self) -> list[GuildOption]:
            guilds = [
                GuildOption(
                    guild_id=_snowflake_str(getattr(guild, "id", None)),
                    guild_name=_safe_text(getattr(guild, "name", None), "未命名服务器"),
                )
                for guild in getattr(self._client, "guilds", [])
                if getattr(guild, "id", None) not in (None, "")
            ]
            guilds.sort(key=lambda item: (item.guild_name.lower(), item.guild_id))
            return guilds

        def _current_guild(self) -> GuildOption | None:
            for guild in self._guilds():
                if guild.guild_id == self._current_guild_id:
                    return guild
            return None

        def _guild_page_for_guild(self, guild_id: str) -> int:
            if not guild_id:
                return 0
            guilds = self._guilds()
            for index, guild in enumerate(guilds):
                if guild.guild_id == guild_id:
                    return index // GUILD_PAGE_SIZE
            return 0

        def _guild_page_items(self) -> list[GuildOption]:
            guilds = self._guilds()
            start = self._guild_page * GUILD_PAGE_SIZE
            end = start + GUILD_PAGE_SIZE
            return guilds[start:end]

        def _scoped_rules(self) -> list[SendPermissionRule]:
            rules = [
                rule
                for rule in self._feature.get_settings().rules
                if rule.scope_type == self._scope_type
                and (not self._current_guild_id or rule.guild_id == self._current_guild_id)
            ]
            rules.sort(key=_rule_sort_key)
            return rules

        def _page_rules(self) -> list[SendPermissionRule]:
            rules = self._scoped_rules()
            max_page = self._max_rule_page()
            if self._rule_page > max_page:
                self._rule_page = max_page
            start = self._rule_page * RULE_PAGE_SIZE
            end = start + RULE_PAGE_SIZE
            return rules[start:end]

        def _max_guild_page(self) -> int:
            return max(0, _page_count(len(self._guilds()), GUILD_PAGE_SIZE) - 1)

        def _max_rule_page(self) -> int:
            return max(0, _page_count(len(self._scoped_rules()), RULE_PAGE_SIZE) - 1)

        async def _refresh_message(self, interaction: Any) -> None:
            self._rebuild_items()
            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self,
            )

        async def _on_prev_guild_page(self, interaction: Any) -> None:
            self._guild_page = max(0, self._guild_page - 1)
            guilds = self._guild_page_items()
            if guilds:
                self._current_guild_id = guilds[0].guild_id
            self._rule_page = 0
            self._selected_rule_keys.clear()
            self._status_message = "已切换到上一组服务器。"
            await self._refresh_message(interaction)

        async def _on_next_guild_page(self, interaction: Any) -> None:
            self._guild_page = min(self._max_guild_page(), self._guild_page + 1)
            guilds = self._guild_page_items()
            if guilds:
                self._current_guild_id = guilds[0].guild_id
            self._rule_page = 0
            self._selected_rule_keys.clear()
            self._status_message = "已切换到下一组服务器。"
            await self._refresh_message(interaction)

        async def _on_prev_rule_page(self, interaction: Any) -> None:
            self._rule_page = max(0, self._rule_page - 1)
            self._status_message = "已切换到上一页条目。"
            await self._refresh_message(interaction)

        async def _on_next_rule_page(self, interaction: Any) -> None:
            self._rule_page = min(self._max_rule_page(), self._rule_page + 1)
            self._status_message = "已切换到下一页条目。"
            await self._refresh_message(interaction)

        async def _on_toggle_override(self, interaction: Any) -> None:
            current = self._feature.get_settings().enabled
            self._feature.set_override_enabled(not current)
            self._status_message = (
                "已开启 Discord 发言权限覆盖，规则会优先于系统放行设置。"
                if not current
                else "已关闭 Discord 发言权限覆盖，恢复由系统设置决定。"
            )
            await self._refresh_message(interaction)

        async def _on_select_all_page(self, interaction: Any) -> None:
            page_keys = {_encode_rule_key(rule) for rule in self._page_rules()}
            self._selected_rule_keys.update(page_keys)
            self._status_message = f"已全选当前页 {len(page_keys)} 项。"
            await self._refresh_message(interaction)

        async def _on_invert_page(self, interaction: Any) -> None:
            page_keys = {_encode_rule_key(rule) for rule in self._page_rules()}
            for key in page_keys:
                if key in self._selected_rule_keys:
                    self._selected_rule_keys.remove(key)
                else:
                    self._selected_rule_keys.add(key)
            self._status_message = f"已对当前页 {len(page_keys)} 项执行反选。"
            await self._refresh_message(interaction)

        async def _on_allow_selected(self, interaction: Any) -> None:
            changed = self._feature.set_rule_allow(self._selected_rule_keys, True)
            self._status_message = f"已将 {changed} 项设置为允许发言。"
            self._selected_rule_keys.clear()
            await self._refresh_message(interaction)

        async def _on_deny_selected(self, interaction: Any) -> None:
            changed = self._feature.set_rule_allow(self._selected_rule_keys, False)
            self._status_message = f"已将 {changed} 项设置为禁止发言。"
            self._selected_rule_keys.clear()
            await self._refresh_message(interaction)

        async def _on_refresh_rules(self, interaction: Any) -> None:
            self._refresh_result = self._feature.refresh_rules(self._client)
            self._selected_rule_keys.clear()
            self._rule_page = 0
            self._status_message = "已重新扫描 Discord 服务器、分类、频道和线程，并写回配置。"
            if self._current_guild() is None:
                guilds = self._guilds()
                self._current_guild_id = guilds[0].guild_id if guilds else ""
            self._guild_page = self._guild_page_for_guild(self._current_guild_id)
            await self._refresh_message(interaction)


    class _GuildSelect(discord.ui.Select):
        def __init__(self, view: DiscordSendPermissionPanelView):
            options = [
                discord.SelectOption(
                    label=_truncate_text(item.guild_name, 100),
                    value=item.guild_id,
                    description=_truncate_text(f"服务器 ID: {item.guild_id}", 100),
                    default=item.guild_id == view._current_guild_id,
                )
                for item in view._guild_page_items()
            ]
            if not options:
                options = [
                    discord.SelectOption(
                        label="暂无可用服务器",
                        value="__empty__",
                        default=True,
                    )
                ]
            super().__init__(
                placeholder="选择要管理的 Discord 服务器",
                min_values=1,
                max_values=1,
                options=options,
                disabled=not view._guild_page_items(),
                row=0,
            )
            self._panel_view = view

        async def callback(self, interaction: Any) -> None:
            selected = self.values[0]
            if selected == "__empty__":
                await interaction.response.defer()
                return
            self._panel_view._current_guild_id = selected
            self._panel_view._guild_page = self._panel_view._guild_page_for_guild(selected)
            self._panel_view._rule_page = 0
            self._panel_view._selected_rule_keys.clear()
            self._panel_view._status_message = "已切换服务器。"
            await self._panel_view._refresh_message(interaction)


    class _ScopeTypeSelect(discord.ui.Select):
        def __init__(self, view: DiscordSendPermissionPanelView):
            options = [
                discord.SelectOption(
                    label=label,
                    value=scope_type,
                    default=scope_type == view._scope_type,
                    description=_truncate_text(f"按{label}粒度调整是否允许发言", 100),
                )
                for scope_type, label in SCOPE_TYPE_LABELS.items()
            ]
            super().__init__(
                placeholder="选择当前要调整的规则范围",
                min_values=1,
                max_values=1,
                options=options,
                row=1,
            )
            self._panel_view = view

        async def callback(self, interaction: Any) -> None:
            self._panel_view._scope_type = self.values[0]
            self._panel_view._rule_page = 0
            self._panel_view._selected_rule_keys.clear()
            self._panel_view._status_message = (
                f"已切换到 {SCOPE_TYPE_LABELS[self._panel_view._scope_type]} 规则。"
            )
            await self._panel_view._refresh_message(interaction)


    class _RuleSelect(discord.ui.Select):
        def __init__(self, view: DiscordSendPermissionPanelView):
            page_rules = view._page_rules()
            options = [
                discord.SelectOption(
                    label=_truncate_text(_rule_label(rule), 100),
                    value=_encode_rule_key(rule),
                    description=_truncate_text(_rule_description(rule), 100),
                    default=_encode_rule_key(rule) in view._selected_rule_keys,
                )
                for rule in page_rules
            ]
            if not options:
                options = [
                    discord.SelectOption(
                        label="当前范围暂无可配置项",
                        value="__empty__",
                        default=True,
                    )
                ]
            super().__init__(
                placeholder="勾选当前页要批量调整的条目",
                min_values=0 if page_rules else 1,
                max_values=max(1, len(options)),
                options=options,
                disabled=not page_rules,
                row=2,
            )
            self._panel_view = view

        async def callback(self, interaction: Any) -> None:
            page_keys = {_encode_rule_key(rule) for rule in self._panel_view._page_rules()}
            self._panel_view._selected_rule_keys.difference_update(page_keys)
            self._panel_view._selected_rule_keys.update(
                value for value in self.values if value != "__empty__"
            )
            self._panel_view._status_message = (
                f"当前页已选中 {len(self._panel_view._selected_rule_keys)} 项。"
            )
            await self._panel_view._refresh_message(interaction)


else:

    class DiscordSendPermissionPanelView:  # pragma: no cover - only used when discord is missing
        def __init__(self, *args: Any, **kwargs: Any):
            raise RuntimeError("discord.py is unavailable")


def _discover_discord_clients(root: Any) -> list[Any]:
    queue = deque([(root, 0)])
    visited: set[int] = set()
    clients: list[Any] = []
    seen_clients: set[int] = set()

    while queue:
        obj, depth = queue.popleft()
        if obj is None:
            continue

        marker = id(obj)
        if marker in visited:
            continue
        visited.add(marker)

        if _is_discord_client(obj):
            if marker not in seen_clients:
                clients.append(obj)
                seen_clients.add(marker)
            continue

        if depth >= 5:
            continue

        for child in _iter_children(obj):
            queue.append((child, depth + 1))

    return clients


def _iter_children(obj: Any):
    if isinstance(obj, dict):
        yield from obj.values()
        return

    if isinstance(obj, (list, tuple, set, frozenset, deque)):
        yield from obj
        return

    for attr in CLIENT_DISCOVERY_ATTRS:
        child = getattr(obj, attr, None)
        if child is not None:
            yield child


def _is_discord_client(obj: Any) -> bool:
    if discord is None or obj is None:
        return False
    return (
        "discord" in type(obj).__module__.lower()
        and hasattr(obj, "tree")
        and hasattr(obj, "guilds")
        and callable(getattr(obj, "is_ready", None))
    )


def _rule_sort_key(rule: SendPermissionRule) -> tuple[str, str, str, str]:
    return (
        _rule_label(rule).lower(),
        rule.guild_id,
        rule.channel_id or rule.category_id,
        rule.thread_id,
    )


def _rule_label(rule: SendPermissionRule) -> str:
    if rule.scope_type == "guild":
        return _safe_text(rule.guild_name, rule.guild_id or "未命名服务器")
    if rule.scope_type == "category":
        return _safe_text(rule.category_name, rule.category_id or "未命名分类")
    if rule.scope_type == "channel":
        return _safe_text(rule.channel_name, rule.channel_id or "未命名频道")
    return _safe_text(rule.thread_name, rule.thread_id or "未命名线程")


def _rule_description(rule: SendPermissionRule) -> str:
    prefix = "允许" if rule.allow else "禁止"
    if rule.scope_type == "guild":
        return f"{prefix} | 服务器 ID: {rule.guild_id}"
    if rule.scope_type == "category":
        return f"{prefix} | 分类 ID: {rule.category_id}"
    if rule.scope_type == "channel":
        return f"{prefix} | 频道 ID: {rule.channel_id}"
    parent_name = _safe_text(rule.channel_name, rule.channel_id or "未知父频道")
    return f"{prefix} | 父频道: {parent_name}"


def _render_rule_page(rules: list[SendPermissionRule]) -> str:
    if not rules:
        return "当前页没有条目。可以点击“自动填充刷新”重新扫描。"

    lines: list[str] = []
    length = 0
    for rule in rules:
        line = f"{'✅' if rule.allow else '❌'} {_rule_label(rule)}"
        if rule.scope_type == "thread":
            parent_name = _safe_text(rule.channel_name, rule.channel_id or "未知父频道")
            line = f"{line} | 父频道: {parent_name}"
        if rule.scope_type == "category":
            line = f"{line} | ID: {rule.category_id}"
        elif rule.scope_type == "channel":
            line = f"{line} | ID: {rule.channel_id}"
        elif rule.scope_type == "guild":
            line = f"{line} | ID: {rule.guild_id}"
        else:
            line = f"{line} | ID: {rule.thread_id}"
        if length + len(line) + 1 > 980:
            lines.append("...")
            break
        lines.append(line)
        length += len(line) + 1
    return "\n".join(lines)


def _build_button(
    label: str,
    row: int,
    callback: Callable[[Any], Any],
    disabled: bool = False,
    style: Any | None = None,
):
    if discord is None:
        raise RuntimeError("discord.py is unavailable")
    button = discord.ui.Button(
        label=label,
        row=row,
        disabled=disabled,
        style=style or discord.ButtonStyle.secondary,
    )
    button.callback = callback
    return button


def _encode_rule_key(rule: SendPermissionRule) -> str:
    return "|".join(get_send_permission_rule_key(rule))


def _page_count(total: int, page_size: int) -> int:
    if total <= 0:
        return 0
    return (total + page_size - 1) // page_size


def _safe_text(value: Any, default: str) -> str:
    text = _snowflake_str(value)
    return text or default


def _snowflake_str(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


def _is_admin_interaction(interaction: Any) -> bool:
    user = getattr(interaction, "user", None)
    perms = getattr(user, "guild_permissions", None)
    if perms is None:
        return False
    return bool(getattr(perms, "administrator", False))
