from typing import TYPE_CHECKING, Any

from django_nplus1.detect import LISTENERS, is_allowed, is_inline_ignored
from django_nplus1.signals import nplus1_detected, setup_context, teardown_context

if TYPE_CHECKING:
    from collections.abc import Sequence
    from contextvars import Token
    from types import TracebackType

    from django_nplus1.detect import Listener, Message, Rule
    from django_nplus1.notifiers import Notifier


class DetectionContext:
    """Reusable detection context for N+1 query detection.

    Context manager that activates N+1 detection for its duration.
    Used by ``NPlus1Middleware`` (per-request), ``Profiler`` (per-test),
    and the Celery integration (per-task).

    Usage::

        with DetectionContext(notifiers=nots, whitelist=wl, sender=MyClass):
            code_to_monitor()
    """

    def __init__(
        self,
        *,
        notifiers: list[Notifier] | None = None,
        whitelist: Sequence[Rule] | None = None,
        sender: Any = None,
    ) -> None:
        self._notifiers = notifiers or []
        self._whitelist = whitelist or []
        self._sender = sender
        self._listeners: dict[str, Listener] = {}
        self._token: Token[Any] | None = None

    def __enter__(self) -> DetectionContext:
        self._token = setup_context()
        for name, listener_cls in LISTENERS.items():
            listener = listener_cls(self)
            listener.setup()
            self._listeners[name] = listener
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Tear down every listener even if one raises; a skipped one keeps checking
        # queries after the scope. The body's exception outranks teardown detections.
        error: Exception | None = None
        try:
            for listener in self._listeners.values():
                try:
                    listener.teardown()
                except Exception as exc:  # noqa: BLE001
                    error = error or exc
        finally:
            self._listeners.clear()
            if self._token is not None:
                teardown_context(self._token)
                self._token = None
        if error is not None and exc_type is None:
            raise error

    def notify(self, message: Message) -> None:
        if message.match(self._whitelist) or is_allowed(message) or is_inline_ignored(message):
            return
        sender = self._sender if self._sender is not None else type(self)
        nplus1_detected.send(sender=sender, message=message)
        for notifier in self._notifiers:
            notifier.notify(message)
