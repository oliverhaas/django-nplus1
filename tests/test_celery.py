import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from celery import Celery
from django.apps import apps
from django.core.exceptions import ImproperlyConfigured
from testapp.models import Occupation, User

from django_nplus1 import NPlus1Error, nplus1_allow, signals
from django_nplus1.celery import setup_celery_detection, teardown_celery_detection

pytestmark = pytest.mark.django_db

app = Celery("test_nplus1")


def read_occupation_users():
    return [occupation.user.name for occupation in Occupation.objects.order_by("pk")]


@app.task
def occupation_users():
    return read_occupation_users()


@app.task
def allowed_occupation_users():
    with nplus1_allow():
        return read_occupation_users()


@app.task
def occupation_users_or_none():
    try:
        return read_occupation_users()
    except Exception:  # noqa: BLE001
        return None


@app.task
def first_occupation_user():
    occupations = list(Occupation.objects.order_by("pk"))
    return occupations[0].user.name


@app.task
def count_users():
    return len(User.objects.all())


@app.task
def count_users_with_unused_select():
    return len(User.objects.select_related("occupation"))


@app.task
def fail():
    raise ValueError("task failed")


@app.task
def pause(started, resume):
    started.set()
    resume.wait(timeout=10)


@app.task(bind=True)
def replace_with_count_users(self):
    return self.replace(count_users.s())


@app.task
def occupation_users_in_subtask():
    return occupation_users.apply().get()


@app.task
def count_users_with_unused_select_in_subtask():
    return count_users_with_unused_select.apply().get()


@pytest.fixture
def disconnect_detection():
    yield
    teardown_celery_detection()


@pytest.fixture
def celery_detection(settings, disconnect_detection):
    settings.NPLUS1_RAISE = True
    setup_celery_detection()


def logged_errors(caplog):
    return [
        record.exc_info[1]
        for record in caplog.records
        if record.name == "django_nplus1" and record.levelno >= logging.ERROR
    ]


@pytest.mark.parametrize("throw", [False, True], ids=["stored", "propagated"])
def test_detection_fails_the_task(objects, celery_detection, caplog, throw):
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        occupation_users.apply(throw=throw).get()
    assert logged_errors(caplog) == []


def test_each_task_run_counts_on_its_own(objects, celery_detection):
    assert [first_occupation_user.apply().get() for _ in range(2)] == ["alice", "alice"]


def test_allow_inside_task_suppresses_detection(objects, celery_detection):
    assert allowed_occupation_users.apply().get() == ["alice", "bob"]


@pytest.mark.parametrize(
    ("task", "state"),
    [(count_users, "SUCCESS"), (fail, "FAILURE"), (replace_with_count_users, "SUCCESS")],
    ids=["success", "failure", "eager-replace"],
)
def test_detection_ends_with_the_task(objects, celery_detection, task, state):
    assert task.apply().state == state
    assert read_occupation_users() == ["alice", "bob"]


@pytest.mark.parametrize(
    ("task", "match"),
    [
        (count_users_with_unused_select, "User.occupation"),
        (occupation_users_or_none, "Occupation.user"),
        (count_users_with_unused_select_in_subtask, "User.occupation"),
    ],
    ids=["at-the-end", "caught", "subtask"],
)
def test_detection_not_raised_by_the_task_is_logged_once(objects, celery_detection, caplog, task, match):
    assert task.apply().successful()
    errors = logged_errors(caplog)
    assert [type(error) for error in errors] == [NPlus1Error]
    assert match in str(errors[0])


def test_detection_not_raised_by_a_task_in_teardown_is_logged_once(objects, celery_detection, nplus1, caplog, request):
    def run_task():
        count_users_with_unused_select.apply()
        assert [type(error) for error in logged_errors(caplog)] == [NPlus1Error]

    request.addfinalizer(run_task)


def test_detection_in_a_subtask_is_logged_once(objects, disconnect_detection, caplog):
    setup_celery_detection()
    assert occupation_users_in_subtask.apply().get() == ["alice", "bob"]
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "Occupation.user" in warnings[0]


def test_task_runs_when_detection_cannot_start(objects, celery_detection, settings, caplog):
    settings.NPLUS1_THRESHOLD = 0
    assert occupation_users.apply().get() == ["alice", "bob"]
    errors = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert [(record.name, type(record.exc_info[1])) for record in errors] == [("django_nplus1", ImproperlyConfigured)]


def test_runs_with_one_task_id_in_two_threads_end_their_own_scopes(celery_detection, caplog):
    started = [threading.Event(), threading.Event()]
    resume = [threading.Event(), threading.Event()]

    def run(index):
        pause.apply(args=(started[index], resume[index]), task_id="same-id")
        return signals.active()

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(run, 0)
        started[0].wait(timeout=10)
        second = pool.submit(run, 1)
        started[1].wait(timeout=10)
        resume[0].set()
        first_active = first.result(timeout=10)
        resume[1].set()
        second_active = second.result(timeout=10)
    assert (first_active, second_active) == (False, False)
    assert logged_errors(caplog) == []


def test_setting_enables_detection_at_startup(objects, settings, disconnect_detection):
    settings.NPLUS1_CELERY = True
    settings.NPLUS1_RAISE = True
    apps.get_app_config("django_nplus1").ready()
    with pytest.raises(NPlus1Error, match="Occupation.user"):
        occupation_users.apply().get()


@pytest.mark.parametrize(
    ("name", "value", "error", "match"),
    [
        ("NPLUS1_THRESHOLD", 0, ImproperlyConfigured, "NPLUS1_THRESHOLD"),
        ("NPLUS1_ERROR", "builtins.NoSuchError", ImproperlyConfigured, "NPLUS1_ERROR"),
        ("NPLUS1_WHITELIST", [{"model": "testapp.Nothing"}], NPlus1Error, "testapp.Nothing"),
    ],
)
def test_setup_rejects_invalid_settings(settings, disconnect_detection, name, value, error, match):
    settings.NPLUS1_RAISE = True
    setattr(settings, name, value)
    with pytest.raises(error, match=match):
        setup_celery_detection()


def test_setup_needs_the_app_installed(monkeypatch, disconnect_detection):
    monkeypatch.delitem(sys.modules, "django_nplus1.patch")
    with pytest.raises(ImproperlyConfigured, match="INSTALLED_APPS"):
        setup_celery_detection()
