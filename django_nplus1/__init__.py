from importlib.metadata import PackageNotFoundError, version

from django_nplus1.middleware import NPlusOneMiddleware
from django_nplus1.profiler import Profiler

try:
    __version__ = version("django-nplus1")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["NPlusOneMiddleware", "Profiler", "__version__"]
