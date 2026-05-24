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
    from django_nplus1 import detect, fields

    original_eager = detect.LISTENERS["eager_load"]
    had_field = "field_load" in detect.LISTENERS
    original_field = detect.LISTENERS.get("field_load")
    original_tracker = corpus._corpus_tracker
    original_field_tracker = corpus._corpus_field_tracker
    yield
    detect.LISTENERS["eager_load"] = original_eager
    if had_field:
        detect.LISTENERS["field_load"] = original_field
    else:
        detect.LISTENERS.pop("field_load", None)
    corpus._corpus_tracker = original_tracker
    corpus._corpus_field_tracker = original_field_tracker
    corpus._corpus_enabled = False
    fields._unpatch_deferred_attribute()


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
    config.workerinput = None  # simulate non-xdist controller session
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


def test_inline_corpus_ignore_marker_suppresses(tmp_path, restore_listeners):
    # Write a source file with the inline marker on the declaration line
    src = tmp_path / "fake_view.py"
    src.write_text(
        "def view():\n    list(User.objects.prefetch_related('hobbies'))  # nplus1: corpus-ignore\n",
        encoding="utf-8",
    )
    corpus.activate()
    site = (str(src), 2, "view")
    corpus.get_tracker().record_load(model=int, field="hobbies", instances=["User:1"], site=site)
    finds = corpus.report()
    assert finds == []


def test_inline_marker_other_label_does_not_suppress_corpus(tmp_path, restore_listeners):
    """The corpus-ignore marker is its own label; `# nplus1: ignore` doesn't match it."""
    src = tmp_path / "fake_view.py"
    src.write_text(
        "def view():\n    list(User.objects.prefetch_related('hobbies'))  # nplus1: ignore\n",
        encoding="utf-8",
    )
    corpus.activate()
    site = (str(src), 2, "view")
    corpus.get_tracker().record_load(model=int, field="hobbies", instances=["User:1"], site=site)
    finds = corpus.report()
    assert len(finds) == 1


def test_whitelist_label_suppresses(settings, restore_listeners):
    settings.NPLUS1_WHITELIST = [
        {"label": "unused_eager_load", "model": "testapp.User", "field": "hobbies"},
    ]
    corpus.activate()
    site = ("/app/views.py", 42, "view")

    # Use a real model class so the whitelist matcher can compare model names
    from testapp.models import User

    corpus.get_tracker().record_load(
        model=User,
        field="hobbies",
        instances=["User:1"],
        site=site,
    )
    finds = corpus.report()
    assert finds == []


def test_whitelist_label_mismatch_does_not_suppress(settings, restore_listeners):
    settings.NPLUS1_WHITELIST = [
        {"label": "n_plus_one", "model": "testapp.User", "field": "hobbies"},  # different label
    ]
    corpus.activate()
    site = ("/app/views.py", 42, "view")

    from testapp.models import User

    corpus.get_tracker().record_load(
        model=User,
        field="hobbies",
        instances=["User:1"],
        site=site,
    )
    finds = corpus.report()
    assert len(finds) == 1


@pytest.mark.django_db
def test_corpus_two_call_sites_tracked_independently(restore_listeners, objects):
    """Two different call sites for the same (model, field): touching one
    does not absolve the other.

    Site A loads only users with hobbies and touches them (used).
    Site B loads only users without hobbies; none are ever touched (unused).
    """
    from testapp.models import User

    # objects fixture: user1 has a hobby, user2 has none
    pks_with = list(User.objects.filter(hobbies__isnull=False).values_list("pk", flat=True))
    pks_without = list(User.objects.filter(hobbies__isnull=True).values_list("pk", flat=True))
    assert pks_with and pks_without, "fixture must provide at least one user with and one without"

    corpus.activate()

    # Site A: load users-with-hobbies and touch all of them (used)
    with corpus.CorpusContext():
        users_a = list(User.objects.prefetch_related("hobbies").filter(pk__in=pks_with))  # site A
        for u in users_a:
            list(u.hobbies.all())

    # Site B: load users-without-hobbies, never touch (unused)
    with corpus.CorpusContext():
        list(User.objects.prefetch_related("hobbies").filter(pk__in=pks_without))  # site B

    finds = [(m.__name__, f, s[1]) for m, f, s in corpus.report()]
    # Exactly one find: site B (users-without-hobbies never accessed)
    assert len(finds) == 1
    model_name, field, _lineno = finds[0]
    assert model_name == "User"
    assert field == "hobbies"


