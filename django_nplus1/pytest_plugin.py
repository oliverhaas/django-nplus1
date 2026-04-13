from typing import TYPE_CHECKING, Any

import pytest

from django_nplus1.profiler import Profiler

if TYPE_CHECKING:
    from collections.abc import Generator


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "nplus1: mark test to detect N+1 queries")


@pytest.fixture
def nplus1() -> Generator[Profiler]:
    with Profiler() as p:
        yield p


@pytest.fixture(autouse=True)
def auto_nplus1(request: pytest.FixtureRequest) -> Generator[None]:
    marker = request.node.get_closest_marker("nplus1")
    if marker:
        with Profiler(whitelist=marker.kwargs.get("whitelist")):
            yield
    else:
        yield
