from typing import Any


def get_chain_items(event: Any) -> list[Any] | None:
    result = _get_result(event)
    if result is None:
        return None

    chain = getattr(result, "chain", None)
    if chain is None:
        return None

    items = getattr(chain, "chain", None)
    if isinstance(items, list):
        return items
    if isinstance(chain, list):
        return chain
    return None


def set_chain_items(event: Any, items: list[Any]) -> bool:
    result = _get_result(event)
    if result is None:
        return False

    chain = getattr(result, "chain", None)
    if chain is None:
        return False

    if hasattr(chain, "chain"):
        chain.chain = items
        return True

    if isinstance(chain, list):
        result.chain = items
        return True

    return False


def build_plain_component(text: str) -> Any | None:
    component_cls = _load_component_class("Plain")
    if component_cls is None:
        return None

    builders = (
        lambda: component_cls(text),
        lambda: component_cls(text=text),
        lambda: component_cls(content=text),
        lambda: component_cls(plain=text),
    )
    for builder in builders:
        try:
            return builder()
        except TypeError:
            continue
    return None


def build_reply_component(message_id: str | int) -> Any | None:
    component_cls = _load_component_class("Reply")
    if component_cls is None:
        return None

    builders = (
        lambda: component_cls(message_id),
        lambda: component_cls(id=message_id),
        lambda: component_cls(message_id=message_id),
        lambda: component_cls(msg_id=message_id),
    )
    for builder in builders:
        try:
            return builder()
        except TypeError:
            continue
    return None


def component_name(component: Any) -> str:
    return type(component).__name__


def _get_result(event: Any) -> Any | None:
    getter = getattr(event, "get_result", None)
    if callable(getter):
        return getter()
    return None


def _load_component_class(name: str) -> Any | None:
    try:
        from astrbot.api import message_components as components
    except Exception:
        return None
    return getattr(components, name, None)