@pytest.mark.django_db
def test_corpus_shared_helper_used_across_sessions(restore_listeners, objects):
    """A prefetch declared once in a helper, exercised across multiple
    sessions on different rows: should not be flagged.

    The helper loads the same set of users each session; different sessions
    touch different rows. Together all loaded instances are touched, so the
    single call site must NOT appear in the report.
    """
    from testapp.models import User

    pks = list(User.objects.values_list("pk", flat=True))
    assert len(pks) >= 2, "fixture must provide at least two users"

    def shared_helper():
        return list(User.objects.prefetch_related("hobbies").all())  # shared site

    corpus.activate()

    # Session 1: touch the first user's hobbies
    with corpus.CorpusContext():
        users = shared_helper()
        list(users[0].hobbies.all())

    # Session 2: touch the second user's hobbies
    with corpus.CorpusContext():
        users = shared_helper()
        list(users[1].hobbies.all())

    finds = corpus.report()
    assert finds == [], f"Expected no finds, got: {finds}"


# ---------------------------------------------------------------------------
# pytester integration scenarios
# ---------------------------------------------------------------------------

pytest_plugins = ["pytester"]

import os
from pathlib import Path

_OUTER_TESTS_DIR = Path(__file__).parent.resolve()


def _setup_inner_env(monkeypatch):
    """Push the outer tests/ dir onto PYTHONPATH and set DJANGO_SETTINGS_MODULE."""
    existing = os.environ.get("PYTHONPATH", "")
    new_path = os.pathsep.join([str(_OUTER_TESTS_DIR), existing]) if existing else str(_OUTER_TESTS_DIR)
    monkeypatch.setenv("PYTHONPATH", new_path)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "settings.base")


def test_sessionfinish_reports_unused_field_load(pytester, monkeypatch):
    """corpus.field_report() finds should appear in output and make exit non-zero."""
    _setup_inner_env(monkeypatch)
    pytester.makepyfile(
        test_field_unused="""
        import pytest
        from django_nplus1.scope import DetectionContext
        from testapp.models import User

        @pytest.mark.django_db
        def test_unused_field():
            user = User.objects.create(name="Alice")
            with DetectionContext():
                list(User.objects.all())  # loads 'name'; never read -> unused_field_load
        """,
    )
    result = pytester.runpytest_subprocess("--nplus1-eager-corpus")
    assert result.ret != 0, f"expected non-zero exit, got {result.ret}\nstdout:\n{result.stdout.str()}"
    result.stdout.fnmatch_lines(["*unused_field_load*"])


def test_sessionfinish_field_exclude_suppresses_report(pytester, monkeypatch):
    """NPLUS1_FIELD_EXCLUDE suppresses field finds; suite exits 0."""
    _setup_inner_env(monkeypatch)
    pytester.makeconftest(
        """
        import django
        from django.conf import settings as django_settings

        def pytest_configure(config):
            django_settings.NPLUS1_FIELD_EXCLUDE = ["testapp.*"]
        """,
    )
    pytester.makepyfile(
        test_field_excluded="""
        import pytest
        from django_nplus1.scope import DetectionContext
        from testapp.models import User

        @pytest.mark.django_db
        def test_excluded_field():
            user = User.objects.create(name="Alice")
            with DetectionContext():
                list(User.objects.all())  # loads 'name'; excluded -> no find
        """,
    )
    result = pytester.runpytest_subprocess("--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"
    assert "unused_field_load" not in result.stdout.str()
