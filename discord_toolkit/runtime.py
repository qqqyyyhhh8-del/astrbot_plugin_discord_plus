from typing import Any, Iterable


class DiscordFeatureRuntime:
    def __init__(self, features: Iterable[Any], logger: Any):
        self._features = list(features)
        self._logger = logger

    async def on_waiting_llm_request(self, event: Any) -> None:
        for feature in self._features:
            try:
                await feature.on_waiting_llm_request(event)
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed in waiting hook",
                    getattr(feature, "name", feature.__class__.__name__),
                )

    async def on_llm_response(self, event: Any, resp: Any) -> None:
        for feature in self._features:
            try:
                await feature.on_llm_response(event, resp)
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed in response hook",
                    getattr(feature, "name", feature.__class__.__name__),
                )

    async def shutdown(self) -> None:
        for feature in self._features:
            try:
                await feature.shutdown()
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed during shutdown",
                    getattr(feature, "name", feature.__class__.__name__),
                )
