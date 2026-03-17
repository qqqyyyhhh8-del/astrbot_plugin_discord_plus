# astrbot_plugin_discord_plus

AstrBot Discord enhancement plugin.

This repository currently provides one missing native behavior for the Discord adapter: showing the bot as typing while AstrBot is waiting for the LLM response.

## Current Feature

- Discord typing indicator during `on_waiting_llm_request`
- Automatic stop after the LLM response is returned
- Modular feature layout for future Discord-specific enhancements

## Project Structure

```text
.
|-- main.py
|-- metadata.yaml
|-- requirements.txt
`-- discord_toolkit/
    |-- runtime.py
    |-- discord_bridge.py
    |-- feature_base.py
    `-- features/
        `-- discord_typing.py
```

## How It Works

`main.py` registers the AstrBot plugin and forwards lifecycle hooks into the modular runtime.

`discord_toolkit/runtime.py` dispatches events to feature modules.

`discord_toolkit/features/discord_typing.py` starts a background typing loop when AstrBot enters `on_waiting_llm_request`, then stops it after `on_llm_response`.

`discord_toolkit/discord_bridge.py` tries to locate the Discord channel object from the AstrBot event and calls the Discord typing API in a tolerant way.

## Installation

1. Put this plugin directory under AstrBot's `data/plugins/`.
2. Make sure the plugin folder name is `astrbot_plugin_discord_plus` or a name AstrBot can load correctly.
3. Reload plugins from the AstrBot admin panel.
4. Test it in Discord by sending a message that triggers an LLM response.

## Extending It

To add a new Discord-only feature:

1. Create a new module under `discord_toolkit/features/`.
2. Implement the feature class on top of `FeatureBase`.
3. Register the feature in `DiscordPlusPlugin` inside `main.py`.

This keeps the plugin entrypoint small and avoids stacking all behavior into one file.

## Notes

- This plugin assumes AstrBot is already running with a Discord adapter that exposes Discord channel objects through the event payload.
- The typing feature is implemented defensively because AstrBot adapter internals may differ between versions.
