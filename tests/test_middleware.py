import logging
import sys
from pathlib import Path

import pytest
from asgiref.sync import async_to_sync
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from testapp.models import Occupation

from django_nplus1 import NPlus1Error, NPlus1Middleware, middleware

pytestmark = pytest.mark.django_db


def build_middleware():
    return NPlus1Middleware(lambda request: HttpResponse())


@pytest.fixture
def unvalidated_whitelist(monkeypatch):
    monkeypatch.setattr(middleware, "_validated_whitelist", None)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, [("django_nplus1", logging.WARNING)]),
        ({"NPLUS1_LOG_LEVEL": logging.ERROR}, [("django_nplus1", logging.ERROR)]),
        ({"NPLUS1_LOG_LEVEL": "error"}, [("django_nplus1", logging.ERROR)]),
        ({"NPLUS1_LOGGER": "project.queries"}, [("project.queries", logging.WARNING)]),
        ({"NPLUS1_LOGGER": logging.getLogger("project.queries")}, [("project.queries", logging.WARNING)]),
        ({"NPLUS1_LOG": False}, []),
    ],
    ids=["default", "level-number", "level-name", "logger-name", "logger", "disabled"],
)
def test_detection_is_logged(objects, client, caplog, settings, overrides, expected):
    for name, value in overrides.items():
        setattr(settings, name, value)
    response = client.get("/lazy_loop/")
    assert response.status_code == 200
    assert [(r.name, r.levelno) for r in caplog.records if "Occupation.user" in r.getMessage()] == expected


@pytest.mark.parametrize("show_all_callers", [False, True])
def test_warning_points_at_the_loading_line(objects, client, settings, show_all_callers):
    settings.NPLUS1_WARN = True
    settings.NPLUS1_SHOW_ALL_CALLERS = show_all_callers
    with pytest.warns(UserWarning, match="Occupation.user") as record:
        client.get("/lazy_loop/")
    assert [Path(w.filename).name for w in record if "Occupation.user" in str(w.message)] == ["views.py"]


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({}, NPlus1Error),
        ({"NPLUS1_ERROR": LookupError}, LookupError),
        ({"NPLUS1_ERROR": "builtins.LookupError"}, LookupError),
    ],
    ids=["default", "class", "dotted-path"],
)
def test_detection_raises_configured_error(objects, client, settings, overrides, error):
    settings.NPLUS1_RAISE = True
    for name, value in overrides.items():
        setattr(settings, name, value)
    with pytest.raises(error, match="Occupation.user"):
        client.get("/lazy_loop/")


def test_unused_eager_load_is_reported_at_the_end_of_the_request(objects, client, settings):
    settings.NPLUS1_RAISE = True
    with pytest.raises(NPlus1Error, match="User.occupation"):
        client.get("/unused_select/")


def test_view_error_wins_over_detection_at_the_end_of_the_request(objects, client, settings):
    settings.NPLUS1_RAISE = True
    with pytest.raises(ValueError, match="view failed"):
        client.get("/unused_select_then_error/")


def test_detection_caught_by_a_template_fails_the_request(objects, client, settings):
    settings.NPLUS1_RAISE = True
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        client.get("/lazy_loop_caught_by_template/")


def test_prefetching_view_passes(objects, client, settings):
    settings.NPLUS1_RAISE = True
    response = client.get("/prefetched_hobbies/")
    assert response.status_code == 200
    assert response.content == b"4"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("NPLUS1_THRESHOLD", 0),
        ("NPLUS1_GET_THRESHOLD", "2"),
        ("NPLUS1_DUPLICATE_QUERY_THRESHOLD", 1.5),
        ("NPLUS1_LOG_LEVEL", "loud"),
        ("NPLUS1_LOGGER", 42),
        ("NPLUS1_ERROR", "builtins.NoSuchError"),
        ("NPLUS1_ERROR", "builtins.len"),
        ("NPLUS1_PROJECT_PACKAGES", "myproject"),
        ("NPLUS1_PROJECT_PACKAGES", [""]),
    ],
)
def test_invalid_setting_fails_at_startup(settings, name, value):
    settings.NPLUS1_RAISE = True
    setattr(settings, name, value)
    with pytest.raises(ImproperlyConfigured, match=name):
        build_middleware()


def test_middleware_needs_the_app_installed(monkeypatch):
    monkeypatch.delitem(sys.modules, "django_nplus1.patch")
    with pytest.raises(ImproperlyConfigured, match="INSTALLED_APPS"):
        build_middleware()


@pytest.mark.parametrize(
    "entry",
    [
        {"label": "n_plus_one"},
        {"model": "testapp.*"},
        {"model": Occupation},
        {"model": "testapp.Occupation", "field": "user"},
    ],
)
def test_whitelisted_detection_is_not_reported(objects, client, settings, entry):
    settings.NPLUS1_RAISE = True
    settings.NPLUS1_WHITELIST = [entry]
    response = client.get("/lazy_loop/")
    assert response.status_code == 200
    assert b"alice" in response.content


def test_whitelist_accepts_field_attname(objects, client, settings, recwarn, unvalidated_whitelist):
    settings.NPLUS1_WHITELIST = [{"label": "unused_field_load", "model": "testapp.Occupation", "field": "user_id"}]
    response = client.get("/prefetched_hobbies/")
    assert response.status_code == 200
    assert [str(w.message) for w in recwarn if "NPLUS1_WHITELIST" in str(w.message)] == []


def test_whitelist_warns_about_unknown_field(settings, unvalidated_whitelist):
    settings.NPLUS1_WHITELIST = [{"model": "testapp.User", "field": "hobby_list"}]
    with pytest.warns(UserWarning, match="not a field"):
        build_middleware()


@pytest.mark.parametrize(
    ("model", "match"),
    [("testapp.Ocupation", "'testapp.Ocupation' not found"), ("Occupation", "Did you mean one of: testapp.Occupation")],
)
def test_whitelist_with_unknown_model_fails_at_startup(settings, model, match):
    settings.NPLUS1_WHITELIST = [{"model": model}]
    with pytest.raises(NPlus1Error, match=match):
        build_middleware()


@pytest.mark.parametrize("path", ["/lazy_loop/", "/async_lazy_loop/"])
def test_async_request_is_checked(objects, async_client, settings, path):
    settings.NPLUS1_RAISE = True
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        async_to_sync(async_client.get)(path)


def test_async_request_detects_duplicate_queries(objects, async_client, settings):
    settings.NPLUS1_RAISE = True
    settings.NPLUS1_DETECT_DUPLICATE_QUERIES = True
    with pytest.raises(NPlus1Error, match="duplicate query"):
        async_to_sync(async_client.get)("/raw_sql_loop/")
