from typing import TYPE_CHECKING, Any

from django_nplus1.detect import Message, Rule, is_allowed, is_inline_ignored
from django_nplus1.exceptions import NPlus1Error
from django_nplus1.scope import DetectionContext
from django_nplus1.signals import nplus1_detected

if TYPE_CHECKING:
    from django_nplus1.notifiers import Notifier


class Profiler(DetectionContext):
    """Test-harness detection context that always raises NPlus1Error.

    Pass ``notifiers=`` to fan out logs/warnings alongside the raise, e.g.::

        from django.conf import settings
        from django_nplus1.notifiers import init

        with Profiler(notifiers=init(settings)):
            ...

    With the default ``notifiers=None`` no notifiers run; only the
    ``nplus1_detected`` signal fires before the raise.
    """

    def __init__(
        self,
        whitelist: list[dict[str, Any]] | None = None,
        notifiers: list[Notifier] | None = None,
    ) -> None:
        rules = [Rule(**item) for item in (whitelist or [])]
        super().__init__(notifiers=notifiers, whitelist=rules)

    def __enter__(self) -> Profiler:
        super().__enter__()
        return self

    def notify(self, message: Message) -> None:
        if message.match(self._whitelist) or is_allowed(message) or is_inline_ignored(message):
            return
        nplus1_detected.send(sender=type(self), message=message)
        for notifier in self._notifiers:
            notifier.notify(message)
        raise NPlus1Error(message.message)
