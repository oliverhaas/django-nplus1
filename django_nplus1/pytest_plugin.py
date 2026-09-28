from collections.abc import Generator  # noqa: TC003 - pluggy evaluates hook annotations
from typing import Any

import pytest

from django_nplus1 import corpus
from django_nplus1.profiler import Profiler


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
    from django.conf import settings

    with Profiler(whitelist=getattr(settings, "NPLUS1_WHITELIST", [])) as p:
        yield p


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    marker = item.get_closest_marker("nplus1")
    if marker is None:
        return (yield)
    from django.conf import settings

    whitelist = [*getattr(settings, "NPLUS1_WHITELIST", []), *(marker.kwargs.get("whitelist") or [])]
    with Profiler(whitelist=whitelist):
        return (yield)


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
