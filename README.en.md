# astrbot_plugin_discord_plus

Discord enhancement plugin for AstrBot.

This repository currently adds one missing Discord behavior from AstrBot's native adapter: showing the bot as typing while AstrBot is waiting for the LLM response.

中文说明: [README.md](./README.md)

## Overview

This plugin is designed as a modular Discord feature toolkit instead of a single-purpose script.

Current features:

- Show Discord typing status during `on_waiting_llm_request`
- Stop typing automatically after `on_llm_response`
- Convert default AstrBot `At` segments into Discord mention syntax
- Add reply reference when the bot answers a Discord message
- Override whether the bot may speak in a Discord guild, category, channel, or thread
- Provide admin commands to auto-fill Discord send-permission rules
- Auto-register a native Discord admin command with a Chinese embed/UI panel for bulk rule management
- Keep a modular structure for future Discord-specific features

## Project Structure

```text
.
|-- main.py
|-- metadata.yaml
|-- requirements.txt
`-- astrbot_plugin_discord_plus_core/
    |-- runtime.py
    |-- discord_bridge.py
    |-- feature_base.py
    `-- features/
        `-- discord_typing.py
```

## How It Works

`main.py`

Registers the AstrBot plugin and forwards AstrBot lifecycle hooks into the internal runtime.

`astrbot_plugin_discord_plus_core/runtime.py`

Dispatches events to feature modules so the plugin entrypoint stays small and maintainable.

`astrbot_plugin_discord_plus_core/features/discord_typing.py`

Implements the typing feature. It starts a background typing loop when AstrBot enters `on_waiting_llm_request` and stops after `on_llm_response`.

`astrbot_plugin_discord_plus_core/features/discord_mention_fix.py`

Converts default AstrBot `At` segments into Discord-compatible `<@user_id>` mentions.

`astrbot_plugin_discord_plus_core/features/discord_reply_reference.py`

Uses Discord-native `reply/reference` sending so replies can reference the original message.

`astrbot_plugin_discord_plus_core/features/discord_send_permission.py`

Controls whether the bot is allowed to speak for a Discord guild, category, channel, or thread, and supports auto-filling rule entries.

`astrbot_plugin_discord_plus_core/features/discord_send_permission_ui.py`

Registers the native Discord `/discord_send_panel` command on startup and serves an admin-only ephemeral Chinese embed/UI for bulk permission management.

`astrbot_plugin_discord_plus_core/discord_bridge.py`

Tries to locate a Discord channel object from the AstrBot event and call the Discord typing API defensively, avoiding tight coupling to AstrBot adapter internals.

## Installation

1. Put this plugin directory under AstrBot's `data/plugins/`.
2. Keep the plugin folder name as `astrbot_plugin_discord_plus`.
3. Reload plugins from the AstrBot admin panel.
4. Test it in Discord with a message that triggers an LLM response.

## Configuration

The plugin now exposes one panel-editable option in the AstrBot admin UI:

- `typing_enabled`
- `mention_fix_enabled`
- `reply_reference_enabled`
- `send_permission_override_enabled`
- `send_permission_rules`

When a toggle is disabled, the plugin remains loaded but stops that specific Discord enhancement.

The AstrBot config panel can still edit `send_permission_rules` manually; the native Discord panel writes back to the same config entries.

`send_permission_rules` uses a `template_list` with four rule scopes:

- `guild`
- `category`
- `channel`
- `thread`

Priority is `thread > channel > category > guild`. For rules at the same level, later entries win. Once send-permission override is enabled, unmatched Discord scopes are denied by default.

## Admin Commands

- `/discord_send_rules_refresh`
  Scans guilds, categories, channels, and threads from the current Discord client and writes them into `send_permission_rules`. Newly discovered rules default to `allow=false`.
- `/discord_send_scope_here`
  Shows the current Discord guild / category / channel / thread IDs and whether speaking is currently allowed there.
- `/discord_send_panel`
  A native Discord command that is auto-synced on startup for connected guilds. Admins get an ephemeral Chinese embed/UI to switch guilds, change rule scope, select all/invert the current page, and batch allow or deny speaking.

## Extending

To add a new Discord-only feature:

1. Add a new module under `astrbot_plugin_discord_plus_core/features/`.
2. Implement the feature class on top of `FeatureBase`.
3. Register the feature in `DiscordPlusPlugin` inside `main.py`.

## Notes

- This plugin assumes AstrBot's Discord adapter exposes Discord-native objects through the event context.
- The typing logic is implemented defensively because AstrBot internals may vary across versions.
- Send-permission override currently targets the LLM reply flow, so it governs whether the bot answers in that Discord scope.
- Only local syntax-level validation has been done in this environment. Full AstrBot runtime verification has not been run here.
