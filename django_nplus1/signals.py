from __future__ import annotations

import contextlib
import functools
import threading
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django.dispatch import Signal

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# Django signal emitted on every N+1 or unused eager load detection.
# Receivers get ``sender`` (the notifying object) and ``message`` (a Message instance).
nplus1_detected = Signal()

_listeners: defaultdict[str, list[Callable[..., Any]]] = defaultdict(list)


def get_worker() -> str:
    return str(threading.current_thread().ident)


def connect(signal_name: str, callback: Callable[..., Any], *, sender: str | None = None) -> None:
    _listeners[_key(signal_name, sender)].append(callback)


def disconnect(signal_name: str, callback: Callable[..., Any], *, sender: str | None = None) -> None:
    key = _key(signal_name, sender)
    try:
        _listeners[key].remove(callback)
    except ValueError:
        pass


def send(signal_name: str, *, sender: str | None = None, **kwargs: Any) -> None:
    for callback in _listeners[_key(signal_name, sender)][:]:
        callback(**kwargs)


def _key(signal_name: str, sender: str | None) -> str:
    if sender is None:
        return signal_name
    return f"{signal_name}:{sender}"


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
            sender=get_worker(),
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
def suppress(signal_name: str, sender: str | None = None) -> Generator[None]:
    sender = sender or get_worker()
    key = _key(signal_name, sender)
    saved = _listeners[key][:]
    _listeners[key].clear()
    try:
        yield
    finally:
        _listeners[key] = saved


# Signal names as constants
LOAD = "load"
IGNORE_LOAD = "ignore_load"
LAZY_LOAD = "lazy_load"
EAGER_LOAD = "eager_load"
TOUCH = "touch"
