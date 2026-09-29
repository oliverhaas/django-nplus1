import sys
import sysconfig
from pathlib import Path

import pytest
from testapp.models import Occupation

from django_nplus1 import NPlus1Error


def occupation_users():
    return [occupation.user for occupation in Occupation.objects.all()]


@pytest.fixture
def occupation_whitelisted_in_settings(settings):
    settings.NPLUS1_WHITELIST = [{"model": "testapp.Occupation"}]


@pytest.mark.django_db
def test_nplus1_fixture_raises_on_detection(objects, nplus1):
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        occupation_users()


@pytest.mark.django_db
def test_nplus1_fixture_catches_detection_inside_a_request(objects, client, nplus1):
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        client.get("/lazy_loop/")


@pytest.mark.nplus1(whitelist=[{"model": "testapp.Occupation"}])
@pytest.mark.django_db
def test_marker_whitelist_matches_app_label(objects):
    occupation_users()


@pytest.mark.nplus1(whitelist=[{"model": "testapp.Occupation"}])
@pytest.mark.django_db
def test_marker_whitelist_covers_requests(objects, client):
    response = client.get("/lazy_loop/")
    assert response.status_code == 200
    assert b"alice" in response.content


@pytest.mark.nplus1
@pytest.mark.django_db
def test_marker_applies_settings_whitelist(occupation_whitelisted_in_settings, objects):
    occupation_users()


@pytest.mark.django_db
def test_nplus1_fixture_applies_settings_whitelist(occupation_whitelisted_in_settings, objects, nplus1):
    occupation_users()


@pytest.mark.parametrize("args", [[], ["--nplus1-eager-corpus"]], ids=["plain", "corpus"])
def test_plugin_stays_out_of_projects_without_django(pytester, monkeypatch, args):
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    pytester.makepyfile(
        """
        def test_sum():
            assert 1 + 1 == 2
        """,
    )
    result = pytester.runpytest_subprocess(*args)
    result.assert_outcomes(passed=1)
    assert result.ret == pytest.ExitCode.OK


def test_detection_works_without_contenttypes(django_pytester, monkeypatch):
    django_pytester.makepyfile(
        **{
            "minimal_settings": """
            SECRET_KEY = "minimal"
            INSTALLED_APPS = ["django_nplus1", "shelves"]
            DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
            """,
            "shelves/__init__": "",
            "shelves/models": """
            from django.db import models


            class Shelf(models.Model):
                pass


            class Book(models.Model):
                shelf = models.ForeignKey(Shelf, on_delete=models.CASCADE)
            """,
            "test_shelves": """
            import pytest
            from shelves.models import Book, Shelf


            @pytest.fixture
            def books(db):
                for _ in range(2):
                    Book.objects.create(shelf=Shelf.objects.create())


            @pytest.mark.nplus1
            @pytest.mark.django_db
            def test_shelf_per_book(books):
                [book.shelf for book in Book.objects.all()]
            """,
        },
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "minimal_settings")
    result = django_pytester.runpytest_subprocess()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*NPlus1Error*Book.shelf*"])


def test_marker_skips_test_database_setup(django_pytester):
    django_pytester.makeconftest(
        """
        from django.db.models.signals import post_migrate


        def ensure_groups(sender, **kwargs):
            from django.contrib.auth.models import Group

            for name in ("editors", "viewers"):
                Group.objects.get_or_create(name=name)


        post_migrate.connect(ensure_groups)
        """,
    )
    django_pytester.makepyfile(
        """
        import pytest


        @pytest.mark.nplus1
        @pytest.mark.django_db
        def test_first_database_test():
            pass
        """,
    )
    result = django_pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_marker_checks_only_the_test_body(django_pytester):
    django_pytester.makepyfile(
        """
        import pytest
        from testapp.models import Occupation, User


        def touch_users():
            for occupation in Occupation.objects.all():
                occupation.user


        @pytest.fixture
        def lazy_loads_around_test(db):
            for _ in range(2):
                Occupation.objects.create(user=User.objects.create())
            touch_users()
            yield
            touch_users()


        @pytest.mark.nplus1
        @pytest.mark.django_db
        def test_setup_and_teardown(lazy_loads_around_test):
            pass


        @pytest.mark.nplus1
        @pytest.mark.django_db
        def test_lazy_load_in_body(lazy_loads_around_test):
            touch_users()


        @pytest.mark.nplus1
        @pytest.mark.django_db
        def test_unused_eager_load_in_body(lazy_loads_around_test):
            list(User.objects.select_related("occupation"))
        """,
    )
    result = django_pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=2)


def test_duplicate_detection_skips_connection_setup(django_pytester, monkeypatch):
    django_pytester.makepyfile(
        file_db_settings="""
        from settings.base import *

        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": "db.sqlite3",
                "TEST": {"NAME": "test_db.sqlite3"},
            },
        }
        """,
    )
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "file_db_settings")
    django_pytester.makeconftest(
        """
        from django.db.backends.signals import connection_created


        def look_up_type_oids(connection, **kwargs):
            for type_name in ("hstore", "citext"):
                with connection.cursor() as cursor:
                    cursor.execute("SELECT %s", [type_name])


        connection_created.connect(look_up_type_oids)
        """,
    )
    django_pytester.makepyfile(
        """
        import pytest
        from django.db import connection

        from django_nplus1.profiler import Profiler


        @pytest.mark.django_db(transaction=True)
        def test_reconnect(settings):
            settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
            connection.close()
            with Profiler():
                connection.ensure_connection()
        """,
    )
    result = django_pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


@pytest.mark.parametrize(
    "command",
    [
        pytest.param([Path(sysconfig.get_path("scripts")) / "pytest"], id="console-script"),
        pytest.param([sys.executable, "-m", "pytest"], id="python-m"),
        pytest.param([sys.executable, "-m", "pytest", "-n", "1"], id="xdist"),
    ],
)
def test_duplicate_detection_skips_queries_without_project_caller(django_pytester, command):
    django_pytester.makepyfile(
        """
        import pytest


        @pytest.fixture
        def detect_duplicates(settings):
            settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True


        def test_flush_inside_scope(detect_duplicates, nplus1, transactional_db):
            pass
        """,
    )
    result = django_pytester.run(*command)
    result.assert_outcomes(passed=1)
