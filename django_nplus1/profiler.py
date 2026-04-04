from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_nplus1.detect import LISTENERS, Message, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.signals import nplus1_detected, setup_context, teardown_context

if TYPE_CHECKING:
    from contextvars import Token
    from types import TracebackType

    from django_nplus1.detect import Listener


class Profiler:
    def __init__(self, whitelist: list[dict[str, Any]] | None = None) -> None:
        self.whitelist = [Rule(**item) for item in (whitelist or [])]
        self._detection_listeners: dict[str, Listener] = {}
        self._token: Token[Any] | None = None

    def __enter__(self) -> Profiler:
        self._token = setup_context()
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
        try:
            for name in list(LISTENERS.keys()):
                listener = self._detection_listeners.pop(name, None)
                if listener:
                    listener.teardown()
        finally:
            if self._token is not None:
                teardown_context(self._token)

    def notify(self, message: Message) -> None:
        if not message.match(self.whitelist):
            nplus1_detected.send(sender=self.__class__, message=message)
            raise NPlus1Error(message.message)
