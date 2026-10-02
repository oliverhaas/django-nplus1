import asyncio
import contextlib
import contextvars
import logging
import threading
from collections import defaultdict
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.dispatch import Signal

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable
    from contextvars import Token

logger = logging.getLogger("django_nplus1")

# Django signal sent once per detection. Receivers get ``sender`` (the class of the
# scope that detected it) and ``message`` (a Message instance).
nplus1_detected = Signal()


def _send_detected(sender: Any, message: Any) -> None:
    try:
        nplus1_detected.send_robust(sender=sender, message=message)
    except Exception:
        logger.exception("django-nplus1: nplus1_detected receivers not run")


def send_detected(sender: Any, message: Any) -> None:
    """Send ``nplus1_detected``. Django logs a receiver that raises, and detection goes on."""
    if not nplus1_detected.has_listeners(sender):
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _send_detected(sender, message)
        return
    # send_robust() runs async receivers with async_to_sync(), which refuses to run in
    # a thread with an event loop, so hand it a thread of its own.
    thread = threading.Thread(target=contextvars.copy_context().run, args=(_send_detected, sender, message))
    thread.start()
    thread.join()


# Per-context listener registry
_listeners: ContextVar[defaultdict[str, list[Callable[..., Any]]] | None] = ContextVar(
    "nplus1_listeners",
    default=None,
)

# Signal names muted in the current context by suppress()
_suppressed: ContextVar[frozenset[str]] = ContextVar("nplus1_suppressed", default=frozenset())


def active() -> bool:
    """Return True while a detection scope is active in the current context."""
    return _listeners.get() is not None


def connect(signal_name: str, callback: Callable[..., Any]) -> None:
    listeners = _listeners.get()
    if listeners is not None:
        listeners[signal_name].append(callback)


def disconnect(signal_name: str, callback: Callable[..., Any]) -> None:
    listeners = _listeners.get()
    if listeners is None:
        return
    with contextlib.suppress(ValueError):
        listeners[signal_name].remove(callback)


def send(signal_name: str, **kwargs: Any) -> None:
    listeners = _listeners.get()
    if listeners is None or signal_name in _suppressed.get():
        return
    callbacks = listeners.get(signal_name)
    if not callbacks:
        return
    for callback in callbacks[:]:
        callback(**kwargs)


def _args(args: Any, kwargs: Any, context: Any, ret: Any = None) -> Any:
    return args


def emit(signal_name: str, *args: Any, **context: Any) -> None:
    """Send a signal whose payload is its positional arguments."""
    send(signal_name, args=args, kwargs={}, context=context, ret=None, parser=_args)


@contextlib.contextmanager
def suppress(signal_name: str) -> Generator[None]:
    """Mute one signal in the current context. Other threads and tasks keep receiving it."""
    token = _suppressed.set(_suppressed.get() | {signal_name})
    try:
        yield
    finally:
        _suppressed.reset(token)


def setup_context(inherit: Iterable[str] = ()) -> Token[defaultdict[str, list[Callable[..., Any]]] | None]:
    """Create a fresh listener registry for the current context. Returns a token for teardown.

    Callbacks for the ``inherit`` signals carry over from the enclosing registry.
    """
    registry: defaultdict[str, list[Callable[..., Any]]] = defaultdict(list)
    outer = _listeners.get()
    if outer is not None:
        for signal_name in inherit:
            registry[signal_name] = list(outer.get(signal_name, ()))
    return _listeners.set(registry)


def teardown_context(token: Token[defaultdict[str, list[Callable[..., Any]]] | None]) -> None:
    """Reset the listener registry to the state before setup_context."""
    _listeners.reset(token)


# Signal names as constants
LOAD = "load"
IGNORE_LOAD = "ignore_load"
LAZY_LOAD = "lazy_load"
EAGER_LOAD = "eager_load"
TOUCH = "touch"
GET_CALL = "get_call"
FIELD_LOAD = "field_load"
FIELD_TOUCH = "field_touch"
QUERY = "query"
