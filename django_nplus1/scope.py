from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Self

from django_nplus1 import signals
from django_nplus1.detect import LISTENERS, Rule, is_allowed, is_inline_ignored

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from contextvars import Token
    from types import TracebackType

    from django_nplus1.detect import Listener, Message
    from django_nplus1.notifiers import Notifier

# The innermost scope entered in the current context.
_active: ContextVar[DetectionContext | None] = ContextVar("nplus1_active_scope", default=None)

# Reads inside a nested scope can use rows that an enclosing scope loaded.
_FORWARDED = (signals.TOUCH, signals.FIELD_TOUCH)


class DetectionContext:
    """Detects N+1 queries and unused eager loads while the ``with`` block runs.

    Scopes nest. A detection inside an inner scope goes to the notifiers of every
    enclosing scope, and a whitelist entry of any of them suppresses it.
    """

    def __init__(
        self,
        *,
        notifiers: Sequence[Notifier] | None = None,
        whitelist: Sequence[Rule | dict[str, Any]] | None = None,
        sender: Any = None,
    ) -> None:
        self._notifiers = list(notifiers or ())
        self._whitelist = [item if isinstance(item, Rule) else Rule(**item) for item in whitelist or ()]
        self._sender = sender
        self._listeners: dict[str, Listener] = {}
        self._outer: DetectionContext | None = None
        self._tokens: tuple[Token[Any], Token[Any]] | None = None
        # A detection that code inside the block catches must still fail the scope.
        self._raised: Exception | None = None
        self._exiting = False

    def __enter__(self) -> Self:
        if self._tokens is not None:
            raise RuntimeError(f"{type(self).__name__} is already active.")
        self._outer = _active.get()
        self._tokens = (signals.setup_context(inherit=_FORWARDED), _active.set(self))
        try:
            for name, listener_cls in LISTENERS.items():
                listener = listener_cls(self)
                listener.setup()
                self._listeners[name] = listener
        except BaseException:
            self._close()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """End the scope and raise its detection, even one that the block caught."""
        # Detections made from here on are raised below, not inside the block.
        self._exiting = True
        caught = self._raised
        outer = self._outer
        error: Exception | None = None
        # Tear down every listener even if one raises, so none outlives the scope.
        try:
            for listener in self._listeners.values():
                try:
                    listener.teardown()
                except Exception as exc:  # noqa: BLE001
                    error = error or exc
        finally:
            self._close()
        if exc_type is None:
            error = caught or error
        elif caught is not None and caught is not exc_val and issubclass(exc_type, Exception):
            error = caught
        else:
            return
        if error is not None:
            if outer is not None:
                outer._record(error)
            raise error

    def _close(self) -> None:
        self._listeners.clear()
        if self._tokens is not None:
            registry_token, active_token = self._tokens
            self._tokens = None
            _active.reset(active_token)
            signals.teardown_context(registry_token)
        self._outer = None
        self._raised = None
        self._exiting = False

    def _record(self, error: Exception) -> None:
        for scope in self._chain():
            if scope._raised is None:
                scope._raised = error

    def _chain(self) -> Iterator[DetectionContext]:
        scope: DetectionContext | None = self
        while scope is not None:
            yield scope
            scope = scope._outer

    def outer_listener[L: Listener](self, listener_cls: type[L]) -> L | None:
        """Return the enclosing scope's listener of this class, if there is one."""
        if self._outer is None:
            return None
        listeners = self._outer._listeners.values()
        return next((listener for listener in listeners if isinstance(listener, listener_cls)), None)

    def suppresses(self, message: Message) -> bool:
        """Check ``nplus1_allow()``, inline ignore comments, and the whitelists of this and the enclosing scopes."""
        return (
            is_allowed(message)
            or is_inline_ignored(message)
            or any(message.match(scope._whitelist) for scope in self._chain())
        )

    def notify(self, message: Message) -> None:
        if self.suppresses(message):
            return
        sender = self._sender if self._sender is not None else type(self)
        signals.nplus1_detected.send(sender=sender, message=message)
        error: Exception | None = None
        notified: list[Notifier] = []
        for scope in self._chain():
            try:
                scope._deliver(message, notified)
            except Exception as exc:  # noqa: BLE001
                error = error or exc
        if error is not None:
            if not self._exiting:
                self._record(error)
            raise error

    def _deliver(self, message: Message, notified: list[Notifier]) -> None:
        for notifier in self._notifiers:
            if notifier not in notified:
                notified.append(notifier)
                notifier.notify(message)
