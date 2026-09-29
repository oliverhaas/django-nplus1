import os
import site
import sys
import sysconfig
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

    from django.db.models import Model

CallSite = tuple[str, int, str]

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


def _is_internal_frame(frame: types.FrameType) -> bool:
    """Check if a frame belongs to the interpreter, installed packages, or our own package."""
    filename = frame.f_code.co_filename
    if filename.startswith("<"):
        # Frozen stdlib modules, and `python -c` code such as the xdist worker bootstrap.
        return filename.startswith("<frozen ") or (
            filename == "<string>" and frame.f_globals.get("__name__") == "__main__"
        )
    return "site-packages" in filename or filename.startswith(_INTERNAL_DIRS)


def get_caller() -> CallSite | None:
    """
    Walk the call stack and return (filename, lineno, funcname) of the
    first project frame, or None when every frame is internal.
    """
    frame: types.FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            if not _is_internal_frame(frame):
                return (frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)
            frame = frame.f_back
    finally:
        del frame
    return None


def get_stack() -> list[CallSite]:
    """
    Return the current call stack as (filename, lineno, funcname) tuples,
    excluding internal frames.
    """
    result: list[CallSite] = []
    frame: types.FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            if not _is_internal_frame(frame):
                result.append((frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name))
            frame = frame.f_back
    finally:
        del frame
    return result


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
