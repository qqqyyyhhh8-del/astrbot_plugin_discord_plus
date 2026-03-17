from typing import Any


class FeatureBase:
    name = "feature"

    async def on_decorating_result(self, event: Any) -> None:
        return None

    async def on_waiting_llm_request(self, event: Any) -> None:
        return None

    async def on_llm_response(self, event: Any, resp: Any) -> None:
        return None

    async def shutdown(self) -> None:
        return None
