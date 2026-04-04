from __future__ import annotations

import contextlib
import functools
from collections import defaultdict
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# Per-context listener registry
_listeners: ContextVar[defaultdict[str, list[Callable[..., Any]]]] = ContextVar(
    "nplus1_listeners",
)


def _get_listeners() -> defaultdict[str, list[Callable[..., Any]]]:
    try:
        return _listeners.get()
    except LookupError:
        registry: defaultdict[str, list[Callable[..., Any]]] = defaultdict(list)
        _listeners.set(registry)
        return registry


def connect(signal_name: str, callback: Callable[..., Any]) -> None:
    _get_listeners()[signal_name].append(callback)


def disconnect(signal_name: str, callback: Callable[..., Any]) -> None:
    try:
        _get_listeners()[signal_name].remove(callback)
    except (ValueError, LookupError):
        pass


def send(signal_name: str, **kwargs: Any) -> None:
    try:
        listeners = _listeners.get()
    except LookupError:
        return  # No active context — detection not enabled
    for callback in listeners[signal_name][:]:
        callback(**kwargs)


def signalify(
    signal_name: str,
    func: Callable[..., Any],
    *,
    parser: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        ret = func(*args, **kwargs)
        send(
            signal_name,
            args=args,
            kwargs=kwargs,
            ret=ret,
            context={},
            parser=parser,
        )
        return ret

    return wrapped


def designalify(signal_name: str, func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        with suppress(signal_name):
            return func(*args, **kwargs)

    return wrapped


@contextlib.contextmanager
def suppress(signal_name: str) -> Generator[None]:
    try:
        registry = _listeners.get()
    except LookupError:
        yield
        return
    saved = registry[signal_name][:]
    registry[signal_name].clear()
    try:
        yield
    finally:
        registry[signal_name] = saved


# Signal names as constants
LOAD = "load"
IGNORE_LOAD = "ignore_load"
LAZY_LOAD = "lazy_load"
EAGER_LOAD = "eager_load"
TOUCH = "touch"
