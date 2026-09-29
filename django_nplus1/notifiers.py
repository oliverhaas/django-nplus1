import warnings
from typing import TYPE_CHECKING, Any

from django_nplus1 import conf

if TYPE_CHECKING:
    from django_nplus1.detect import Message


class Notifier:
    CONFIG_KEY: str
    ENABLED_DEFAULT = False

    def __init__(self, config: Any) -> None:
        pass

    # Notifiers built from the same settings are equal, so nested scopes report once.
    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and vars(other) == vars(self)

    def __hash__(self) -> int:
        return hash(type(self))

    @classmethod
    def is_enabled(cls, config: Any) -> bool:
        return bool(getattr(config, cls.CONFIG_KEY, cls.ENABLED_DEFAULT))

    def notify(self, message: Message) -> None:
        raise NotImplementedError


class LogNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_LOG"
    ENABLED_DEFAULT = True

    def __init__(self, config: Any) -> None:
        self.logger = conf.logger(config)
        self.level = conf.log_level(config)

    def notify(self, message: Message) -> None:
        self.logger.log(self.level, message.message)


class WarningNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_WARN"

    def notify(self, message: Message) -> None:
        # The warning points at the line that triggered the detection.
        if message.caller:
            filename, lineno, _ = message.caller
        elif message.callers and message.callers[-1]:
            filename, lineno, _ = message.callers[-1][0]
        else:
            filename, lineno = "django_nplus1", 0
        warnings.warn_explicit(message.message, UserWarning, filename=filename, lineno=lineno)


class ErrorNotifier(Notifier):
    CONFIG_KEY = "NPLUS1_RAISE"

    def __init__(self, config: Any) -> None:
        self.error = conf.error_class(config)

    def notify(self, message: Message) -> None:
        raise self.error(message.message)


def init(config: Any) -> list[Notifier]:
    """Build the notifiers that the ``NPLUS1_LOG``, ``NPLUS1_WARN`` and ``NPLUS1_RAISE`` settings enable."""
    return [
        notifier_cls(config)
        for notifier_cls in (LogNotifier, WarningNotifier, ErrorNotifier)
        if notifier_cls.is_enabled(config)
    ]
