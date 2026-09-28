import os
import site
import sys
import sysconfig
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

_PACKAGE_DIR = str(Path(__file__).resolve().parent)
# "scripts" holds console-script launchers such as bin/pytest.
_INTERNAL_DIRS = tuple(
    f"{Path(directory)}{os.sep}"
    for directory in {
        _PACKAGE_DIR,
        *site.getsitepackages(),
        *(sysconfig.get_path(key) for key in ("stdlib", "platstdlib", "purelib", "platlib", "scripts")),
    }
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


def get_caller() -> tuple[str, int, str] | None:
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


def get_stack() -> list[tuple[str, int, str]]:
    """
    Return the current call stack as (filename, lineno, funcname) tuples,
    excluding internal frames.
    """
    result: list[tuple[str, int, str]] = []
    frame: types.FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            if not _is_internal_frame(frame):
                result.append((frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name))
            frame = frame.f_back
    finally:
        del frame
    return result
