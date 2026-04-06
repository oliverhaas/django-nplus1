from importlib.metadata import PackageNotFoundError, version

from django_nplus1.detect import nplus1_allow
from django_nplus1.middleware import NPlus1Middleware
from django_nplus1.profiler import Profiler
from django_nplus1.signals import nplus1_detected

try:
    __version__ = version("django-nplus1")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["NPlus1Middleware", "Profiler", "__version__", "nplus1_allow", "nplus1_detected"]
