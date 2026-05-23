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
        from testapp.models import User

        @pytest.mark.django_db
        def test_a():
            User.objects.create()
            User.objects.create()
            list(User.objects.prefetch_related('hobbies').all())  # unused

        @pytest.mark.django_db
        def test_b():
            User.objects.create()
            User.objects.create()
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
        from testapp.models import User, Hobby

        @pytest.mark.django_db
        def test_a():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            users = list(User.objects.prefetch_related('hobbies').all())
            for u in users:
                list(u.hobbies.all())  # touch

        @pytest.mark.django_db
        def test_b():
            user = User.objects.create()
            hobby = Hobby.objects.create()
            user.hobbies.add(hobby)
            users = list(User.objects.prefetch_related('hobbies').all())
            for u in users:
                list(u.hobbies.all())  # touch
        """,
    )
    result = pytester.runpytest_subprocess("-n", "2", "--nplus1-eager-corpus")
    assert result.ret == 0, f"expected exit 0, got {result.ret}\nstdout:\n{result.stdout.str()}"
