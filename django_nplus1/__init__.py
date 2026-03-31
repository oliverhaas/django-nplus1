from importlib.metadata import PackageNotFoundError, version

from django_nplus1.middleware import NPlus1Middleware
from django_nplus1.profiler import Profiler

try:
    __version__ = version("django-nplus1")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

# Backwards compatibility
NPlusOneMiddleware = NPlus1Middleware

__all__ = ["NPlus1Middleware", "NPlusOneMiddleware", "Profiler", "__version__"]
