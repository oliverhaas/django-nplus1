from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django_nplus1.detect import LISTENERS, Listener, Message, Rule
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.signals import nplus1_detected

if TYPE_CHECKING:
    from types import TracebackType


class Profiler:
    def __init__(self, whitelist: list[dict[str, Any]] | None = None) -> None:
        self.whitelist = [Rule(**item) for item in (whitelist or [])]
        self._listeners: dict[str, Listener] = {}

    def __enter__(self) -> Profiler:
        for name, listener_type in LISTENERS.items():
            self._listeners[name] = listener_type(self)
            self._listeners[name].setup()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        for name in list(LISTENERS.keys()):
            self._listeners.pop(name).teardown()

    def notify(self, message: Message) -> None:
        if not message.match(self.whitelist):
            nplus1_detected.send(sender=self.__class__, message=message)
            raise NPlus1Error(message.message)
