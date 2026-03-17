from typing import Any, Iterable


class DiscordFeatureRuntime:
    def __init__(self, features: Iterable[Any], logger: Any):
        self._features = list(features)
        self._logger = logger

    async def on_decorating_result(self, event: Any) -> None:
        for feature in self._features:
            try:
                await feature.on_decorating_result(event)
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed in decorating hook",
                    getattr(feature, "name", feature.__class__.__name__),
                )
            if _event_stopped(event):
                break

    async def on_waiting_llm_request(self, event: Any) -> None:
        for feature in self._features:
            try:
                await feature.on_waiting_llm_request(event)
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed in waiting hook",
                    getattr(feature, "name", feature.__class__.__name__),
                )
            if _event_stopped(event):
                break

    async def on_llm_response(self, event: Any, resp: Any) -> None:
        for feature in self._features:
            try:
                await feature.on_llm_response(event, resp)
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed in response hook",
                    getattr(feature, "name", feature.__class__.__name__),
                )
            if _event_stopped(event):
                break

    async def shutdown(self) -> None:
        for feature in self._features:
            try:
                await feature.shutdown()
            except Exception:
                self._logger.exception(
                    "discord feature '%s' failed during shutdown",
                    getattr(feature, "name", feature.__class__.__name__),
                )


def _event_stopped(event: Any) -> bool:
    checker = getattr(event, "is_stopped", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False
