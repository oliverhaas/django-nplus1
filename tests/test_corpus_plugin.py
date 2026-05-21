from unittest import mock

import pytest

from django_nplus1 import corpus
from django_nplus1.pytest_plugin import _corpus_enabled


def _config(flag_value: bool = False) -> mock.Mock:
    """Build a fake pytest config with the corpus flag set or unset."""
    config = mock.Mock()
    config.getoption.return_value = flag_value
    return config


def test_corpus_enabled_via_cli_flag():
    config = _config(flag_value=True)
    assert _corpus_enabled(config) is True


def test_corpus_enabled_via_django_setting(settings):
    settings.NPLUS1_EAGER_CORPUS = True
    config = _config(flag_value=False)
    assert _corpus_enabled(config) is True


def test_corpus_disabled_when_neither_set(settings):
    settings.NPLUS1_EAGER_CORPUS = False
    config = _config(flag_value=False)
    assert _corpus_enabled(config) is False


@pytest.fixture
def restore_listeners():
    from django_nplus1 import detect

    original_listener = detect.LISTENERS["eager_load"]
    original_tracker = corpus._corpus_tracker
    yield
    detect.LISTENERS["eager_load"] = original_listener
    corpus._corpus_tracker = original_tracker
    corpus._corpus_enabled = False


def test_pytest_configure_activates_corpus(restore_listeners):
    from django_nplus1 import detect
    from django_nplus1.pytest_plugin import pytest_configure

    config = _config(flag_value=True)
    pytest_configure(config)
    assert detect.LISTENERS["eager_load"] is corpus.CorpusEagerListener
    assert corpus.is_enabled() is True


def test_pytest_configure_noop_when_disabled(restore_listeners):
    from django_nplus1 import detect
    from django_nplus1.pytest_plugin import pytest_configure

    config = _config(flag_value=False)
    pytest_configure(config)
    # Listener swap should NOT have happened
    assert detect.LISTENERS["eager_load"] is not corpus.CorpusEagerListener


def _session(corpus_on: bool = True, exit_status: int = 0):
    config = mock.Mock()
    config.getoption.return_value = corpus_on
    terminal = mock.Mock()
    config.pluginmanager.get_plugin.return_value = terminal
    session = mock.Mock()
    session.config = config
    session.exitstatus = exit_status
    return session, terminal


def test_sessionfinish_reports_and_sets_exit_when_finds(restore_listeners):
    from django_nplus1.pytest_plugin import pytest_sessionfinish

    # Populate the tracker with an unused entry
    corpus.activate()
    site = ("/app/views.py", 42, "view_fn")
    corpus.get_tracker().record_load(model=int, field="hobbies", instances=["User:1"], site=site)

    session, terminal = _session(corpus_on=True, exit_status=0)
    pytest_sessionfinish(session, exitstatus=0)

    assert terminal.write_line.called
    text = terminal.write_line.call_args[0][0]
    assert "unused_eager_load" in text
    assert "int.hobbies" in text
    assert "/app/views.py:42" in text
    assert session.exitstatus == 1


def test_sessionfinish_no_finds_does_not_change_exit(restore_listeners):
    from django_nplus1.pytest_plugin import pytest_sessionfinish

    corpus.activate()
    session, terminal = _session(corpus_on=True, exit_status=0)
    pytest_sessionfinish(session, exitstatus=0)

    assert not terminal.write_line.called
    assert session.exitstatus == 0


def test_sessionfinish_noop_when_corpus_disabled():
    from django_nplus1.pytest_plugin import pytest_sessionfinish

    session, terminal = _session(corpus_on=False, exit_status=0)
    # Even if there's a tracker, do nothing when corpus is off
    pytest_sessionfinish(session, exitstatus=0)
    assert not terminal.write_line.called
    assert session.exitstatus == 0


def test_sessionfinish_preserves_failed_exit_status(restore_listeners):
    """If the suite already failed (exit_status != 0), don't overwrite it."""
    from django_nplus1.pytest_plugin import pytest_sessionfinish

    corpus.activate()
    site = ("/app/views.py", 42, "view_fn")
    corpus.get_tracker().record_load(model=int, field="hobbies", instances=["User:1"], site=site)

    session, terminal = _session(corpus_on=True, exit_status=2)
    pytest_sessionfinish(session, exitstatus=2)
    # Report still happens
    assert terminal.write_line.called
    # But exit status stays at 2 (preserve test failure code)
    assert session.exitstatus == 2
