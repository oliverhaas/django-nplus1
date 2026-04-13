from typing import Any

from django_nplus1.detect import Message, Rule, is_allowed
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.scope import DetectionContext
from django_nplus1.signals import nplus1_detected


class Profiler(DetectionContext):
    def __init__(self, whitelist: list[dict[str, Any]] | None = None) -> None:
        rules = [Rule(**item) for item in (whitelist or [])]
        super().__init__(whitelist=rules)

    def __enter__(self) -> Profiler:
        super().__enter__()
        return self

    def notify(self, message: Message) -> None:
        if not message.match(self._whitelist) and not is_allowed(message):
            nplus1_detected.send(sender=type(self), message=message)
            raise NPlus1Error(message.message)
