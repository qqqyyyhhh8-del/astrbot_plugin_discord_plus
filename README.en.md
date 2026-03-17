# astrbot_plugin_discord_plus

Discord enhancement plugin for AstrBot.

This repository currently adds one missing Discord behavior from AstrBot's native adapter: showing the bot as typing while AstrBot is waiting for the LLM response.

中文说明: [README.md](./README.md)

## Overview

This plugin is designed as a modular Discord feature toolkit instead of a single-purpose script.

Current features:

- Show Discord typing status during `on_waiting_llm_request`
- Stop typing automatically after `on_llm_response`
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

When disabled, the plugin remains loaded but stops sending Discord typing status.

## Extending

To add a new Discord-only feature:

1. Add a new module under `astrbot_plugin_discord_plus_core/features/`.
2. Implement the feature class on top of `FeatureBase`.
3. Register the feature in `DiscordPlusPlugin` inside `main.py`.

## Notes

- This plugin assumes AstrBot's Discord adapter exposes Discord-native objects through the event context.
- The typing logic is implemented defensively because AstrBot internals may vary across versions.
- Only local syntax-level validation has been done in this environment. Full AstrBot runtime verification has not been run here.
