import asyncio
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from discord_toolkit.discord_bridge import build_event_key, find_discord_channel, trigger_typing
from discord_toolkit.feature_base import FeatureBase


class DiscordTypingFeature(FeatureBase):
    name = "discord_typing"

    def __init__(
        self,
        logger: Any,
        config_getter: Callable[[], bool],
        interval_seconds: float = 1.0,
        max_duration_seconds: float = 180.0,
    ):
        self._logger = logger
        self._config_getter = config_getter
        self._interval_seconds = interval_seconds
        self._max_duration_seconds = max_duration_seconds
        self._tasks: dict[str, asyncio.Task] = {}

    async def on_waiting_llm_request(self, event: Any) -> None:
        if not self._config_getter():
            return

        key = build_event_key(event)
        if key in self._tasks:
            return

        channel = find_discord_channel(event)
        if channel is None:
            return

        task = asyncio.create_task(self._typing_loop(key, channel))
        self._tasks[key] = task

    async def on_llm_response(self, event: Any, resp: Any) -> None:
        await self._stop_task(build_event_key(event))

    async def shutdown(self) -> None:
        keys = list(self._tasks)
        for key in keys:
            await self._stop_task(key)

    async def _typing_loop(self, key: str, channel: Any) -> None:
        deadline = asyncio.get_running_loop().time() + self._max_duration_seconds
        try:
            while True:
                ok = await trigger_typing(channel)
                if not ok:
                    return

                if asyncio.get_running_loop().time() >= deadline:
                    return

                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("discord typing loop failed for %s", key)
        finally:
            self._tasks.pop(key, None)

    async def _stop_task(self, key: str) -> None:
        task = self._tasks.pop(key, None)
        if task is None:
            return

        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
