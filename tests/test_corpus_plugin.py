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

    original = detect.LISTENERS["eager_load"]
    yield
    detect.LISTENERS["eager_load"] = original
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
