from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from django_nplus1.detect import LISTENERS, Listener, Message, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.signals import _listeners, nplus1_detected

if TYPE_CHECKING:
    from contextvars import Token
    from types import TracebackType


class Profiler:
    def __init__(self, whitelist: list[dict[str, Any]] | None = None) -> None:
        self.whitelist = [Rule(**item) for item in (whitelist or [])]
        self._detection_listeners: dict[str, Listener] = {}
        self._token: Token[defaultdict[str, list[Any]]] | None = None

    def __enter__(self) -> Profiler:
        self._token = _listeners.set(defaultdict(list))
        for name, listener_type in LISTENERS.items():
            self._detection_listeners[name] = listener_type(self)
            self._detection_listeners[name].setup()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        for name in list(LISTENERS.keys()):
            self._detection_listeners.pop(name).teardown()
        if self._token is not None:
            _listeners.reset(self._token)

    def notify(self, message: Message) -> None:
        if not message.match(self.whitelist):
            nplus1_detected.send(sender=self.__class__, message=message)
            raise NPlus1Error(message.message)
