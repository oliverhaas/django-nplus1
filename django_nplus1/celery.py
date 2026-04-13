"""Celery integration for per-task N+1 query detection.

Wraps each Celery task execution in a DetectionContext, mirroring how
NPlus1Middleware wraps HTTP requests.

Activate via settings::

    NPLUS1_CELERY = True

Or manually::

    from django_nplus1.celery import setup_celery_detection
    setup_celery_detection()
"""

from __future__ import annotations

import logging
from typing import Any

from django_nplus1.middleware import _load_config
from django_nplus1.scope import DetectionContext

logger = logging.getLogger("django_nplus1")

# task_id -> active DetectionContext (one entry per in-flight task)
_active_scopes: dict[str, DetectionContext] = {}

_connected = False


def _on_prerun(sender: Any = None, task_id: str = "", **kwargs: Any) -> None:
    """Create and enter a DetectionContext for this task."""
    try:
        nots, whitelist = _load_config()
    except Exception:  # noqa: BLE001
        logger.debug("Failed to load config for task %s", task_id, exc_info=True)
        return
    scope = DetectionContext(notifiers=nots, whitelist=whitelist)
    scope.__enter__()
    _active_scopes[task_id] = scope


def _on_postrun(sender: Any = None, task_id: str = "", **kwargs: Any) -> None:
    """Exit and clean up the DetectionContext for this task."""
    scope = _active_scopes.pop(task_id, None)
    if scope is not None:
        scope.__exit__(None, None, None)


def setup_celery_detection() -> None:
    """Connect Celery task signals for per-task N+1 detection.

    Safe to call multiple times; subsequent calls are no-ops.

    Raises ``ImportError`` if celery is not installed.
    """
    global _connected  # noqa: PLW0603
    if _connected:
        return

    try:
        from celery.signals import task_postrun, task_prerun
    except ImportError as exc:
        msg = (
            "Celery is required for django-nplus1 Celery integration. "
            "Install it with: pip install django-nplus1[celery]"
        )
        raise ImportError(msg) from exc

    task_prerun.connect(_on_prerun)
    task_postrun.connect(_on_postrun)
    _connected = True


def teardown_celery_detection() -> None:
    """Disconnect Celery task signals. Useful for testing."""
    global _connected  # noqa: PLW0603
    if not _connected:
        return
    try:
        from celery.signals import task_postrun, task_prerun
    except ImportError:
        return
    task_prerun.disconnect(_on_prerun)
    task_postrun.disconnect(_on_postrun)
    _active_scopes.clear()
    _connected = False
