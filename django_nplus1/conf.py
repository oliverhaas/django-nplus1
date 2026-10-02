"""Readers for the ``NPLUS1_*`` settings that reject values detection can't use."""

import logging
import sys
from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from django_nplus1.exceptions import NPlus1Error

THRESHOLD_SETTINGS = ("NPLUS1_THRESHOLD", "NPLUS1_GET_THRESHOLD", "NPLUS1_DUPLICATE_QUERY_THRESHOLD")


def threshold(config: Any, name: str) -> int:
    value = getattr(config, name, 2)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ImproperlyConfigured(f"{name} must be an integer of at least 1, got {value!r}.")
    return value


def check_thresholds(config: Any) -> None:
    for name in THRESHOLD_SETTINGS:
        threshold(config, name)


def check_installed() -> None:
    """Raise unless the app's ``ready()`` has installed the ORM hooks that detection relies on."""
    if "django_nplus1.patch" not in sys.modules:
        raise ImproperlyConfigured(
            "Add 'django_nplus1' to INSTALLED_APPS. Without it, django-nplus1 detects nothing.",
        )


def project_packages(config: Any) -> tuple[str, ...]:
    value = getattr(config, "NPLUS1_PROJECT_PACKAGES", ())
    if not isinstance(value, (list, tuple)) or not all(isinstance(name, str) and name for name in value):
        raise ImproperlyConfigured(f"NPLUS1_PROJECT_PACKAGES must be a list of module names, got {value!r}.")
    return tuple(value)


def logger(config: Any) -> Any:
    value = getattr(config, "NPLUS1_LOGGER", None)
    if value is None:
        return logging.getLogger("django_nplus1")
    if isinstance(value, str):
        return logging.getLogger(value)
    if not callable(getattr(value, "log", None)):
        raise ImproperlyConfigured(f"NPLUS1_LOGGER must be a logger or a logger name, got {value!r}.")
    return value


def log_level(config: Any) -> int:
    value = getattr(config, "NPLUS1_LOG_LEVEL", logging.WARNING)
    if isinstance(value, str):
        level = logging.getLevelNamesMapping().get(value.upper())
        if level is None:
            raise ImproperlyConfigured(f"NPLUS1_LOG_LEVEL {value!r} is not a logging level name.")
        return level
    if isinstance(value, bool) or not isinstance(value, int):
        raise ImproperlyConfigured(f"NPLUS1_LOG_LEVEL must be an int or a level name, got {value!r}.")
    return value


def error_class(config: Any) -> type[Exception]:
    value = getattr(config, "NPLUS1_ERROR", NPlus1Error)
    if isinstance(value, str):
        try:
            value = import_string(value)
        except ImportError as exc:
            raise ImproperlyConfigured(f"NPLUS1_ERROR {value!r} could not be imported.") from exc
    if not (isinstance(value, type) and issubclass(value, Exception)):
        raise ImproperlyConfigured(f"NPLUS1_ERROR must be an exception class, got {value!r}.")
    return value
