from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any

from django_nplus1.exceptions import NPlus1Error

if TYPE_CHECKING:
    from django_nplus1.detect import Message

_SENTINEL = object()


class Notifier:
    CONFIG_KEY: str | None = None
    ENABLED_DEFAULT: bool = False

    @classmethod
    def is_enabled(cls, config: Any) -> bool:
        if cls.CONFIG_KEY is None:
            return cls.ENABLED_DEFAULT
        value = getattr(config, cls.CONFIG_KEY, _SENTINEL)
        if value is _SENTINEL:
            return cls.ENABLED_DEFAULT
        return bool(value)

    def notify(self, message: Message) -> None:
        pass


class LogNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_LOG"
    ENABLED_DEFAULT = True

    def __init__(self, config: Any) -> None:
        self.logger: logging.Logger = getattr(config, "NPLUS1_LOGGER", logging.getLogger("django_nplus1"))
        self.level: int = getattr(config, "NPLUS1_LOG_LEVEL", logging.WARNING)

    def notify(self, message: Message) -> None:
        self.logger.log(self.level, message.message)


class WarningNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_WARN"
    ENABLED_DEFAULT = False

    def __init__(self, config: Any) -> None:
        pass

    def notify(self, message: Message) -> None:
        if message.caller:
            filename, lineno, _ = message.caller
            warnings.warn_explicit(
                message.message,
                UserWarning,
                filename=filename,
                lineno=lineno,
            )
        else:
            # No caller info available (e.g. EagerLoadMessage at teardown).
            # Use warn_explicit with our own package as source rather than
            # a misleading stacklevel that points to internal dispatch code.
            warnings.warn_explicit(
                message.message,
                UserWarning,
                filename="django_nplus1",
                lineno=0,
            )


class ErrorNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_RAISE"
    ENABLED_DEFAULT = False

    def __init__(self, config: Any) -> None:
        self.error: type[Exception] = getattr(config, "NPLUS1_ERROR", NPlus1Error)

    def notify(self, message: Message) -> None:
        raise self.error(message.message)


def init(config: Any) -> list[Notifier]:
    return [
        notifier_cls(config)
        for notifier_cls in (LogNotifier, WarningNotifier, ErrorNotifier)
        if notifier_cls.is_enabled(config)
    ]
