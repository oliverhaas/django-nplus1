import pytest

UNUSED_PREFETCH = """
import pytest
from testapp.models import User

from django_nplus1 import DetectionContext


@pytest.mark.django_db
def test_prefetch():
    User.objects.create(name="alice")
    with DetectionContext():
        list(User.objects.prefetch_related("hobbies"))
"""

READ_EVERYWHERE = """
import pytest
from testapp.models import User

from django_nplus1 import DetectionContext


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["alice", "bob"])
def test_prefetch(name):
    User.objects.create(name=name)
    with DetectionContext():
        for user in User.objects.prefetch_related("hobbies"):
            user.name
            list(user.hobbies.all())
"""

READ_BY_ONE_TEST = """
import pytest
from testapp.models import User

from django_nplus1 import DetectionContext


def users_with_hobbies():
    return list(User.objects.prefetch_related("hobbies"))


@pytest.mark.django_db
def test_reads_hobbies():
    User.objects.create(name="alice")
    with DetectionContext():
        for user in users_with_hobbies():
            user.name
            list(user.hobbies.all())


@pytest.mark.django_db
def test_reads_names():
    User.objects.create(name="bob")
    with DetectionContext():
        for user in users_with_hobbies():
            user.name
"""

OUTSIDE_SCOPES = """
import pytest
from testapp.models import User


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["alice", "bob"])
def test_prefetch(name):
    User.objects.create(name=name)
    list(User.objects.prefetch_related("hobbies"))
"""


@pytest.mark.parametrize("args", [[], ["-n", "2"]], ids=["serial", "xdist"])
def test_unused_loads_fail_the_session(django_pytester, args):
    django_pytester.makepyfile(UNUSED_PREFETCH)
    result = django_pytester.runpytest_subprocess("-q", "--nplus1-eager-corpus", *args)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(
        [
            "*= django-nplus1 corpus =*",
            "django-nplus1: corpus-wide unused_eager_load *",
            "  User.hobbies * in test_prefetch",
            "django-nplus1: corpus-wide unused_field_load *",
            "  User.name * in test_prefetch",
        ],
    )
    assert sorted(path.name for path in django_pytester.path.iterdir() if path.name.startswith(".nplus1")) == []


def test_setting_enables_corpus_mode(django_pytester, monkeypatch):
    django_pytester.makepyfile(corpus_settings="from settings.base import *\n\nNPLUS1_EAGER_CORPUS = True\n")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "corpus_settings")
    django_pytester.makepyfile(UNUSED_PREFETCH)
    result = django_pytester.runpytest_subprocess()
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["django-nplus1: corpus-wide unused_eager_load *"])


@pytest.mark.parametrize(
    "module",
    [READ_EVERYWHERE, READ_BY_ONE_TEST, OUTSIDE_SCOPES],
    ids=["read-everywhere", "read-by-one-test", "outside-scopes"],
)
@pytest.mark.parametrize("args", [[], ["-n", "2"]], ids=["serial", "xdist"])
def test_session_without_unused_loads_passes(django_pytester, module, args):
    django_pytester.makepyfile(module)
    result = django_pytester.runpytest_subprocess("--nplus1-eager-corpus", *args)
    assert result.ret == pytest.ExitCode.OK
    assert "django-nplus1 corpus" not in result.stdout.str()


def test_interrupted_session_keeps_its_exit_code(django_pytester):
    django_pytester.makepyfile(
        UNUSED_PREFETCH
        + """

def test_stop():
    pytest.exit("stopped")
""",
    )
    result = django_pytester.runpytest_subprocess("--nplus1-eager-corpus")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.stdout.fnmatch_lines(["django-nplus1: corpus-wide unused_eager_load *"])
