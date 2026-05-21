from typing import TYPE_CHECKING, Any

import pytest

from django_nplus1 import corpus
from django_nplus1.profiler import Profiler

if TYPE_CHECKING:
    from collections.abc import Generator


def _corpus_enabled(config: Any) -> bool:
    if config.getoption("--nplus1-eager-corpus", default=False):
        return True
    try:
        from django.conf import settings
    except ImportError, AttributeError:
        return False
    return bool(getattr(settings, "NPLUS1_EAGER_CORPUS", False))


def pytest_addoption(parser: Any) -> None:
    parser.addoption(
        "--nplus1-eager-corpus",
        action="store_true",
        default=False,
        help="Accumulate unused_eager_load detections across the whole session.",
    )


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "nplus1: mark test to detect N+1 queries")
    if _corpus_enabled(config):
        corpus.activate()


@pytest.fixture
def nplus1() -> Generator[Profiler]:
    with Profiler() as p:
        yield p


@pytest.fixture(autouse=True)
def auto_nplus1(request: pytest.FixtureRequest) -> Generator[None]:
    if _corpus_enabled(request.config):
        with corpus.CorpusContext():
            yield
        return
    marker = request.node.get_closest_marker("nplus1")
    if marker:
        with Profiler(whitelist=marker.kwargs.get("whitelist")):
            yield
    else:
        yield
