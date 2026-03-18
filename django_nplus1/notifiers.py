from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django_nplus1.exceptions import NPlusOneError

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


class ErrorNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_RAISE"
    ENABLED_DEFAULT = False

    def __init__(self, config: Any) -> None:
        self.error: type[Exception] = getattr(config, "NPLUS1_ERROR", NPlusOneError)

    def notify(self, message: Message) -> None:
        raise self.error(message.message)


def init(config: Any) -> list[Notifier]:
    return [notifier_cls(config) for notifier_cls in (LogNotifier, ErrorNotifier) if notifier_cls.is_enabled(config)]
