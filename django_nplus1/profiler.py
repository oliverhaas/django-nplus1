from typing import TYPE_CHECKING, Any

from django_nplus1.exceptions import NPlus1Error
from django_nplus1.scope import DetectionContext

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django_nplus1.detect import Message
    from django_nplus1.notifiers import Notifier


class Profiler(DetectionContext):
    """Detection scope for tests that raises ``NPlus1Error`` on the first detection.

    ``notifiers`` run before the raise, for example ``Profiler(notifiers=init(settings))``
    to also log through the configured logger.
    """

    def __init__(
        self,
        whitelist: Sequence[dict[str, Any]] | None = None,
        notifiers: Sequence[Notifier] | None = None,
    ) -> None:
        super().__init__(notifiers=notifiers, whitelist=whitelist)

    def _deliver(self, message: Message, notified: list[Notifier]) -> None:
        super()._deliver(message, notified)
        raise NPlus1Error(message.message)
