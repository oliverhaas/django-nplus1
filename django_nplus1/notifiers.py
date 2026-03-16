from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django_nplus1.exceptions import NPlusOneError

if TYPE_CHECKING:
    from django_nplus1.detect import Message


class Notifier:
    CONFIG_KEY: str | None = None
    ENABLED_DEFAULT: bool = False

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        if cls.CONFIG_KEY is None:
            return cls.ENABLED_DEFAULT
        if cls.CONFIG_KEY in config:
            return bool(config[cls.CONFIG_KEY])
        return cls.ENABLED_DEFAULT

    def notify(self, message: Message) -> None:
        pass


class LogNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_LOG"
    ENABLED_DEFAULT = True

    def __init__(self, config: dict[str, Any]) -> None:
        self.logger: logging.Logger = config.get("NPLUS1_LOGGER", logging.getLogger("django_nplus1"))
        self.level: int = config.get("NPLUS1_LOG_LEVEL", logging.WARNING)

    def notify(self, message: Message) -> None:
        self.logger.log(self.level, message.message)


class ErrorNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_RAISE"
    ENABLED_DEFAULT = False

    def __init__(self, config: dict[str, Any]) -> None:
        self.error: type[Exception] = config.get("NPLUS1_ERROR", NPlusOneError)

    def notify(self, message: Message) -> None:
        raise self.error(message.message)


def init(config: dict[str, Any]) -> list[Notifier]:
    return [notifier_cls(config) for notifier_cls in (LogNotifier, ErrorNotifier) if notifier_cls.is_enabled(config)]
