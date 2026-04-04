from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import types

_PACKAGE_DIR = str(Path(__file__).resolve().parent)


def _is_internal_frame(filename: str) -> bool:
    """Check if a frame belongs to site-packages or our own package."""
    return "site-packages" in filename or filename.startswith(_PACKAGE_DIR)


def get_caller() -> tuple[str, int, str]:
    """
    Walk the call stack and return (filename, lineno, funcname) of the
    first frame outside site-packages and django_nplus1.
    """
    frame: types.FrameType | None = sys._getframe(1)
    try:
        while frame is not None:
            fn = frame.f_code.co_filename
            if not _is_internal_frame(fn):
                return (fn, frame.f_lineno, frame.f_code.co_name)
            frame = frame.f_back
    finally:
        del frame
    return ("<unknown>", 0, "<unknown>")
