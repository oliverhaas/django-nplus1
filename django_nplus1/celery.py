"""Celery integration: every task runs in its own detection scope, like a request under NPlus1Middleware.

Enable it with ``NPLUS1_CELERY = True``, or call ``setup_celery_detection()``.
"""

import logging
import threading
from collections import defaultdict
from typing import Any

from django_nplus1.middleware import load_config
from django_nplus1.scope import DetectionContext

logger = logging.getLogger("django_nplus1")

# Task id -> scopes of its runs in flight. An eager self.replace() runs the replacement
# under the same id while the replaced task is still running.
_active_scopes: defaultdict[str, list[DetectionContext]] = defaultdict(list)

_connected = False
_connect_lock = threading.Lock()


def _on_prerun(sender: Any = None, task_id: str = "", **kwargs: Any) -> None:
    try:
        nots, whitelist = load_config()
        scope = DetectionContext(notifiers=nots, whitelist=whitelist)
        scope.__enter__()
    except Exception:
        logger.exception("django-nplus1: detection not started for task %s", task_id)
        return
    _active_scopes[task_id].append(scope)


def _on_postrun(sender: Any = None, task_id: str = "", **kwargs: Any) -> None:
    scopes = _active_scopes.get(task_id)
    if not scopes:
        return
    scope = scopes.pop()
    if not scopes:
        del _active_scopes[task_id]
    # The task has finished, so a detection raised here can't fail it any more.
    try:
        scope.__exit__(None, None, None)
    except Exception:
        logger.exception("django-nplus1: detection at the end of task %s raised", task_id)


def setup_celery_detection() -> None:
    """Connect the Celery task signals. Later calls do nothing.

    Raises ``ImportError`` without Celery, and ``ImproperlyConfigured`` or ``NPlus1Error``
    for invalid ``NPLUS1_*`` settings.
    """
    global _connected  # noqa: PLW0603
    with _connect_lock:
        if _connected:
            return
        try:
            from celery.signals import task_postrun, task_prerun  # type: ignore[import-untyped]
        except ImportError as exc:
            msg = (
                "Celery is required for django-nplus1 Celery integration. "
                "Install it with: pip install django-nplus1[celery]"
            )
            raise ImportError(msg) from exc
        load_config()
        task_prerun.connect(_on_prerun)
        task_postrun.connect(_on_postrun)
        _connected = True


def teardown_celery_detection() -> None:
    """Disconnect the Celery task signals.

    Call it only while no task runs. Scopes of tasks in flight are dropped without ending them.
    """
    global _connected  # noqa: PLW0603
    with _connect_lock:
        if not _connected:
            return
        from celery.signals import task_postrun, task_prerun

        task_prerun.disconnect(_on_prerun)
        task_postrun.disconnect(_on_postrun)
        _active_scopes.clear()
        _connected = False
