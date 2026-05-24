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
    marker = request.node.get_closest_marker("nplus1")
    if marker:
        with Profiler(whitelist=marker.kwargs.get("whitelist")):
            yield
    else:
        yield


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    if not _corpus_enabled(session.config):
        return
    workerinput = getattr(session.config, "workerinput", None)
    if workerinput is not None:
        corpus.dump_worker(workerinput["workerid"])
        return
    corpus.merge_worker_dumps()
    eager_finds = corpus.report()
    field_finds = corpus.field_report()
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    text_blocks = []
    if eager_finds:
        text_blocks.append(corpus.format_finds(eager_finds))
    if field_finds:
        text_blocks.append(corpus.format_field_finds(field_finds))
    if not text_blocks:
        return
    text = "\n".join(text_blocks)
    if terminal is not None:
        terminal.write_line(text)
    else:
        print(text)  # noqa: T201 - fallback when terminalreporter unavailable
    if session.exitstatus == 0:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
