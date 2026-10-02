"""Celery integration: every task runs in its own detection scope, like a request under NPlus1Middleware.

Enable it with ``NPLUS1_CELERY = True``, or call ``setup_celery_detection()``.
"""

import logging
import sys
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


def _on_postrun(
    sender: Any = None,
    task_id: str = "",
    retval: Any = None,
    state: str | None = None,
    **kwargs: Any,
) -> None:
    scopes = _active_scopes.get(task_id)
    if not scopes:
        return
    scope = scopes.pop()
    if not scopes:
        del _active_scopes[task_id]
    if state is None:
        # The task's error is still propagating, as with apply(throw=True).
        error = sys.exception()
    elif state != "SUCCESS" and isinstance(retval, BaseException):
        error = retval
    else:
        error = None
    # Celery has recorded the task's result, so a detection raised here can't change it.
    outer = scope._outer
    try:
        if error is None:
            scope.__exit__(None, None, None)
        else:
            scope.__exit__(type(error), error, error.__traceback__)
    except Exception as exc:
        # Log a detection unless an enclosing scope raises it when it ends.
        if outer is None or not any(enclosing._raised is exc for enclosing in outer._chain()):
            logger.exception("django-nplus1: detection not raised by task %s", task_id)


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
