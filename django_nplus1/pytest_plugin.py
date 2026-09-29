from collections.abc import Generator  # noqa: TC003 - pluggy evaluates hook annotations
from typing import Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_nplus1 import corpus
from django_nplus1.profiler import Profiler

_CORPUS_ACTIVE = pytest.StashKey[bool]()
_CORPUS_FINDINGS = pytest.StashKey[str]()
_WORKER_OUTPUT_KEY = "nplus1_corpus"


def _setting(name: str, default: Any) -> Any:
    # The plugin also loads for projects that don't configure Django.
    from django.conf import settings

    try:
        return getattr(settings, name, default)
    except ImproperlyConfigured:
        return default


def _whitelist(item: pytest.Item) -> list[dict[str, Any]]:
    marker = item.get_closest_marker("nplus1")
    marker_whitelist = marker.kwargs.get("whitelist") if marker is not None else None
    return [*_setting("NPLUS1_WHITELIST", []), *(marker_whitelist or [])]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--nplus1-eager-corpus",
        action="store_true",
        default=False,
        help="Report eager loads and fields loaded somewhere in the session but never read.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "nplus1(whitelist=None): fail the test on the first N+1 query")
    if config.getoption("--nplus1-eager-corpus") or _setting("NPLUS1_EAGER_CORPUS", False):
        corpus.activate()
        config.stash[_CORPUS_ACTIVE] = True


def pytest_unconfigure(config: pytest.Config) -> None:
    if config.stash.get(_CORPUS_ACTIVE, False):
        corpus.deactivate()


@pytest.fixture
def nplus1(request: pytest.FixtureRequest) -> Generator[Profiler]:
    with Profiler(whitelist=_whitelist(request.node)) as profiler:
        yield profiler


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    if item.get_closest_marker("nplus1") is None:
        return (yield)
    with Profiler(whitelist=_whitelist(item)):
        return (yield)


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node: Any, error: Any) -> None:
    # pytest-xdist hands each worker's config.workeroutput to the controller.
    payload = getattr(node, "workeroutput", {}).get(_WORKER_OUTPUT_KEY)
    if payload is not None:
        corpus.merge(payload)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if not config.stash.get(_CORPUS_ACTIVE, False):
        return
    workeroutput = getattr(config, "workeroutput", None)
    if workeroutput is not None:
        workeroutput[_WORKER_OUTPUT_KEY] = corpus.serialize()
        return
    blocks = [
        corpus.format_findings(label, findings) for label in corpus.TRACKERS if (findings := corpus.report(label))
    ]
    if not blocks:
        return
    config.stash[_CORPUS_FINDINGS] = "\n".join(blocks)
    if session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    findings = config.stash.get(_CORPUS_FINDINGS, None)
    if findings:
        terminalreporter.write_sep("=", "django-nplus1 corpus")
        terminalreporter.write_line(findings)
