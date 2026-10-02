from collections.abc import Generator  # noqa: TC003 - pluggy evaluates hook annotations
from typing import TYPE_CHECKING, Any

import pytest
from django.core.exceptions import ImproperlyConfigured

from django_nplus1 import corpus
from django_nplus1.middleware import whitelist_rules
from django_nplus1.profiler import Profiler

if TYPE_CHECKING:
    from django_nplus1.detect import Rule

_CORPUS_ACTIVE = pytest.StashKey[bool]()
_CORPUS_FINDINGS = pytest.StashKey[str]()
_TEST_ERROR = pytest.StashKey[BaseException]()
_PROFILER = pytest.StashKey[Profiler]()
_WORKER_OUTPUT_KEY = "nplus1_corpus"


def _setting(name: str, default: Any) -> Any:
    # The plugin also loads for projects that don't configure Django.
    from django.conf import settings

    try:
        return getattr(settings, name, default)
    except ImproperlyConfigured:
        return default


def _whitelist(item: pytest.Item) -> list[Rule | dict[str, Any]]:
    marker = item.get_closest_marker("nplus1")
    marker_whitelist = marker.kwargs.get("whitelist") if marker is not None else None
    return [*whitelist_rules(), *(marker_whitelist or [])]


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
    """A ``Profiler`` from setup to teardown. Its block ends with the test, so an error in the setup or the test counts as the block's."""
    profiler = Profiler(whitelist=_whitelist(request.node))
    profiler.__enter__()
    request.node.stash[_PROFILER] = profiler
    try:
        yield profiler
    except BaseException as exc:
        profiler.__exit__(type(exc), exc, exc.__traceback__)
        raise
    error = request.node.stash.get(_TEST_ERROR, None)
    if error is None:
        profiler.__exit__(None, None, None)
    else:
        profiler.__exit__(type(error), error, error.__traceback__)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Generator[None]:
    if item.get_closest_marker("nplus1") is None:
        return (yield)
    with Profiler(whitelist=_whitelist(item)):
        return (yield)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item,
    call: pytest.CallInfo[None],
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Keep the error of the setup or the test for the ``nplus1`` fixture. Runs after pytest's unittest hook sets it for a TestCase."""
    report = yield
    if call.when in ("setup", "call") and call.excinfo is not None:
        item.stash[_TEST_ERROR] = call.excinfo.value
    elif call.when == "teardown" and _TEST_ERROR in item.stash:
        # Fixture teardown has run, so drop the traceback instead of keeping it for the session.
        del item.stash[_TEST_ERROR]
    return report


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    """End the ``nplus1`` fixture's block, so a detection in another fixture's teardown is raised there only."""
    profiler = item.stash.get(_PROFILER, None)
    if profiler is not None:
        del item.stash[_PROFILER]
        profiler._exiting = True


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
