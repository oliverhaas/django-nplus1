import os
import site
import sys
import sysconfig
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any

from asgiref.sync import SyncToAsync
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed

from django_nplus1 import conf

if TYPE_CHECKING:
    import types
    from collections.abc import Iterator

    from django.db.models import Model

CallSite = tuple[str, int, str]
CallPath = tuple[tuple[str, int], ...]

_PACKAGE_DIR = str(Path(__file__).parent)
# "scripts" holds console-script launchers such as bin/pytest. Frame filenames can
# carry either the symlinked or the resolved path, so both spellings are listed.
_INTERNAL_DIRS = tuple(
    f"{spelling}{os.sep}"
    for directory in {
        _PACKAGE_DIR,
        *site.getsitepackages(),
        *(sysconfig.get_path(key) for key in ("stdlib", "platstdlib", "purelib", "platlib", "scripts")),
    }
    for spelling in {str(Path(directory)), os.path.realpath(directory)}
)

# The frames of the coroutine that handed a call to a worker thread through
# sync_to_async(), as aget() does. The worker thread's own stack doesn't lead back to it.
async_caller_frames: ContextVar[tuple[types.FrameType, ...]] = ContextVar("nplus1_async_caller_frames", default=())

# The frame that runs a sync_to_async() call in the worker thread.
_THREAD_HANDLER_CODE = SyncToAsync.thread_handler.__code__

# NPLUS1_PROJECT_PACKAGES as (module names, "name." prefixes), read on first use.
_project_packages: tuple[frozenset[str], tuple[str, ...]] | None = None


def _read_project_packages() -> tuple[frozenset[str], tuple[str, ...]]:
    global _project_packages  # noqa: PLW0603
    if _project_packages is None:
        try:
            names = conf.project_packages(settings)
        except ImproperlyConfigured:
            # Settings that aren't configured yet, or an invalid value, which scopes
            # raise for when they start.
            return frozenset(), ()
        _project_packages = (frozenset(names), tuple(f"{name}." for name in names))
    return _project_packages


def _reset_project_packages(*, setting: str, **kwargs: Any) -> None:
    global _project_packages  # noqa: PLW0603
    if setting == "NPLUS1_PROJECT_PACKAGES":
        _project_packages = None


setting_changed.connect(_reset_project_packages)


def _is_internal_frame(frame: types.FrameType) -> bool:
    """Check if a frame belongs to the interpreter, installed packages, or our own package."""
    filename = frame.f_code.co_filename
    if filename.startswith("<"):
        # Frozen stdlib modules, and `python -c` code such as the xdist worker bootstrap.
        return filename.startswith("<frozen ") or (
            filename == "<string>" and frame.f_globals.get("__name__") == "__main__"
        )
    if "site-packages" not in filename and not filename.startswith(_INTERNAL_DIRS):
        return False
    # The project's own packages count as its code wherever they are installed.
    names, prefixes = _read_project_packages()
    if not names:
        return True
    module = frame.f_globals.get("__name__", "")
    return module not in names and not module.startswith(prefixes)


def _frames(frame: types.FrameType | None) -> Iterator[types.FrameType]:
    """Walk the stack outward from ``frame``. In a sync_to_async() worker thread, continue with the awaiting coroutines."""
    while frame is not None:
        if frame.f_code is _THREAD_HANDLER_CODE and (caller_frames := async_caller_frames.get()):
            yield from caller_frames
            return
        yield frame
        frame = frame.f_back


def get_caller() -> CallSite | None:
    """
    Walk the call stack and return (filename, lineno, funcname) of the
    first project frame, or None when every frame is internal.
    """
    for frame in _frames(sys._getframe(1)):
        if not _is_internal_frame(frame):
            return (frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)
    return None


def get_call_path() -> tuple[CallSite, CallPath] | None:
    """
    Return the call site of the first project frame and the (filename, lineno) of
    each call that leads from it to the caller, or None when every frame is internal.
    """
    path = []
    for frame in _frames(sys._getframe(1)):
        # Lines, not instruction offsets: the coroutines awaiting a sync_to_async()
        # call can still be suspending in their own thread.
        lineno = frame.f_lineno
        path.append((frame.f_code.co_filename, lineno))
        if not _is_internal_frame(frame):
            return (frame.f_code.co_filename, lineno, frame.f_code.co_name), tuple(path)
    return None


def get_stack() -> list[CallSite]:
    """
    Return the current call stack as (filename, lineno, funcname) tuples,
    excluding internal frames.
    """
    return [
        (frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)
        for frame in _frames(sys._getframe(1))
        if not _is_internal_frame(frame)
    ]


def to_key(instance: Model) -> str:
    """Identify a model instance as ``app_label.Model:pk``.

    Reads the primary key from ``__dict__`` so no descriptor (and no signal) runs.
    Unsaved instances fall back to their object id.
    """
    meta = instance._meta
    values = [instance.__dict__.get(field.attname) for field in meta.pk_fields]
    if any(value is None for value in values):
        return f"{meta.label}:#{id(instance)}"
    return f"{meta.label}:{values[0] if len(values) == 1 else tuple(values)}"
