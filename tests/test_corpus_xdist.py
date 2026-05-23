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
                    list(u.hobbies.all())  # touch

        @pytest.mark.django_db
        def test_b():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            with DetectionContext():
                users = list(User.objects.prefetch_related('hobbies').all())
                for u in users:
                    list(u.hobbies.all())  # touch
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"


def test_xdist_one_worker_touches_one_does_not(pytester, monkeypatch):
    """Asymmetric case: one worker touches the prefetched relation, the
    other doesn't. The shared prefetch declaration must NOT be flagged,
    because some test in the suite did touch it.
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
                    list(u.hobbies.all())  # touch

        @pytest.mark.django_db
        def test_b():
            User.objects.create()
            User.objects.create()
            with DetectionContext():
                helper()  # no touch
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
