import os
from pathlib import Path

import pytest

pytest.importorskip("xdist", reason="pytest-xdist not installed")

pytest_plugins = ["pytester"]

# Path to the outer project's tests/ directory (where testapp + settings live)
_OUTER_TESTS_DIR = Path(__file__).parent.resolve()


def _setup_inner_env(monkeypatch):
    """Push the outer tests/ dir onto PYTHONPATH and set DJANGO_SETTINGS_MODULE
    so the inner pytester subprocess can import testapp + settings.base.
    """
    existing = os.environ.get("PYTHONPATH", "")
    new_path = os.pathsep.join([str(_OUTER_TESTS_DIR), existing]) if existing else str(_OUTER_TESTS_DIR)
    monkeypatch.setenv("PYTHONPATH", new_path)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "settings.base")


def test_xdist_reports_unused_prefetch(pytester, monkeypatch):
    _setup_inner_env(monkeypatch)
    pytester.makepyfile(
        test_unused="""
        import pytest
        from django_nplus1.scope import DetectionContext
        from testapp.models import User

        @pytest.mark.django_db
        def test_a():
            User.objects.create()
            User.objects.create()
            with DetectionContext():
                list(User.objects.prefetch_related('hobbies').all())  # unused

        @pytest.mark.django_db
        def test_b():
            User.objects.create()
            User.objects.create()
            with DetectionContext():
                list(User.objects.prefetch_related('hobbies').all())  # unused
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 1, f"expected exit 1, got {result.ret}\nstdout:\n{result.stdout.str()}"
    result.stdout.fnmatch_lines(
        [
            "*corpus-wide unused_eager_load*",
            "*User.hobbies*",
        ],
    )


def test_xdist_used_prefetch_not_flagged(pytester, monkeypatch):
    _setup_inner_env(monkeypatch)
    pytester.makepyfile(
        test_used="""
        import pytest
        from django_nplus1.scope import DetectionContext
        from testapp.models import User, Hobby

        @pytest.mark.django_db
        def test_a():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            with DetectionContext():
                users = list(User.objects.prefetch_related('hobbies').all())
                for u in users:
                    _ = u.name  # touch concrete field
                    list(u.hobbies.all())  # touch relation

        @pytest.mark.django_db
        def test_b():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            with DetectionContext():
                users = list(User.objects.prefetch_related('hobbies').all())
                for u in users:
                    _ = u.name  # touch concrete field
                    list(u.hobbies.all())  # touch relation
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"


def test_xdist_one_worker_touches_one_does_not(pytester, monkeypatch):
    """Asymmetric case: one worker touches the prefetched relation, the
    other doesn't. The shared prefetch declaration must NOT be flagged,
    because some test in the suite did touch it.

    Note: both tests read ``u.name`` to silence the field-load detector
    (the new ``unused_field_load`` find would otherwise fail the suite).
    Relation-touch coverage is unchanged: only ``test_a`` calls
    ``u.hobbies.all()``.
    """
    _setup_inner_env(monkeypatch)
    pytester.makepyfile(
        test_asymmetric="""
        import pytest
        from django_nplus1.scope import DetectionContext
        from testapp.models import User, Hobby

        def helper():
            return list(User.objects.prefetch_related('hobbies').all())  # SHARED SITE

        @pytest.mark.django_db
        def test_a():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            with DetectionContext():
                users = helper()
                for u in users:
                    _ = u.name  # touch concrete field
                    list(u.hobbies.all())  # touch relation

        @pytest.mark.django_db
        def test_b():
            User.objects.create()
            User.objects.create()
            with DetectionContext():
                users = helper()  # no relation touch, but read name
                for u in users:
                    _ = u.name  # touch concrete field to avoid field find
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"


def test_xdist_uninstrumented_tests_produce_no_finds(pytester, monkeypatch):
    """Tests that run pure ORM code without any DetectionContext (no
    middleware, no Celery, no explicit wrap) must not contribute to the
    corpus tracker even when an unused prefetch is plainly visible.
    """
    _setup_inner_env(monkeypatch)
    pytester.makepyfile(
        test_uninstrumented="""
        import pytest
        from testapp.models import User

        @pytest.mark.django_db
        def test_a():
            User.objects.create()
            list(User.objects.prefetch_related('hobbies').all())  # uninstrumented

        @pytest.mark.django_db
        def test_b():
            User.objects.create()
            list(User.objects.prefetch_related('hobbies').all())  # uninstrumented
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"
    assert "corpus-wide unused_eager_load" not in result.stdout.str()


def test_dump_worker_and_merge_round_trip_field_tracker(tmp_path, monkeypatch):
    import json

    from django_nplus1 import corpus

    monkeypatch.chdir(tmp_path)
    site = ("/app/views.py", 1, "fn")

    eager = corpus.CorpusEagerTracker()
    eager.record_load(int, "hobbies", ["User:1"], site)
    field = corpus.CorpusFieldTracker()
    field.record_load(int, "bio", ["User:1"], site)
    corpus._corpus_tracker = eager
    corpus._corpus_field_tracker = field
    corpus.dump_worker("gw0")

    dump_path = tmp_path / ".nplus1-eager-corpus.gw0.json"
    payload = json.loads(dump_path.read_text())
    assert "eager" in payload
    assert "field" in payload
    assert payload["field"]["data"][0]["field"] == "bio"

    eager2 = corpus.CorpusEagerTracker()
    field2 = corpus.CorpusFieldTracker()
    corpus._corpus_tracker = eager2
    corpus._corpus_field_tracker = field2
    corpus.merge_worker_dumps()
    assert eager2.unused() == [(int, "hobbies", site)]
    assert field2.unused() == [(int, "bio", site)]
    assert not dump_path.exists()


def test_merge_tolerates_legacy_eager_only_payload(tmp_path, monkeypatch):
    import json

    from django_nplus1 import corpus

    monkeypatch.chdir(tmp_path)
    site = ("/app/views.py", 1, "fn")
    legacy = {
        "data": [{"model": "builtins.int", "field": "hobbies", "site": list(site), "instances": ["U:1"]}],
        "touched": [],
    }
    (tmp_path / ".nplus1-eager-corpus.gw0.json").write_text(json.dumps(legacy))

    eager = corpus.CorpusEagerTracker()
    field = corpus.CorpusFieldTracker()
    corpus._corpus_tracker = eager
    corpus._corpus_field_tracker = field
    corpus.merge_worker_dumps()
    assert eager.unused() == [(int, "hobbies", site)]
    assert field.unused() == []
